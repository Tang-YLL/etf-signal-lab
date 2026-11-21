from app.models import Instrument, Bar, Watchlist, Revision
from app.db import SessionLocal
from app.provider import DailyBar
from app.service import active_source, ingest, recalculate
from datetime import date,timedelta

def test_api_is_available_without_auth(client):
    assert client.get("/api/v1/health").status_code==200
    assert client.get("/api/v1/etfs").status_code==200

def test_search_returns_two_official_names(client, monkeypatch):
    from app.provider import AKShareProvider
    monkeypatch.setattr(AKShareProvider, "get_instruments", lambda self, text, limit=1000: [{
        "symbol":"159307", "name":"博时中证红利低波100ETF",
        "full_name":"博时中证红利低波动100交易型开放式指数证券投资基金",
        "market_name":"红利低波100ETF博时", "exchange":"SZ", "source":"AKSHARE_EM"
    }])
    response=client.get("/api/v1/etfs/search?q=159307")
    assert response.status_code==200
    assert response.json()[0]["full_name"].startswith("博时中证红利低波动100")
    assert response.json()[0]["market_name"]=="红利低波100ETF博时"

def test_search_supports_offset_and_limit(client, monkeypatch):
    from app.provider import AKShareProvider
    monkeypatch.setattr(AKShareProvider, "get_instruments", lambda self, text, limit=1000: [
        {"symbol":"159307","name":"博时中证红利低波100ETF","full_name":None,"market_name":None,"exchange":"SZ","source":"AKSHARE_EM"},
        {"symbol":"159915","name":"创业板ETF","full_name":None,"market_name":None,"exchange":"SZ","source":"AKSHARE_EM"}
    ])
    response=client.get("/api/v1/etfs/search?q=ETF&limit=1&offset=1")
    assert response.status_code==200
    assert response.headers["X-ETF-Search-Total"]=="2"
    assert len(response.json())==1
    assert response.json()[0]["symbol"]=="159915"

def test_search_status_is_explicit(client):
    response=client.get("/api/v1/etfs/search/status")
    assert response.status_code==200
    assert set(response.json())=={"source","warning"}

def test_api_basic(client,monkeypatch):
    # No network required for acceptance fixture; pause automatic refresh thread.
    monkeypatch.setattr("app.main.schedule_refresh",lambda *args,**kwargs:None)
    response=client.post("/api/v1/watchlist",json={"symbol":"510300","name":"测试沪深300","category":"broad"})
    assert response.status_code==201, response.text
    assert client.get("/api/v1/etfs").json()[0]["symbol"]=="510300"
    assert client.patch("/api/v1/etfs/510300",json={"category":"gold"}).status_code==200
    clear=client.patch("/api/v1/etfs/510300",json={"category":None})
    assert clear.status_code==200
    assert clear.json()["category"] is None
    assert client.delete("/api/v1/watchlist/510300").status_code==200
    assert client.get("/api/v1/etfs").json()==[]

def test_ingest_revision_and_recalculation(client):
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
    summary=client.get("/api/v1/etfs/510300").json()
    assert summary["close"]>1.0
    assert summary["data_status"]=="PENDING"
    assert summary["signal"]=="UNAVAILABLE"
    assert summary["indicators"] is not None
    assert summary["indicator_status"]=="PENDING"
    assert summary["thresholds"] is None
    assert client.get("/api/v1/etfs/510300/next-day-thresholds").json()["status"]=="UNAVAILABLE"
    with SessionLocal() as db:
        bars=db.query(Bar).all()
        for bar in bars:bar.data_status="CONFIRMED"
        db.commit()
        recalculate(db,"510300")
    confirmed=client.get("/api/v1/etfs/510300").json()
    assert confirmed["data_status"] in ("CONFIRMED","STALE")
    assert confirmed["indicators"] is not None
    assert confirmed["thresholds"]["status"] in ("BOUNDED_EXHAUSTIVE","RANGE_TOO_LARGE")
    with SessionLocal() as db:
        latest=db.query(Bar).order_by(Bar.date.desc()).first()
        newest_date=latest.date
        latest.data_status="PENDING"
        db.commit()
        recalculate(db,"510300")
    pending=client.get("/api/v1/etfs/510300").json()
    assert pending["data_status"]=="PENDING"
    assert pending["pending_date"]==newest_date
    assert pending["date"]!=newest_date
    assert pending["indicators"] is not None
    assert pending["thresholds"] is not None
    confirmed_signals=client.get("/api/v1/etfs/510300/signals").json()
    assert all(item["date"]!=newest_date for item in confirmed_signals)

def test_ingest_and_api_use_one_active_vendor_source(client):
    with SessionLocal() as db:
        db.add(Instrument(symbol="159915",name="测试创业板ETF",exchange="SZ",category="broad"))
        db.commit()
        first=date(2026,1,1)
        rows=[DailyBar((first+timedelta(days=n)).isoformat(),1+n*.001,1.02+n*.001,.98+n*.001,1.0+n*.001,1000.,None)
              for n in range(25)]
        assert ingest(db,"159915",rows,source="tencent")==25
        recalculate(db,"159915",source="tencent")
        assert active_source(db,"159915")=="tencent"
        assert {bar.source for bar in db.query(Bar).filter_by(symbol="159915").all()}=={"tencent"}
    bars=client.get("/api/v1/etfs/159915/daily-bars").json()
    assert len(bars)==25 and bars[-1]["date"]=="2026-01-25"
