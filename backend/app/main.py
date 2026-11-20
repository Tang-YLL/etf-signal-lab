import json
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from .db import Base, engine, session, SessionLocal
from . import models
from .config import COOKIE_HTTPS, session_secret
from .security import init_admin, verify_password, encode_password, ensure_login
from .strategies import STRATEGIES, Strategy
from .service import schedule_refresh, recalculate, rule_for, eligible_day, recover_abandoned_runs
from .provider import AKShareProvider, exchange

@asynccontextmanager
async def lifespan(app):
    # Docker runs Alembic first. create_all only handles clean dev/test starts.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        init_admin(db)
        for category, rule in STRATEGIES.items():
            if not db.get(models.StrategyTemplate, category):
                db.add(models.StrategyTemplate(category=category, version=1, params_json=json.dumps(asdict(rule))))
        db.commit()
        recover_abandoned_runs(db)
        schedule_refresh(db)
    yield

app=FastAPI(title="ETF Signal Lab", version="0.1.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=session_secret(), session_cookie="etfsession", max_age=86400, same_site="strict", https_only=COOKIE_HTTPS)
DB = Annotated[Session, Depends(session)]
Auth = Annotated[bool, Depends(ensure_login)]

class LoginBody(BaseModel):
    username: str
    password: str

class PasswordBody(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12,max_length=128)

class WatchBody(BaseModel):
    symbol: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1,max_length=120)
    category: str | None = None

class EditETF(BaseModel):
    category: str | None = None
    signals_enabled: bool | None = None

class RuleBody(BaseModel):
    buy_rsi: tuple[int,int,int]
    sell_rsi: tuple[int,int,int]
    boll_k: float = Field(gt=0,le=5)
    extreme_deviation: float = Field(ge=0,lt=.5)
    enabled: bool = True

class OverrideBody(BaseModel):
    params: RuleBody | None

@app.get("/api/v1/health")
def health():return {"status":"ok","version":"0.1.0"}

@app.post("/api/v1/auth/login")
def login(request:Request,body:LoginBody,db:DB):
    if request.headers.get("X-Requested-With")!="ETFSignalLab":raise HTTPException(403,"CSRF header required")
    stored=db.get(models.Setting,"password_hash")
    if body.username!="admin" or stored is None or not verify_password(body.password,stored.value):
        raise HTTPException(401,"Invalid credentials")
    request.session.clear()
    request.session["user"]="admin"
    return {"logged_in":True}

@app.post("/api/v1/auth/logout")
def logout(request:Request,authenticated:Auth):
    request.session.clear()
    return {"logged_in":False}

@app.get("/api/v1/auth/me")
def me(request:Request):return {"logged_in":request.session.get("user")=="admin"}

@app.post("/api/v1/auth/change-password")
def change_password(body:PasswordBody,db:DB,authenticated:Auth):
    record=db.get(models.Setting,"password_hash")
    if not verify_password(body.old_password,record.value):raise HTTPException(403,"Wrong old password")
    record.value=encode_password(body.new_password)
    db.commit()
    return {"ok":True}

def instrument_or_404(db,symbol):
    if not re.fullmatch(r"\d{6}",symbol):raise HTTPException(422,"Invalid ETF symbol")
    inst=db.get(models.Instrument,symbol)
    if not inst:raise HTTPException(404,"ETF not in catalogue")
    return inst

def latest_bar(db,symbol,confirmed=False):
    query=select(models.Bar).where(models.Bar.symbol==symbol,models.Bar.source=="akshare_em",models.Bar.adjustment=="RAW")
    if confirmed:
        query=query.where(models.Bar.data_status=="CONFIRMED")
    return db.scalar(query.order_by(desc(models.Bar.date)).limit(1))

def latest_indicator(db,symbol,date=None):
    inst=db.get(models.Instrument,symbol)
    if not inst:return None
    query=select(models.IndicatorSnapshot).where(models.IndicatorSnapshot.symbol==symbol,models.IndicatorSnapshot.rule_version==inst.rule_version)
    if date is not None:query=query.where(models.IndicatorSnapshot.date==date)
    return db.scalar(query.order_by(desc(models.IndicatorSnapshot.date),desc(models.IndicatorSnapshot.id)).limit(1))

def latest_threshold(db,symbol,date=None):
    inst=db.get(models.Instrument,symbol)
    if not inst:return None
    query=select(models.ThresholdSnapshot).where(models.ThresholdSnapshot.symbol==symbol,models.ThresholdSnapshot.rule_version==inst.rule_version)
    if date is not None:query=query.where(models.ThresholdSnapshot.date==date)
    return db.scalar(query.order_by(desc(models.ThresholdSnapshot.date),desc(models.ThresholdSnapshot.id)).limit(1))

def etf_summary(db,inst):
    # Historical/pending bars remain visible, but B/S signals must reference a
    # confirmed close. If a newer bar is pending, retain the preceding snapshot.
    newest=latest_bar(db,inst.symbol)
    confirmed=latest_bar(db,inst.symbol,confirmed=True)
    reference=confirmed or newest
    if not newest:
        status="UNAVAILABLE"
    elif confirmed and newest.date>confirmed.date:
        status="PENDING"
    elif confirmed and newest.date==confirmed.date:
        status="CONFIRMED"
    else:
        status=newest.data_status
    if confirmed and status=="CONFIRMED" and confirmed.date<eligible_day().isoformat():
        status="STALE"
    indicator=latest_indicator(db,inst.symbol,confirmed.date) if confirmed else None
    threshold=latest_threshold(db,inst.symbol,confirmed.date) if confirmed else None
    return {
        "symbol":inst.symbol,"name":inst.name,"exchange":inst.exchange,"category":inst.category,
        "signals_enabled":inst.signals_enabled,"rule_version":inst.rule_version,
        "close":reference.close if reference else None,"date":reference.date if reference else None,
        "pending_date":newest.date if newest and newest.data_status!="CONFIRMED" else None,
        "data_status":status,
        "indicators":({"rsi14":indicator.rsi14,"ma20":indicator.ma20,
                       "boll_upper":indicator.boll_upper,"boll_lower":indicator.boll_lower}
                      if indicator else None),
        "signal":indicator.signal if indicator else "UNAVAILABLE",
        "thresholds":json.loads(threshold.result_json) if threshold else None
    }

@app.get("/api/v1/system/status")
def status(db:DB,authenticated:Auth):
    last=db.scalar(select(models.RefreshRun).order_by(desc(models.RefreshRun.id)))
    return {"app_version":"0.1.0","provider":AKShareProvider().health_check(),
        "watchlist_count":len(db.scalars(select(models.Watchlist)).all()),
        "latest_run":({"id":last.id,"status":last.status,"message":last.message,"started_at":last.started_at} if last else None),
        "candidate_rules_warning":"策略阈值仅为未经历史有效性检验的默认值。",
        "confirmation_notice":"收盘确认采用盘后重复采样启发式，未经过独立供应商交叉验证。"}

@app.get("/api/v1/etfs")
def list_etfs(db:DB,authenticated:Auth):
    # Returns saved data immediately. Only launches background network refresh if cooldown permits.
    schedule_refresh(db)
    symbols=db.scalars(select(models.Watchlist.symbol).order_by(models.Watchlist.added_at)).all()
    return [etf_summary(db,db.get(models.Instrument,s)) for s in symbols]

@app.get("/api/v1/etfs/search")
def search_etfs(db:DB,authenticated:Auth,q:str=Query(min_length=1,max_length=60)):
    local=db.scalars(select(models.Instrument).where(models.Instrument.symbol.contains(q) | models.Instrument.name.contains(q)).limit(50)).all()
    results=[{"symbol":x.symbol,"name":x.name,"exchange":x.exchange,"category":x.category,"source":"LOCAL"} for x in local]
    # Remote search may fail; local results remain usable. No invented ETF identity.
    try:
        online=AKShareProvider().get_instruments(q)
        seen={r["symbol"] for r in results}
        results += [{**x,"category":None,"source":"AKSHARE"} for x in online if x["symbol"] not in seen]
    except Exception:
        pass
    return results[:80]

@app.post("/api/v1/watchlist",status_code=201)
def add_watch(body:WatchBody,db:DB,authenticated:Auth):
    if body.category is not None and body.category not in STRATEGIES:raise HTTPException(422,"Unknown category")
    inst=db.get(models.Instrument,body.symbol)
    if not inst:
        inst=models.Instrument(symbol=body.symbol,name=body.name,exchange=exchange(body.symbol),category=body.category)
        db.add(inst)
    if not db.get(models.Watchlist,body.symbol):db.add(models.Watchlist(symbol=body.symbol))
    db.commit()
    schedule_refresh(db,[body.symbol],force=True)
    return etf_summary(db,inst)

@app.delete("/api/v1/watchlist/{symbol}")
def delete_watch(symbol:str,db:DB,authenticated:Auth):
    inst=instrument_or_404(db,symbol)
    record=db.get(models.Watchlist,symbol)
    if record:db.delete(record);db.commit()
    return {"ok":True}

@app.get("/api/v1/etfs/{symbol}")
def detail(symbol:str,db:DB,authenticated:Auth):return etf_summary(db,instrument_or_404(db,symbol))

@app.patch("/api/v1/etfs/{symbol}")
def edit_etf(symbol:str,body:EditETF,db:DB,authenticated:Auth):
    inst=instrument_or_404(db,symbol)
    # Distinguish an omitted category from explicit null (clear classification).
    if "category" in body.model_fields_set:
        if body.category is not None and body.category not in STRATEGIES:
            raise HTTPException(422,"Unknown category")
        inst.category=body.category
    if body.signals_enabled is not None:inst.signals_enabled=body.signals_enabled
    inst.rule_version+=1
    db.commit()
    recalculate(db,symbol)
    return etf_summary(db,inst)

@app.get("/api/v1/etfs/{symbol}/daily-bars")
def daily_bars(symbol:str,db:DB,authenticated:Auth,limit:int=Query(300,ge=20,le=800)):
    instrument_or_404(db,symbol)
    rows=db.scalars(select(models.Bar).where(models.Bar.symbol==symbol).order_by(desc(models.Bar.date)).limit(limit)).all()
    return [{"date":r.date,"open":r.open,"high":r.high,"low":r.low,"close":r.close,"volume":r.volume,"status":r.data_status} for r in reversed(rows)]

@app.get("/api/v1/etfs/{symbol}/indicators")
def indicators(symbol:str,db:DB,authenticated:Auth,limit:int=Query(300,ge=20,le=800)):
    inst=instrument_or_404(db,symbol)
    rows=db.scalars(select(models.IndicatorSnapshot).where(models.IndicatorSnapshot.symbol==symbol,models.IndicatorSnapshot.rule_version==inst.rule_version).order_by(desc(models.IndicatorSnapshot.date),desc(models.IndicatorSnapshot.id))).all()
    by_date={}
    for r in rows:
        if r.date not in by_date:by_date[r.date]={"date":r.date,"rsi14":r.rsi14,"ma20":r.ma20,"boll_upper":r.boll_upper,"boll_lower":r.boll_lower,"signal":r.signal,"rule_version":r.rule_version}
    confirmed_dates=set(db.scalars(select(models.Bar.date).where(
        models.Bar.symbol==symbol,models.Bar.source=="akshare_em",
        models.Bar.adjustment=="RAW",models.Bar.data_status=="CONFIRMED")).all())
    for day,value in by_date.items():
        if day not in confirmed_dates:
            value["signal"]="PENDING"
            value["data_status"]="PENDING"
        else:
            value["data_status"]="CONFIRMED"
    return list(reversed(list(by_date.values())[:limit]))

@app.get("/api/v1/etfs/{symbol}/signals")
def signals(symbol:str,db:DB,authenticated:Auth):
    return [r for r in indicators(symbol,db,authenticated,limit=300) if r["signal"] not in ("WATCH","UNAVAILABLE","PENDING")]

@app.get("/api/v1/etfs/{symbol}/next-day-thresholds")
def thresholds(symbol:str,db:DB,authenticated:Auth):
    inst=instrument_or_404(db,symbol)
    confirmed=latest_bar(db,symbol,confirmed=True)
    row=latest_threshold(db,symbol,confirmed.date) if confirmed else None
    return json.loads(row.result_json) if row else {"status":"UNAVAILABLE","reason":"No confirmed close with a calculated threshold","intervals":{}}

@app.get("/api/v1/strategy/templates")
def strategies(db:DB,authenticated:Auth):
    return [{"category":r.category,"version":r.version,"params":json.loads(r.params_json)} for r in db.scalars(select(models.StrategyTemplate)).all()]

@app.put("/api/v1/strategy/templates/{category}")
def update_strategy(category:str,body:RuleBody,db:DB,authenticated:Auth):
    template=db.get(models.StrategyTemplate,category)
    if template is None:raise HTTPException(404,"Unknown template")
    template.version+=1
    template.params_json=body.model_dump_json()
    symbols=db.scalars(select(models.Instrument.symbol).where(models.Instrument.category==category)).all()
    for symbol in symbols:db.get(models.Instrument,symbol).rule_version+=1
    db.commit()
    for symbol in symbols:recalculate(db,symbol)
    return {"category":category,"version":template.version}

@app.put("/api/v1/etfs/{symbol}/strategy-override")
def override_strategy(symbol:str,body:OverrideBody,db:DB,authenticated:Auth):
    inst=instrument_or_404(db,symbol)
    existing=db.get(models.StrategyOverride,symbol)
    if body.params is None:
        if existing:db.delete(existing)
    elif existing:
        existing.params_json=body.params.model_dump_json()
        existing.version+=1
    else:db.add(models.StrategyOverride(symbol=symbol,params_json=body.params.model_dump_json()))
    inst.rule_version+=1
    db.commit()
    recalculate(db,symbol)
    return etf_summary(db,inst)

@app.post("/api/v1/data/refresh")
def refresh(db:DB,authenticated:Auth):
    run_id=schedule_refresh(db,force=True)
    return {"status":"QUEUED" if run_id else "ALREADY_RUNNING_OR_EMPTY","run_id":run_id}

@app.post("/api/v1/data/refresh/{symbol}")
def refresh_one(symbol:str,db:DB,authenticated:Auth):
    instrument_or_404(db,symbol)
    run_id=schedule_refresh(db,[symbol],force=True)
    return {"status":"QUEUED" if run_id else "ALREADY_RUNNING","run_id":run_id}

@app.get("/api/v1/data/runs")
def list_runs(db:DB,authenticated:Auth):
    rows=db.scalars(select(models.RefreshRun).order_by(desc(models.RefreshRun.id)).limit(30)).all()
    return [{"id":r.id,"status":r.status,"message":r.message,"started_at":r.started_at,"finished_at":r.finished_at} for r in rows]

@app.get("/api/v1/data/runs/{run_id}")
def run_status(run_id:int,db:DB,authenticated:Auth):
    run=db.get(models.RefreshRun,run_id)
    if not run:raise HTTPException(404,"No such run")
    return {"id":run.id,"status":run.status,"message":run.message,"finished_at":run.finished_at}
