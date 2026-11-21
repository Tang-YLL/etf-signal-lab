from datetime import date
from types import SimpleNamespace
import pytest
from app.provider import AKShareProvider, DataError, DailyBar, FallbackProvider, TencentProvider

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
            {"代码":"sh510300","名称":"沪深300ETF","基金全称":"华泰柏瑞沪深300交易型指数证券投资基金","场内简称":"沪深300ETF"},
            {"代码":"sz159915","名称":"创业板ETF","基金全称":"易方达创业板交易型开放式指数证券投资基金","场内简称":"创业板ETF"}])
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
    assert one[0]["full_name"].startswith("华泰柏瑞")
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

def test_exact_code_is_sorted_first_and_matches_all_names(monkeypatch):
    import sys,pandas as pd
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_spot_em=lambda:pd.DataFrame([
        {"代码":"159915","名称":"创业板ETF","基金全称":"易方达创业板交易型开放式指数证券投资基金","场内简称":"创业板ETF"},
        {"代码":"159307","名称":"博时中证红利低波100ETF","基金全称":"博时中证红利低波动100交易型开放式指数证券投资基金","场内简称":"红利低波100ETF博时"}])))
    monkeypatch.setattr(AKShareProvider,"_catalogue_cache",None)
    monkeypatch.setattr(AKShareProvider,"_catalogue_expires",0.0)
    monkeypatch.setattr(AKShareProvider,"_em_retry_after",0.0)
    provider=AKShareProvider()
    result=provider.get_instruments("159307")
    assert result[0]["symbol"]=="159307"
    assert result[0]["full_name"].startswith("博时中证红利低波动100")
    assert provider.get_instruments("博时中证红利低波动100")[0]["symbol"]=="159307"

def test_catalogues_are_merged_to_fill_missing_symbols(monkeypatch):
    import sys,pandas as pd
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(
        fund_etf_spot_em=lambda:pd.DataFrame([{"代码":"510300","名称":"沪深300ETF"}]),
        fund_etf_category_sina=lambda **kw:pd.DataFrame([{"代码":"sz159307","名称":"博时中证红利低波100ETF"}])))
    monkeypatch.setattr(AKShareProvider,"_catalogue_cache",None)
    monkeypatch.setattr(AKShareProvider,"_catalogue_expires",0.0)
    monkeypatch.setattr(AKShareProvider,"_em_retry_after",0.0)
    provider=AKShareProvider()
    result=provider.get_instruments("159307")
    assert result[0]["symbol"]=="159307"
    assert AKShareProvider.catalogue_status()["source"]=="AKSHARE_EM+AKSHARE_SINA"

def test_tencent_daily_bars_parse_raw_rows_without_requesting_adjusted_data():
    import json
    calls=[]
    payload=json.dumps({"code":0,"data":{"sh510300":{"day":[
        ["2026-11-19","1.0","1.1","1.2","0.9","1100"],
        ["2026-11-20","1.1","1.2","1.3","1.0","1200"]
    ]}}})
    provider=TencentProvider(transport=lambda url: calls.append(url) or payload)
    rows=provider.get_daily_bars("510300",date(2026,11,1),date(2026,11,20))
    assert [(row.date,row.open,row.high,row.low,row.close,row.volume) for row in rows]==[
        ("2026-11-19",1.0,1.2,.9,1.1,1100.0),
        ("2026-11-20",1.1,1.3,1.0,1.2,1200.0)
    ]
    assert rows[0].amount is None
    assert provider.last_source=="tencent"
    assert len(calls)==1 and "sh510300" in calls[0] and ",day," in calls[0] and calls[0].endswith(",none")

def test_tencent_rejects_adjusted_payload_for_raw_request():
    import json
    payload=json.dumps({"code":0,"data":{"sz159915":{"qfqday":[
        ["2026-11-19","1.0","1.1","1.2","0.9","1100"]
    ]}}})
    provider=TencentProvider(transport=lambda url: payload)
    with pytest.raises(DataError,match="adjusted"):
        provider.get_daily_bars("159915",date(2026,11,1),date(2026,11,20))

def test_tencent_rejects_malformed_rows():
    import json
    payload=json.dumps({"code":0,"data":{"sz159307":{"day":[["2026-11-19",1,1.1]]}}})
    provider=TencentProvider(transport=lambda url: payload)
    with pytest.raises(DataError,match="Malformed"):
        provider.get_daily_bars("159307",date(2026,11,1),date(2026,11,20))

def test_fallback_provider_uses_tencent_after_primary_failure():
    import json
    class BrokenProvider:
        name="akshare_em"
        def get_daily_bars(self,*args,**kwargs):
            raise DataError("temporary primary failure")
    payload=json.dumps({"code":0,"data":{"sh510300":{"day":[
        ["2026-11-19","1.0","1.1","1.2","0.9","1100"]
    ]}}})
    provider=FallbackProvider([BrokenProvider(),TencentProvider(transport=lambda url: payload)])
    rows=provider.get_daily_bars("510300",date(2026,11,1),date(2026,11,20))
    assert rows[0].date=="2026-11-19"
    assert provider.last_source=="tencent"
