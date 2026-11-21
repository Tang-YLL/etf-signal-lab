from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.provider import DailyBar
from app import service, models
from app.db import SessionLocal

def test_same_day_after_close_can_pass_repeat_sampling(client, monkeypatch):
    monkeypatch.setattr(service, "shanghai_now",
        lambda: datetime(2026,11,20,18,30,tzinfo=ZoneInfo("Asia/Shanghai")))
    row=DailyBar("2026-11-20", 1.0, 1.1, 0.9, 1.05, 1000, 1050)
    with SessionLocal() as db:
        service.ingest(db,"510300",[row])
        bar=db.query(models.Bar).filter_by(symbol="510300").one()
        assert bar.data_status=="PENDING"
        bar.last_seen=datetime.now(timezone.utc)-timedelta(minutes=11)
        db.commit()
        service.ingest(db,"510300",[row])
        assert db.query(models.Bar).filter_by(symbol="510300").one().data_status=="CONFIRMED"

def test_restarted_refresh_runs_are_marked_interrupted(client):
    with SessionLocal() as db:
        run=models.RefreshRun(status="RUNNING",symbols_json='["510300"]')
        db.add(run)
        db.commit()
        assert service.recover_abandoned_runs(db)==1
        assert db.get(models.RefreshRun,run.id).status=="INTERRUPTED"
        assert service.recover_abandoned_runs(db)==0
