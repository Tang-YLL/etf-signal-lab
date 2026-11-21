import json
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Annotated
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from .db import Base, engine, session, SessionLocal
from . import models
from .strategies import STRATEGIES, Strategy
from .service import schedule_refresh, recalculate, rule_for, eligible_day, recover_abandoned_runs, active_source
from .provider import AKShareProvider, build_provider, exchange

@asynccontextmanager
async def lifespan(app):
    # Docker runs Alembic first. create_all only handles clean dev/test starts.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for category, rule in STRATEGIES.items():
            if not db.get(models.StrategyTemplate, category):
                db.add(models.StrategyTemplate(category=category, version=1, params_json=json.dumps(asdict(rule))))
        db.commit()
        recover_abandoned_runs(db)
        schedule_refresh(db)
    yield

app=FastAPI(title="ETF Signal Lab", version="0.1.0", lifespan=lifespan)
DB = Annotated[Session, Depends(session)]

class WatchBody(BaseModel):
    symbol: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1,max_length=120)
    full_name: str | None = Field(default=None,max_length=180)
    market_name: str | None = Field(default=None,max_length=120)
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

def instrument_or_404(db,symbol):
    if not re.fullmatch(r"\d{6}",symbol):raise HTTPException(422,"Invalid ETF symbol")
    inst=db.get(models.Instrument,symbol)
    if not inst:raise HTTPException(404,"ETF not in catalogue")
    return inst

def latest_bar(db,symbol,confirmed=False,source=None):
    source = source or active_source(db, symbol)
    query=select(models.Bar).where(models.Bar.symbol==symbol,models.Bar.adjustment=="RAW")
    if source:
        query=query.where(models.Bar.source==source)
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
    # Numeric indicators can be shown provisionally on the first fetch.
    # Directional signals and next-day threshold snapshots remain confirmed-only.
    indicator=latest_indicator(db,inst.symbol,reference.date) if reference else None
    threshold=latest_threshold(db,inst.symbol,confirmed.date) if confirmed else None
    return {
        "symbol":inst.symbol,"name":inst.name,"full_name":inst.full_name,"market_name":inst.market_name,
        "exchange":inst.exchange,"category":inst.category,
        "signals_enabled":inst.signals_enabled,"rule_version":inst.rule_version,
        "close":reference.close if reference else None,"date":reference.date if reference else None,
        "pending_date":newest.date if newest and newest.data_status!="CONFIRMED" else None,
        "data_status":status,
        "indicators":({"rsi14":indicator.rsi14,"ma20":indicator.ma20,
                       "boll_upper":indicator.boll_upper,"boll_lower":indicator.boll_lower}
                      if indicator else None),
        "indicator_status":"CONFIRMED" if confirmed and indicator else ("PENDING" if indicator else "UNAVAILABLE"),
        "signal":indicator.signal if confirmed and indicator else "UNAVAILABLE",
        "thresholds":json.loads(threshold.result_json) if confirmed and threshold else None
    }

@app.get("/api/v1/system/status")
def status(db:DB):
    last=db.scalar(select(models.RefreshRun).order_by(desc(models.RefreshRun.id)))
    return {"app_version":"0.1.0","provider":build_provider().health_check(),
        "watchlist_count":len(db.scalars(select(models.Watchlist)).all()),
        "latest_run":({"id":last.id,"status":last.status,"message":last.message,"started_at":last.started_at} if last else None),
        "candidate_rules_warning":"策略阈值仅为未经历史有效性检验的默认值。",
        "confirmation_notice":"收盘确认采用盘后重复采样启发式，未经过独立供应商交叉验证。"}

@app.get("/api/v1/etfs")
def list_etfs(db:DB):
    # Returns saved data immediately. Only launches background network refresh if cooldown permits.
    schedule_refresh(db)
    symbols=db.scalars(select(models.Watchlist.symbol).order_by(models.Watchlist.added_at)).all()
    return [etf_summary(db,db.get(models.Instrument,s)) for s in symbols]

@app.get("/api/v1/etfs/search")
def search_etfs(response:Response,db:DB,q:str=Query(min_length=1,max_length=60),
                limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0,le=5000)):
    keyword=q.strip()
    if not keyword:
        return []
    exact=re.fullmatch(r"\d{6}",keyword)
    local_query=select(models.Instrument).where(
        models.Instrument.symbol.contains(keyword) |
        models.Instrument.name.contains(keyword) |
        models.Instrument.full_name.contains(keyword) |
        models.Instrument.market_name.contains(keyword)
    ).order_by(models.Instrument.symbol).limit(limit+offset)
    local=db.scalars(local_query).all()
    results=[{"symbol":x.symbol,"name":x.name,"full_name":x.full_name,"market_name":x.market_name,
              "exchange":x.exchange,"category":x.category,"source":"LOCAL"} for x in local]
    # Remote search may fail; local results remain usable. No invented ETF identity.
    try:
        online=AKShareProvider().get_instruments(keyword,limit=1000)
        response.headers["X-ETF-Catalogue-Source"]=AKShareProvider.catalogue_status()["source"]
        if AKShareProvider.catalogue_status()["warning"]:
            response.headers["X-ETF-Catalogue-Warning"]=AKShareProvider.catalogue_status()["warning"]
        seen={r["symbol"] for r in results}
        results += [{**x,"category":None} for x in online if x["symbol"] not in seen]
    except Exception as exc:
        response.headers["X-ETF-Catalogue-Warning"]=f"SEARCH_UNAVAILABLE:{type(exc).__name__}"
        if exact and not results:
            response.headers["X-ETF-Catalogue-Exact-Code"]="NOT_IN_CACHED_CATALOGUE"
    results.sort(key=lambda row:(row["symbol"]!=keyword,row["symbol"]))
    response.headers["X-ETF-Search-Total"]=str(len(results))
    return results[offset:offset+limit]

@app.get("/api/v1/etfs/search/status")
def search_status():
    return AKShareProvider.catalogue_status()

@app.post("/api/v1/watchlist",status_code=201)
def add_watch(body:WatchBody,db:DB):
    if body.category is not None and body.category not in STRATEGIES:raise HTTPException(422,"Unknown category")
    inst=db.get(models.Instrument,body.symbol)
    if not inst:
        inst=models.Instrument(symbol=body.symbol,name=body.name,full_name=body.full_name,
                               market_name=body.market_name,exchange=exchange(body.symbol),category=body.category)
        db.add(inst)
    else:
        inst.full_name=body.full_name or inst.full_name
        inst.market_name=body.market_name or inst.market_name
    if not db.get(models.Watchlist,body.symbol):db.add(models.Watchlist(symbol=body.symbol))
    db.commit()
    schedule_refresh(db,[body.symbol],force=True)
    return etf_summary(db,inst)

@app.delete("/api/v1/watchlist/{symbol}")
def delete_watch(symbol:str,db:DB):
    inst=instrument_or_404(db,symbol)
    record=db.get(models.Watchlist,symbol)
    if record:db.delete(record);db.commit()
    return {"ok":True}

@app.get("/api/v1/etfs/{symbol}")
def detail(symbol:str,db:DB):return etf_summary(db,instrument_or_404(db,symbol))

@app.patch("/api/v1/etfs/{symbol}")
def edit_etf(symbol:str,body:EditETF,db:DB):
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
def daily_bars(symbol:str,db:DB,limit:int=Query(300,ge=20,le=800)):
    instrument_or_404(db,symbol)
    source=active_source(db,symbol)
    query=select(models.Bar).where(models.Bar.symbol==symbol,models.Bar.adjustment=="RAW")
    if source:
        query=query.where(models.Bar.source==source)
    rows=db.scalars(query.order_by(desc(models.Bar.date)).limit(limit)).all()
    return [{"date":r.date,"open":r.open,"high":r.high,"low":r.low,"close":r.close,"volume":r.volume,"status":r.data_status} for r in reversed(rows)]

@app.get("/api/v1/etfs/{symbol}/indicators")
def indicators(symbol:str,db:DB,limit:int=Query(300,ge=20,le=800)):
    inst=instrument_or_404(db,symbol)
    rows=db.scalars(select(models.IndicatorSnapshot).where(models.IndicatorSnapshot.symbol==symbol,models.IndicatorSnapshot.rule_version==inst.rule_version).order_by(desc(models.IndicatorSnapshot.date),desc(models.IndicatorSnapshot.id))).all()
    by_date={}
    for r in rows:
        if r.date not in by_date:by_date[r.date]={"date":r.date,"rsi14":r.rsi14,"ma20":r.ma20,"boll_upper":r.boll_upper,"boll_lower":r.boll_lower,"signal":r.signal,"rule_version":r.rule_version}
    source=active_source(db,symbol)
    confirmed_query=select(models.Bar.date).where(
        models.Bar.symbol==symbol,models.Bar.adjustment=="RAW",models.Bar.data_status=="CONFIRMED")
    if source:
        confirmed_query=confirmed_query.where(models.Bar.source==source)
    confirmed_dates=set(db.scalars(confirmed_query).all())
    for day,value in by_date.items():
        if day not in confirmed_dates:
            value["signal"]="PENDING"
            value["data_status"]="PENDING"
        else:
            value["data_status"]="CONFIRMED"
    return list(reversed(list(by_date.values())[:limit]))

@app.get("/api/v1/etfs/{symbol}/signals")
def signals(symbol:str,db:DB):
    return [r for r in indicators(symbol,db,limit=300) if r["signal"] not in ("WATCH","UNAVAILABLE","PENDING")]

@app.get("/api/v1/etfs/{symbol}/next-day-thresholds")
def thresholds(symbol:str,db:DB):
    inst=instrument_or_404(db,symbol)
    confirmed=latest_bar(db,symbol,confirmed=True)
    row=latest_threshold(db,symbol,confirmed.date) if confirmed else None
    return json.loads(row.result_json) if row else {"status":"UNAVAILABLE","reason":"No confirmed close with a calculated threshold","intervals":{}}

@app.get("/api/v1/strategy/templates")
def strategies(db:DB):
    return [{"category":r.category,"version":r.version,"params":json.loads(r.params_json)} for r in db.scalars(select(models.StrategyTemplate)).all()]

@app.put("/api/v1/strategy/templates/{category}")
def update_strategy(category:str,body:RuleBody,db:DB):
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
def override_strategy(symbol:str,body:OverrideBody,db:DB):
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
def refresh(db:DB):
    run_id=schedule_refresh(db,force=True)
    return {"status":"QUEUED" if run_id else "ALREADY_RUNNING_OR_EMPTY","run_id":run_id}

@app.post("/api/v1/data/refresh/{symbol}")
def refresh_one(symbol:str,db:DB):
    instrument_or_404(db,symbol)
    run_id=schedule_refresh(db,[symbol],force=True)
    return {"status":"QUEUED" if run_id else "ALREADY_RUNNING","run_id":run_id}

@app.get("/api/v1/data/runs")
def list_runs(db:DB):
    rows=db.scalars(select(models.RefreshRun).order_by(desc(models.RefreshRun.id)).limit(30)).all()
    return [{"id":r.id,"status":r.status,"message":r.message,"started_at":r.started_at,"finished_at":r.finished_at} for r in rows]

@app.get("/api/v1/data/runs/{run_id}")
def run_status(run_id:int,db:DB):
    run=db.get(models.RefreshRun,run_id)
    if not run:raise HTTPException(404,"No such run")
    return {"id":run.id,"status":run.status,"message":run.message,"finished_at":run.finished_at}
