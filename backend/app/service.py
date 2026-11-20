"""Non-blocking refresh coordinator and historical calculation persistence."""
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta, timezone, date
from dataclasses import asdict
from zoneinfo import ZoneInfo
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from . import models
from .db import SessionLocal
from .provider import AKShareProvider, DataError
from .indicators import calculate
from .strategies import STRATEGIES, Strategy, evaluate
from .solvers import solve
from .config import COOLDOWN

log = logging.getLogger(__name__)
TZ=ZoneInfo("Asia/Shanghai")
_gate=threading.Lock()
_pending=False
_last_check: datetime | None=None
_provider_factory=AKShareProvider

def set_provider_factory(factory):
    global _provider_factory
    _provider_factory=factory

def shanghai_now():
    return datetime.now(TZ)

def eligible_day():
    today=shanghai_now()
    # No current-session bar until late post-market; still requires repeat-sample verification.
    target = today.date() if today.weekday()<5 and today.hour>=18 else today.date()-timedelta(days=1)
    while target.weekday()>=5:
        target-=timedelta(days=1)
    return target

def serialize_bar(bar):
    return {key:getattr(bar,key) for key in ("date","open","high","low","close","volume","amount")}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def rule_for(db:Session, inst: models.Instrument) -> Strategy | None:
    if not inst.category or inst.category not in STRATEGIES:return None
    template=db.get(models.StrategyTemplate,inst.category)
    params=json.loads(template.params_json) if template else asdict(STRATEGIES[inst.category])
    override=db.get(models.StrategyOverride,inst.symbol)
    if override:params.update(json.loads(override.params_json))
    params["buy_rsi"]=tuple(params["buy_rsi"])
    params["sell_rsi"]=tuple(params["sell_rsi"])
    params["enabled"]=bool(params["enabled"] and inst.signals_enabled)
    return Strategy(**params)

def recalculate(db:Session, symbol: str):
    inst=db.get(models.Instrument,symbol)
    if inst is None: return
    rows=db.scalars(select(models.Bar).where(models.Bar.symbol==symbol,models.Bar.adjustment=="RAW",models.Bar.source=="akshare_em").order_by(models.Bar.date)).all()
    if not rows:return
    closes=[]
    rule=rule_for(db,inst)
    for row in rows:
        closes.append(row.close)
        if len(closes)<20:continue
        ind=calculate(closes,rule.boll_k if rule else 2.0)
        current_signal=evaluate(row.close,ind,rule) if rule else "UNAVAILABLE"
        version_hash=digest([(r.date,r.checksum) for r in rows[:len(closes)]])
        existing=db.scalar(select(models.IndicatorSnapshot).where(models.IndicatorSnapshot.symbol==symbol,models.IndicatorSnapshot.date==row.date,models.IndicatorSnapshot.rule_version==inst.rule_version,models.IndicatorSnapshot.data_hash==version_hash))
        if not existing:
            db.add(models.IndicatorSnapshot(symbol=symbol,date=row.date,rule_version=inst.rule_version,data_hash=version_hash,
                rsi14=ind["rsi14"],ma20=ind["ma20"],boll_lower=ind["boll_lower"],boll_upper=ind["boll_upper"],
                signal=current_signal,rule_json=json.dumps(asdict(rule)) if rule else "{}"))
    # Compute the actionable reference only for the latest confirmed close.
    # A pending session must never displace the preceding confirmed scenario.
    confirmed_indices=[i for i,row in enumerate(rows) if row.data_status=="CONFIRMED"]
    if rule and confirmed_indices:
        index=confirmed_indices[-1]
        if index>=19:
            latest=rows[index]
            final_hash=digest([(r.date,r.checksum) for r in rows[:index+1]])
            existing=db.scalar(select(models.ThresholdSnapshot).where(
                models.ThresholdSnapshot.symbol==symbol,models.ThresholdSnapshot.date==latest.date,
                models.ThresholdSnapshot.rule_version==inst.rule_version,
                models.ThresholdSnapshot.data_hash==final_hash))
            if not existing:
                output=solve(closes[:index+1],rule,tick="0.001")
                db.add(models.ThresholdSnapshot(symbol=symbol,date=latest.date,rule_version=inst.rule_version,
                    data_hash=final_hash,result_json=json.dumps(output)))
    db.commit()

def ingest(db:Session, symbol: str, fetched: list):
    """Upsert with revisions and conservative two-sample confirmation."""
    updates=0
    observed=datetime.now(timezone.utc)
    allowed=eligible_day()
    for raw in fetched:
        value=serialize_bar(raw)
        day=date.fromisoformat(value["date"])
        if day>allowed:continue
        checksum=digest(value)
        existing=db.scalar(select(models.Bar).where(models.Bar.symbol==symbol,models.Bar.date==raw.date,models.Bar.source=="akshare_em",models.Bar.adjustment=="RAW"))
        if existing is None:
            db.add(models.Bar(symbol=symbol,source="akshare_em",adjustment="RAW",checksum=checksum,**value))
            updates+=1
        elif existing.checksum!=checksum:
            old={k:getattr(existing,k) for k in ("open","high","low","close","volume","amount")}
            db.add(models.Revision(symbol=symbol,date=raw.date,old_json=json.dumps(old),new_json=json.dumps(value)))
            for key in ("open","high","low","close","volume","amount"):setattr(existing,key,value[key])
            existing.checksum=checksum
            existing.last_seen=observed
            existing.first_seen=observed
            existing.stable_observations=1
            existing.data_status="PENDING"
            updates+=1
        else:
            # Vendor does not publish a final flag. Repeat agreement 10+ min later is a heuristic.
            if observed.replace(tzinfo=None)-existing.last_seen.replace(tzinfo=None)>=timedelta(minutes=10):
                existing.stable_observations+=1
                if existing.stable_observations>=2 and day<shanghai_now().date():
                    existing.data_status="CONFIRMED"
            existing.last_seen=observed
    db.commit()
    return updates

def perform_refresh(run_id: int):
    global _pending
    try:
        with SessionLocal() as db:
            run=db.get(models.RefreshRun,run_id)
            run.status="RUNNING"
            db.commit()
            symbols=json.loads(run.symbols_json)
            provider=_provider_factory()
            failures=[]
            changed=0
            for symbol in symbols:
                try:
                    latest=db.scalar(select(models.Bar).where(models.Bar.symbol==symbol).order_by(desc(models.Bar.date)))
                    start=date.fromisoformat(latest.date)-timedelta(days=45) if latest else eligible_day()-timedelta(days=730)
                    rows=provider.get_daily_bars(symbol,start,shanghai_now().date(),"RAW")
                    changed+=ingest(db,symbol,rows)
                    recalculate(db,symbol)
                except Exception as exc:
                    log.warning("Failed refreshing ETF %s: %s",symbol,type(exc).__name__)
                    failures.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:180]}")
            run.status="PARTIAL" if failures and len(failures)<len(symbols) else "FAILED" if failures else "SUCCESS"
            run.message=json.dumps({"changed":changed,"failures":failures},ensure_ascii=False)
            run.finished_at=datetime.now(timezone.utc)
            db.commit()
    except Exception:
        log.exception("Refresh run crashed")
        try:
            with SessionLocal() as db:
                run=db.get(models.RefreshRun,run_id)
                if run:
                    run.status="FAILED"
                    run.message="Unexpected refresh failure; see server logs"
                    run.finished_at=datetime.now(timezone.utc)
                    db.commit()
        except Exception:log.exception("Cannot persist refresh error")
    finally:
        with _gate:_pending=False

def recover_abandoned_runs(db:Session) -> int:
    """Runs interrupted by process/container termination cannot resume a thread."""
    unfinished=db.scalars(select(models.RefreshRun).where(
        models.RefreshRun.status.in_(("QUEUED","RUNNING")))).all()
    for run in unfinished:
        run.status="INTERRUPTED"
        run.finished_at=datetime.now(timezone.utc)
        run.message="Backend restarted before this update completed; retrying watchlist on startup"
    if unfinished:db.commit()
    return len(unfinished)

def schedule_refresh(db:Session, symbols: list[str] | None=None, force=False) -> int | None:
    global _pending, _last_check
    now=datetime.now(timezone.utc)
    with _gate:
        if _pending or not force and _last_check and (now-_last_check).total_seconds()<COOLDOWN:return None
        if symbols is None:
            symbols=db.scalars(select(models.Watchlist.symbol)).all()
        if not symbols:return None
        _pending=True
        _last_check=now
    try:
        run=models.RefreshRun(status="QUEUED",source="akshare_em",symbols_json=json.dumps(sorted(set(symbols))))
        db.add(run)
        db.commit()
        db.refresh(run)
        threading.Thread(target=perform_refresh,args=(run.id,),daemon=True,name="etf-refresh").start()
        return run.id
    except Exception:
        with _gate:_pending=False
        raise
