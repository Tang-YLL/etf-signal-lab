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
