from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, UniqueConstraint, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class Instrument(Base):
    __tablename__ = "etf_instruments"
    symbol: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    market_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exchange: Mapped[str] = mapped_column(String(2))
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rule_version: Mapped[int] = mapped_column(Integer, default=1)
    signals_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Watchlist(Base):
    __tablename__ = "watchlist"
    symbol: Mapped[str] = mapped_column(ForeignKey("etf_instruments.symbol"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Bar(Base):
    __tablename__ = "daily_bars"
    __table_args__ = (UniqueConstraint("symbol", "date", "source", "adjustment", name="uq_bar_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(6), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    source: Mapped[str] = mapped_column(String(40), default="akshare_em")
    adjustment: Mapped[str] = mapped_column(String(6), default="RAW")
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    stable_observations: Mapped[int] = mapped_column(Integer, default=1)
    data_status: Mapped[str] = mapped_column(String(20), default="PENDING")

class Revision(Base):
    __tablename__ = "daily_bar_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(6), index=True)
    date: Mapped[str] = mapped_column(String(10))
    old_json: Mapped[str] = mapped_column(Text)
    new_json: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"
    __table_args__ = (UniqueConstraint("symbol", "date", "rule_version", "data_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(6), index=True)
    date: Mapped[str] = mapped_column(String(10))
    rule_version: Mapped[int] = mapped_column(Integer)
    data_hash: Mapped[str] = mapped_column(String(64))
    rsi14: Mapped[float | None] = mapped_column(Float, nullable=True)
    ma20: Mapped[float | None] = mapped_column(Float, nullable=True)
    boll_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    boll_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal: Mapped[str] = mapped_column(String(20))
    rule_json: Mapped[str] = mapped_column(Text)

class ThresholdSnapshot(Base):
    __tablename__ = "threshold_snapshots"
    __table_args__ = (UniqueConstraint("symbol", "date", "rule_version", "data_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(6), index=True)
    date: Mapped[str] = mapped_column(String(10))
    rule_version: Mapped[int] = mapped_column(Integer)
    data_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class StrategyTemplate(Base):
    __tablename__ = "strategy_templates"
    category: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    params_json: Mapped[str] = mapped_column(Text)

class StrategyOverride(Base):
    __tablename__ = "strategy_overrides"
    symbol: Mapped[str] = mapped_column(String(6), primary_key=True)
    params_json: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)

class RefreshRun(Base):
    __tablename__ = "data_refresh_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    source: Mapped[str] = mapped_column(String(40), default="akshare_em")
    symbols_json: Mapped[str] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Setting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
