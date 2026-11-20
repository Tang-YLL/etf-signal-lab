from datetime import date
from types import SimpleNamespace
import pytest
from app.provider import AKShareProvider, DataError, DailyBar

def test_valid_bars(monkeypatch):
    import sys,pandas as pd
    data=pd.DataFrame([{"日期":"2026-11-19","开盘":1.0,"最高":1.2,"最低":0.9,"收盘":1.1,"成交量":1100,"成交额":900}])
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=lambda **kw:data))
    results=AKShareProvider().get_daily_bars("510300",date(2026,11,1),date(2026,11,20))
    assert len(results)==1 and results[0].close==1.1

def test_bad_schema(monkeypatch):
    import sys,pandas as pd
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=lambda **kw:pd.DataFrame([{"wrong":2}])))
    with pytest.raises(DataError):AKShareProvider().get_daily_bars("510300",date(2026,11,1),date(2026,11,20))

def test_invalid_ohlc(monkeypatch):
    import sys,pandas as pd
    data=pd.DataFrame([{"日期":"2026-11-19","开盘":1.0,"最高":.8,"最低":.9,"收盘":1.1,"成交量":1100}])
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=lambda **kw:data))
    with pytest.raises(DataError):AKShareProvider().get_daily_bars("510300",date(2026,11,1),date(2026,11,20))

def test_duplicate_conflict_is_not_silently_overwritten(monkeypatch):
    import sys,pandas as pd
    row={"日期":"2026-11-19","开盘":1.0,"最高":1.2,"最低":0.9,"收盘":1.1,"成交量":1100}
    changed=dict(row,收盘=1.09)
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=lambda **kw:pd.DataFrame([row,changed])))
    with pytest.raises(DataError,match="Conflicting OHLCV"):
        AKShareProvider().get_daily_bars("510300",date(2026,11,1),date(2026,11,20))

def test_identical_duplicate_allowed(monkeypatch):
    import sys,pandas as pd
    row={"日期":"2026-11-19","开盘":1.0,"最高":1.2,"最低":0.9,"收盘":1.1,"成交量":1100}
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=lambda **kw:pd.DataFrame([row,row])))
    assert len(AKShareProvider().get_daily_bars("510300",date(2026,11,1),date(2026,11,20)))==1

def test_new_calendar_method(monkeypatch):
    import sys,pandas as pd
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(
        calendar_trade_date_hist_sina=lambda:pd.DataFrame({"trade_date":["2026-11-19","2026-11-20"]})))
    assert AKShareProvider().get_trading_calendar()==["2026-11-19","2026-11-20"]

def test_sina_catalogue_fallback_and_cache(monkeypatch):
    import sys,pandas as pd
    calls={"em":0,"sina":0}
    def bad_em():
        calls["em"]+=1
        raise RuntimeError("502 Bad Gateway")
    def good_sina(*,symbol):
        assert symbol=="ETF基金"
        calls["sina"]+=1
        return pd.DataFrame([
            {"代码":"sh510300","名称":"沪深300ETF"},
            {"代码":"sz159915","名称":"创业板ETF"}])
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(
        fund_etf_spot_em=bad_em,fund_etf_category_sina=good_sina))
    monkeypatch.setattr(AKShareProvider,"_catalogue_cache",None)
    monkeypatch.setattr(AKShareProvider,"_catalogue_expires",0.0)
    monkeypatch.setattr(AKShareProvider,"_em_retry_after",0.0)
    p=AKShareProvider()
    one=p.get_instruments("510300")
    two=p.get_instruments("159915")
    assert one[0]["symbol"]=="510300" and one[0]["exchange"]=="SH"
    assert one[0]["source"]=="AKSHARE_SINA"
    assert two[0]["symbol"]=="159915" and two[0]["exchange"]=="SZ"
    assert calls=={"em":1,"sina":1}

def test_catalogue_invalid_raises(monkeypatch):
    import sys,pandas as pd
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(
        fund_etf_spot_em=lambda:pd.DataFrame(),
        fund_etf_category_sina=lambda **kw:pd.DataFrame()))
    monkeypatch.setattr(AKShareProvider,"_catalogue_cache",None)
    monkeypatch.setattr(AKShareProvider,"_catalogue_expires",0.0)
    monkeypatch.setattr(AKShareProvider,"_em_retry_after",0.0)
    with pytest.raises(DataError):
        AKShareProvider().get_instruments("510300")
