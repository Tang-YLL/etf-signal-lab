"""AKShare interface wrapper. Market data are external and may fail or revise."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from math import isfinite
import re
import threading
import time

@dataclass(frozen=True)
class DailyBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None

class DataError(RuntimeError):
    pass

class AKShareProvider:
    name = "akshare_em"
    # Class-wide cache limits network calls from multiple browser tabs.
    _catalogue_lock = threading.Lock()
    _catalogue_cache = None
    _catalogue_expires = 0.0
    _em_retry_after = 0.0

    def get_instruments(self, text: str = ""):
        import akshare as ak
        cls = type(self)
        with cls._catalogue_lock:
            now = time.monotonic()
            if cls._catalogue_cache is not None and now < cls._catalogue_expires:
                entries = cls._catalogue_cache
            else:
                entries = None
                if now >= cls._em_retry_after:
                    try:
                        entries = self._parse_catalogue(ak.fund_etf_spot_em(), "AKSHARE_EM")
                    except Exception:
                        # Eastmoney may return HTTP 502 or temporary rate limits.
                        # Avoid repeatedly hitting a failing upstream endpoint.
                        cls._em_retry_after = now + 1800
                if entries is None:
                    try:
                        entries = self._parse_catalogue(ak.fund_etf_category_sina(symbol="ETF基金"), "AKSHARE_SINA")
                    except Exception as exc:
                        if cls._catalogue_cache is not None:
                            entries = [{**r, "source": "STALE_CATALOGUE"} for r in cls._catalogue_cache]
                        else:
                            raise DataError("Both ETF catalogue sources unavailable: " + type(exc).__name__) from exc
                cls._catalogue_cache = entries
                cls._catalogue_expires = now + (1800 if entries else 300)
        keyword=text.lower().strip()
        return [r for r in entries if keyword in r["symbol"] or keyword in r["name"].lower()][:80]

    @staticmethod
    def _parse_catalogue(df, source: str):
        if df is None or df.empty:
            raise DataError("Empty ETF catalogue")
        if not {"代码", "名称"}.issubset(df.columns):
            raise DataError("ETF catalogue schema changed")
        entries=[]
        seen=set()
        for _,row in df.iterrows():
            raw=str(row["代码"]).strip()
            match=re.fullmatch(r"(?:(sh|sz))?(\\d{6})",raw,flags=re.IGNORECASE)
            if not match:
                continue
            market,code=match.groups()
            if code in seen:
                continue
            name=str(row["名称"]).strip()
            if not name or name.lower() in ("nan","none"):
                continue
            seen.add(code)
            entries.append({
                "symbol": code,
                "name": name,
                "exchange": market.upper() if market else exchange(code),
                "source": source
            })
        if not entries:
            raise DataError("Catalogue contains no valid ETF symbols")
        return entries

    def get_daily_bars(self, symbol: str, start: date, end: date, adjustment: str = "RAW"):
        if adjustment!="RAW": raise DataError("Only RAW is validated for this version")
        if not re.fullmatch(r"\d{6}",symbol): raise DataError("Invalid 6-digit symbol")
        import akshare as ak
        df = ak.fund_etf_hist_em(symbol=symbol,period="daily",start_date=start.strftime("%Y%m%d"),end_date=end.strftime("%Y%m%d"),adjust="")
        if df is None or df.empty: raise DataError("Empty ETF history response")
        required={"日期","开盘","最高","最低","收盘","成交量"}
        if not required.issubset(df.columns):raise DataError("ETF history schema changed: "+str(sorted(required-set(df.columns))))
        result={}
        for _,row in df.iterrows():
            try:
                day=date.fromisoformat(str(row["日期"])[:10])
                o,h,l,c,v=(float(row[x]) for x in ("开盘","最高","最低","收盘","成交量"))
                amount=float(row["成交额"]) if "成交额" in df.columns else None
            except (TypeError,ValueError,KeyError) as exc:
                raise DataError("Malformed ETF OHLCV record") from exc
            if not all(isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or h < max(o,c,l) or l>min(o,c,h):
                raise DataError(f"Invalid ETF OHLCV {day}")
            if amount is not None and (not isfinite(amount) or amount<0):raise DataError("Invalid turnover")
            if start<=day<=end:
                item=DailyBar(day.isoformat(),o,h,l,c,v,amount)
                previous=result.get(item.date)
                if previous is not None and previous!=item:
                    raise DataError("Conflicting OHLCV rows for "+item.date)
                result[item.date]=item
        if not result:raise DataError("No bars in requested date range")
        return [result[k] for k in sorted(result)]

    def get_latest_available_date(self, symbol: str):
        # The latest *available* bar is not necessarily the latest *confirmed* close.
        end=datetime.now(ZoneInfo("Asia/Shanghai")).date()
        start=end-timedelta(days=40)
        bars=self.get_daily_bars(symbol,start,end,"RAW")
        return date.fromisoformat(bars[-1].date)

    def get_trading_calendar(self):
        # Never assume unavailable calendar provides a reliable confirmed status.
        import akshare as ak
        # AKShare 1.20.45 renamed tool_trade_date_hist_sina.
        fn=getattr(ak,"calendar_trade_date_hist_sina",None)
        if fn is None:fn=getattr(ak,"tool_trade_date_hist_sina",None)
        if fn is None:raise DataError("Trading calendar API not available in installed AKShare")
        df=fn()
        if df is None or df.empty or "trade_date" not in df.columns:
            raise DataError("Calendar unavailable or schema changed")
        return [str(d)[:10] for d in df["trade_date"]]

    def health_check(self):
        try:
            import akshare
            return {"status":"AVAILABLE_UNTESTED", "package_version":getattr(akshare,"__version__","unknown")}
        except Exception as exc:
            return {"status":"UNAVAILABLE", "reason":str(exc)[:140]}

def exchange(symbol: str) -> str:
    # This is a display hint only; not a classification of ETF type.
    return "SH" if symbol.startswith(("5","6")) else "SZ"
