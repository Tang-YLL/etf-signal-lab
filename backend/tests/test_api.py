from app.models import Instrument, Bar, Watchlist, Revision
from app.db import SessionLocal
from app.provider import DailyBar
from app.service import ingest, recalculate
from datetime import date,timedelta

def test_auth(client):
    assert client.get("/api/v1/health").status_code==200
    assert client.get("/api/v1/etfs").status_code==401
    assert client.post("/api/v1/auth/login",json={"username":"admin","password":"wrong"},headers={"X-Requested-With":"ETFSignalLab"}).status_code==401

def test_api_basic(logged_client,monkeypatch):
    # No network required for acceptance fixture; pause automatic refresh thread.
    monkeypatch.setattr("app.main.schedule_refresh",lambda *args,**kwargs:None)
    response=logged_client.post("/api/v1/watchlist",json={"symbol":"510300","name":"测试沪深300","category":"broad"},headers={"X-Requested-With":"ETFSignalLab"})
    assert response.status_code==201, response.text
    assert logged_client.get("/api/v1/etfs").json()[0]["symbol"]=="510300"
    assert logged_client.patch("/api/v1/etfs/510300",json={"category":"gold"},headers={"X-Requested-With":"ETFSignalLab"}).status_code==200
    assert logged_client.delete("/api/v1/watchlist/510300",headers={"X-Requested-With":"ETFSignalLab"}).status_code==200
    assert logged_client.get("/api/v1/etfs").json()==[]

def test_ingest_revision_and_recalculation(logged_client):
    with SessionLocal() as db:
        inst=Instrument(symbol="510300",name="测试沪深300",exchange="SH",category="broad")
        db.add(inst)
        db.commit()
        first=date(2025,1,1)
        rows=[DailyBar((first+timedelta(days=n)).isoformat(),1+n*.001,1.02+n*.001,.98+n*.001,1.0+n*.001,1000.,10000.) for n in range(35)]
        count=ingest(db,"510300",rows)
        assert count==35
        assert ingest(db,"510300",rows)==0
        recalculate(db,"510300")
        revised=list(rows)
        r=revised[-1]
        revised[-1]=DailyBar(r.date,r.open,r.high,r.low,r.close+.0001,r.volume,r.amount)
        # This revision remains inside OHLC range.
        assert ingest(db,"510300",revised)==1
        assert len(db.query(Revision).all())==1
        recalculate(db,"510300")
    assert logged_client.get("/api/v1/etfs/510300").json()["close"]>1.0
    assert logged_client.get("/api/v1/etfs/510300/next-day-thresholds").json()["status"] in ("BOUNDED_EXHAUSTIVE","RANGE_TOO_LARGE")
