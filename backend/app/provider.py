"""AKShare interface wrapper. Market data are external and may fail or revise."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from math import isfinite
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import COOLDOWN, REQUEST_TIMEOUT, DATA_SOURCE

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
    _catalogue_source = "UNKNOWN"
    _catalogue_warning = None

    def __init__(self):
        self.last_source = self.name

    def get_instruments(self, text: str = "", limit: int = 1000):
        import akshare as ak
        cls = type(self)
        keyword = text.lower().strip()
        limit = max(1, min(limit, 1000))
        with cls._catalogue_lock:
            now = time.monotonic()
            cache_has_exact = cls._catalogue_cache is not None and any(
                row["symbol"] == keyword for row in cls._catalogue_cache
            )
            cache_valid = cls._catalogue_cache is not None and now < cls._catalogue_expires
            if cache_valid and not (re.fullmatch(r"\d{6}", keyword) and not cache_has_exact
                                    and cls._catalogue_source == "STALE_CATALOGUE"):
                entries = cls._catalogue_cache
            else:
                primary = None
                secondary = None
                warnings = []
                if now >= cls._em_retry_after:
                    try:
                        primary = self._parse_catalogue(ak.fund_etf_spot_em(), "AKSHARE_EM")
                    except Exception as exc:
                        # Eastmoney may return HTTP 502 or temporary rate limits.
                        # Avoid repeatedly hitting a failing upstream endpoint.
                        cls._em_retry_after = now + 1800
                        warnings.append(f"AKSHARE_EM:{type(exc).__name__}")
                try:
                    secondary = self._parse_catalogue(ak.fund_etf_category_sina(symbol="ETF基金"), "AKSHARE_SINA")
                except Exception as exc:
                    warnings.append(f"AKSHARE_SINA:{type(exc).__name__}")

                if primary is None and secondary is None:
                    if cls._catalogue_cache is not None:
                        entries = [{**r, "source": "STALE_CATALOGUE"} for r in cls._catalogue_cache]
                        cls._catalogue_source = "STALE_CATALOGUE"
                        cls._catalogue_warning = "CATALOGUE_UNAVAILABLE:" + ",".join(warnings)
                    else:
                        raise DataError("Both ETF catalogue sources unavailable: " + ",".join(warnings))
                else:
                    merged = {row["symbol"]: dict(row) for row in (secondary or [])}
                    for row in (primary or []):
                        existing = merged.get(row["symbol"], {})
                        merged[row["symbol"]] = {**existing, **row}
                        for key in ("name", "full_name", "market_name"):
                            if not merged[row["symbol"]].get(key) and existing.get(key):
                                merged[row["symbol"]][key] = existing[key]
                    entries = list(merged.values())
                    cls._catalogue_source = "AKSHARE_EM+AKSHARE_SINA" if primary and secondary else (
                        "AKSHARE_EM" if primary else "AKSHARE_SINA")
                    cls._catalogue_warning = ",".join(warnings) or None
                cls._catalogue_cache = entries
                cls._catalogue_expires = now + (1800 if entries else 300)
        matches = [r for r in entries if not keyword or keyword in r["symbol"] or keyword in r["name"].lower()
                   or keyword in (r.get("full_name") or "").lower()
                   or keyword in (r.get("market_name") or "").lower()]
        matches.sort(key=lambda row: (row["symbol"] != keyword, row["symbol"]))
        return matches[:limit]

    @classmethod
    def catalogue_status(cls):
        return {"source": cls._catalogue_source, "warning": cls._catalogue_warning}

    @staticmethod
    def _parse_catalogue(df, source: str):
        if df is None or df.empty:
            raise DataError("Empty ETF catalogue")
        if "代码" not in df.columns:
            raise DataError("ETF catalogue schema changed")
        entries=[]
        seen=set()
        for _,row in df.iterrows():
            raw=str(row["代码"]).strip()
            match=re.fullmatch(r"(?:(sh|sz))?(\d{6})",raw,flags=re.IGNORECASE)
            if not match:
                continue
            market,code=match.groups()
            if code in seen:
                continue
            def value(*columns):
                for column in columns:
                    if column in df.columns:
                        candidate = str(row[column]).strip()
                        if candidate and candidate.lower() not in ("nan", "none"):
                            return candidate
                return None

            name=value("基金简称", "名称", "简称")
            full_name=value("基金全称", "基金名称", "全称")
            market_name=value("场内简称", "证券简称", "市场简称")
            if not name or name.lower() in ("nan","none"):
                continue
            seen.add(code)
            entries.append({
                "symbol": code,
                "name": name,
                "full_name": full_name,
                "market_name": market_name,
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
        self.last_source = self.name
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


def _decode_tencent_payload(payload):
    """Decode Tencent's JSON/JSONP response without depending on a callback name."""
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            text = payload.decode("gb18030", errors="replace")
    else:
        text = str(payload)
    text = text.strip()
    if "=" in text and not text.startswith("{"):
        text = text.split("=", 1)[1].strip()
        if text.endswith(";"):
            text = text[:-1].strip()
    elif text.endswith(")") and "(" in text and not text.startswith("{"):
        text = text[text.find("(") + 1:-1].strip()
    try:
        value = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise DataError("Tencent response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise DataError("Tencent response has invalid top-level schema")
    code = value.get("code")
    if code not in (None, 0, "0"):
        raise DataError(f"Tencent response returned code {code}")
    return value


class TencentProvider:
    """Tencent Finance historical ETF adapter."""

    name = "tencent"
    endpoint = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self, transport=None, timeout: float | None = None):
        self.timeout = REQUEST_TIMEOUT if timeout is None else timeout
        self._transport = transport or (lambda url: self._request(url, self.timeout))
        self.last_source = self.name

    @staticmethod
    def _request(url: str, timeout: float):
        request = Request(url, headers={
            "User-Agent": "Mozilla/5.0 ETF-Signal-Lab/0.1",
            "Referer": "https://finance.qq.com/",
        })
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DataError(f"Tencent request failed: {type(exc).__name__}") from exc

    def get_daily_bars(self, symbol: str, start: date, end: date, adjustment: str = "RAW"):
        if adjustment != "RAW":
            raise DataError("Only RAW is validated for this version")
        if not re.fullmatch(r"\d{6}", symbol):
            raise DataError("Invalid 6-digit symbol")
        if start > end:
            raise DataError("Invalid date range")
        market_symbol = exchange(symbol).lower() + symbol
        param = ",".join((market_symbol, "day", start.isoformat(), end.isoformat(), "1000", "none"))
        url = f"{self.endpoint}?param={quote(param, safe=',')}"
        payload = self._transport(url)
        data = _decode_tencent_payload(payload).get("data")
        node = data.get(market_symbol) if isinstance(data, dict) else None
        if not isinstance(node, dict):
            raise DataError("Tencent response has no requested ETF")
        rows = node.get("day")
        if not rows:
            if node.get("qfqday") or node.get("hfqday"):
                raise DataError("Tencent returned adjusted data for RAW request")
            raise DataError("Empty Tencent ETF history response")
        result = {}
        for raw in rows:
            if not isinstance(raw, (list, tuple)) or len(raw) < 6:
                raise DataError("Malformed Tencent OHLCV record")
            try:
                day = date.fromisoformat(str(raw[0])[:10])
                # Tencent daily rows are [date, open, close, high, low, volume].
                o, c, h, l, v = (float(raw[index]) for index in (1, 2, 3, 4, 5))
            except (TypeError, ValueError, IndexError) as exc:
                raise DataError("Malformed Tencent OHLCV record") from exc
            if not all(isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0 or v < 0:
                raise DataError(f"Invalid Tencent ETF OHLCV {day}")
            if h < max(o, c, l) or l > min(o, c, h):
                raise DataError(f"Invalid Tencent ETF OHLCV {day}")
            if start <= day <= end:
                item = DailyBar(day.isoformat(), o, h, l, c, v, None)
                previous = result.get(item.date)
                if previous is not None and previous != item:
                    raise DataError("Conflicting Tencent OHLCV rows for " + item.date)
                result[item.date] = item
        if not result:
            raise DataError("No Tencent bars in requested date range")
        self.last_source = self.name
        return [result[key] for key in sorted(result)]

    def get_latest_available_date(self, symbol: str):
        end = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        bars = self.get_daily_bars(symbol, end - timedelta(days=40), end, "RAW")
        return date.fromisoformat(bars[-1].date)

    def health_check(self):
        return {"status": "AVAILABLE_UNTESTED", "provider": self.name}


class FallbackProvider:
    """Try providers in order and expose the source that actually succeeded."""

    name = "fallback"
    _retry_after = {}
    _retry_lock = threading.Lock()

    def __init__(self, providers=None):
        self.providers = list(providers or (AKShareProvider(), TencentProvider()))
        self.last_source = None

    def get_daily_bars(self, symbol: str, start: date, end: date, adjustment: str = "RAW"):
        failures = []
        for provider in self.providers:
            provider_name = getattr(provider, "name", type(provider).__name__)
            now = time.monotonic()
            with self._retry_lock:
                retry_after = self._retry_after.get(provider_name, 0.0)
            if now < retry_after:
                failures.append(f"{provider_name}:cooldown")
                continue
            try:
                rows = provider.get_daily_bars(symbol, start, end, adjustment)
            except Exception as exc:
                failures.append(f"{provider_name}:{type(exc).__name__}")
                message = f"{type(exc).__name__}:{exc}".lower()
                if any(token in message for token in ("rate", "429", "502", "503", "timeout", "temporarily")):
                    with self._retry_lock:
                        self._retry_after[provider_name] = now + max(COOLDOWN, 60)
                continue
            if not rows:
                failures.append(f"{provider_name}:Empty")
                continue
            with self._retry_lock:
                self._retry_after.pop(provider_name, None)
            self.last_source = getattr(provider, "last_source", provider_name)
            return rows
        raise DataError("All market data providers failed: " + ",".join(failures))

    def health_check(self):
        return {
            "status": "AVAILABLE_UNTESTED",
            "provider": self.name,
            "providers": [provider.health_check() for provider in self.providers
                           if hasattr(provider, "health_check")],
        }


def configured_provider_name():
    value = str(DATA_SOURCE).strip().lower()
    if value in ("akshare", "eastmoney"):
        return AKShareProvider.name
    if value == "tencent":
        return TencentProvider.name
    if value in ("fallback", "akshare+tencent", "akshare_tencent"):
        return FallbackProvider.name
    raise DataError(f"Unsupported MARKET_DATA_PROVIDER: {DATA_SOURCE}")


def build_provider():
    value = str(DATA_SOURCE).strip().lower()
    if value in ("akshare", "eastmoney"):
        return AKShareProvider()
    if value == "tencent":
        return TencentProvider()
    if value in ("fallback", "akshare+tencent", "akshare_tencent"):
        return FallbackProvider()
    raise DataError(f"Unsupported MARKET_DATA_PROVIDER: {DATA_SOURCE}")

def exchange(symbol: str) -> str:
    # This is a display hint only; not a classification of ETF type.
    return "SH" if symbol.startswith(("5","6")) else "SZ"
