"""Deterministic FastAPI server used by the browser E2E suite.

The fixture replaces only the external market-data boundary. The HTTP routes,
SQLite persistence, refresh thread, indicator calculation and threshold solver
remain the production implementations.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DATA_DIR = Path(os.environ.get("E2E_DATA_DIR", str(ROOT / "frontend" / ".e2e-data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# This directory is owned by the test harness. Remove only its SQLite files so
# a stale browser run cannot leak watchlist rows into the next run.
for suffix in ("etf.db", "etf.db-wal", "etf.db-shm"):
    (DATA_DIR / suffix).unlink(missing_ok=True)

os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{DATA_DIR / 'etf.db'}"
os.environ["MARKET_DATA_PROVIDER"] = "akshare"
os.environ["MARKET_CHECK_COOLDOWN_SECONDS"] = "1"
os.environ["MARKET_REQUEST_TIMEOUT_SECONDS"] = "1"
sys.path.insert(0, str(BACKEND))

subprocess.run(
    [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
    cwd=BACKEND,
    check=True,
)

from sqlalchemy import select  # noqa: E402
import uvicorn  # noqa: E402

from app import main, models, service  # noqa: E402
from app.provider import DailyBar  # noqa: E402


CATALOGUE = {
    "510300": {
        "name": "华泰柏瑞沪深300ETF",
        "full_name": "华泰柏瑞沪深300交易型开放式指数证券投资基金",
        "market_name": "沪深300ETF华泰柏瑞",
        "exchange": "SH",
        "base": 4.0,
        "volume": 45_000_000,
    },
    "159915": {
        "name": "易方达创业板ETF",
        "full_name": "易方达创业板交易型开放式指数证券投资基金",
        "market_name": "创业板ETF易方达",
        "exchange": "SZ",
        "base": 2.2,
        "volume": 68_000_000,
    },
    "159307": {
        "name": "博时中证红利低波100ETF",
        "full_name": "博时中证红利低波动100交易型开放式指数证券投资基金",
        "market_name": "红利低波100ETF博时",
        "exchange": "SZ",
        "base": 1.05,
        "volume": 1_100_000,
    },
}


def _trading_days() -> list[date]:
    end = date.today() - timedelta(days=1)
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    days: list[date] = []
    cursor = end - timedelta(days=220)
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days[-160:]


TRADING_DAYS = _trading_days()


class FixtureProvider:
    """Stable catalogue and OHLCV values for browser-level acceptance tests."""

    name = "e2e_fixture"

    @classmethod
    def catalogue_status(cls):
        return {"source": "E2E_FIXTURE", "warning": None}

    def __init__(self):
        self.last_source = self.name

    def get_instruments(self, text: str = "", limit: int = 1000):
        keyword = text.strip().lower()
        rows = []
        for symbol, item in CATALOGUE.items():
            if not keyword or any(keyword in str(item[key]).lower() for key in ("name", "full_name", "market_name")) or keyword in symbol:
                rows.append({
                    "symbol": symbol,
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "market_name": item["market_name"],
                    "exchange": item["exchange"],
                    "source": "E2E_FIXTURE",
                })
        rows.sort(key=lambda row: (row["symbol"] != text.strip(), row["symbol"]))
        return rows[:limit]

    def get_daily_bars(self, symbol: str, start: date, end: date, adjustment: str = "RAW"):
        if adjustment != "RAW":
            raise ValueError("E2E fixture only supports RAW")
        item = CATALOGUE[symbol]
        bars = []
        for index, day in enumerate(TRADING_DAYS):
            if not start <= day <= end:
                continue
            # The small deterministic oscillation yields non-flat RSI/BOLL
            # values while retaining valid OHLC ranges for every symbol.
            close = item["base"] * (1 + 0.018 * math.sin(index / 4.7) + 0.004 * math.sin(index / 11.0))
            open_price = close * (1 + 0.002 * math.sin(index / 3.0))
            high = max(open_price, close) * 1.006
            low = min(open_price, close) * 0.994
            bars.append(DailyBar(
                day.isoformat(),
                round(open_price, 6),
                round(high, 6),
                round(low, 6),
                round(close, 6),
                float(item["volume"] + index * 1_000),
                float(item["volume"] * close),
            ))
        if not bars:
            raise ValueError(f"No fixture bars for {symbol}")
        self.last_source = self.name
        return bars

    def health_check(self):
        return {"status": "AVAILABLE", "provider": self.name, "package_version": "fixture"}


# Use the same production ingestion/recalculation path, but make the newest
# fixture bar explicitly pending and all prior bars confirmed. This gives the
# browser tests a real PENDING state plus a usable confirmed threshold snapshot
# without sleeping ten minutes for the repeat-observation heuristic.
_real_ingest = service.ingest


def _fixture_ingest(db, symbol, fetched, source="akshare_em", adjustment="RAW"):
    changed = _real_ingest(db, symbol, fetched, source=source, adjustment=adjustment)
    rows = db.scalars(select(models.Bar).where(
        models.Bar.symbol == symbol,
        models.Bar.source == source,
        models.Bar.adjustment == adjustment,
    ).order_by(models.Bar.date)).all()
    for row in rows[:-1]:
        row.data_status = "CONFIRMED"
        row.stable_observations = max(row.stable_observations, 2)
    if rows:
        rows[-1].data_status = "PENDING"
    db.commit()
    return changed


service.ingest = _fixture_ingest
service.set_provider_factory(FixtureProvider)
main.AKShareProvider = FixtureProvider
main.build_provider = lambda: FixtureProvider()


if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("E2E_BACKEND_PORT", "8000")), log_level="warning")
