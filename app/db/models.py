"""SQLAlchemy ORM models — mirror sql/001_schema.sql."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric,
    String, Text, Float, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username:         Mapped[str | None] = mapped_column(Text)
    capital:          Mapped[float] = mapped_column(Numeric(14, 2), default=500_000, nullable=False)
    risk_pct:         Mapped[float] = mapped_column(Numeric(4, 2), default=1.0, nullable=False)
    trade_style:      Mapped[str]   = mapped_column(Text, default="All", nullable=False)
    risk_profile:     Mapped[str]   = mapped_column(Text, default="Moderate", nullable=False)
    alerts_on:        Mapped[bool]  = mapped_column(Boolean, default=True, nullable=False)
    watchlist:        Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MarketData(Base):
    __tablename__ = "market_data"
    ts:         Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument: Mapped[str] = mapped_column(Text, primary_key=True)
    timeframe:  Mapped[str] = mapped_column(Text, primary_key=True)
    open:       Mapped[float] = mapped_column(Float, nullable=False)
    high:       Mapped[float] = mapped_column(Float, nullable=False)
    low:        Mapped[float] = mapped_column(Float, nullable=False)
    close:      Mapped[float] = mapped_column(Float, nullable=False)
    volume:     Mapped[int]   = mapped_column(BigInteger, default=0, nullable=False)


class OptionsChainRow(Base):
    __tablename__ = "options_chain"
    ts:          Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument:  Mapped[str]  = mapped_column(Text, primary_key=True)
    expiry:      Mapped[date] = mapped_column(Date, primary_key=True)
    strike:      Mapped[float] = mapped_column(Numeric(12, 2), primary_key=True)
    option_type: Mapped[str]  = mapped_column(String(2), primary_key=True)
    ltp:   Mapped[float | None] = mapped_column(Float)
    bid:   Mapped[float | None] = mapped_column(Float)
    ask:   Mapped[float | None] = mapped_column(Float)
    iv:    Mapped[float | None] = mapped_column(Float)
    oi:    Mapped[int   | None] = mapped_column(BigInteger)
    oi_change: Mapped[int | None] = mapped_column(BigInteger)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    delta: Mapped[float | None] = mapped_column(Float)
    gamma: Mapped[float | None] = mapped_column(Float)
    theta: Mapped[float | None] = mapped_column(Float)
    vega:  Mapped[float | None] = mapped_column(Float)


class IVHistory(Base):
    __tablename__ = "iv_history"
    instrument:     Mapped[str]  = mapped_column(Text, primary_key=True)
    date:           Mapped[date] = mapped_column(Date, primary_key=True)
    iv_close:       Mapped[float] = mapped_column(Float, nullable=False)
    atm_strike:     Mapped[float | None] = mapped_column(Numeric(12, 2))
    spot_close:     Mapped[float | None] = mapped_column(Float)
    days_to_expiry: Mapped[int   | None] = mapped_column(Integer)
    vix_close:      Mapped[float | None] = mapped_column(Float)
    pcr_oi:         Mapped[float | None] = mapped_column(Float)
    max_pain:       Mapped[float | None] = mapped_column(Numeric(12, 2))


class NewsItem(Base):
    __tablename__ = "news_log"
    id:          Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts:          Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    instrument:  Mapped[str | None] = mapped_column(Text)
    headline:    Mapped[str] = mapped_column(Text, nullable=False)
    source:      Mapped[str | None] = mapped_column(Text)
    url:         Mapped[str | None] = mapped_column(Text)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    impact:      Mapped[str | None] = mapped_column(Text)
    raw:         Mapped[dict | None] = mapped_column(JSONB)


class FeaturesLog(Base):
    __tablename__ = "features_log"
    ts:         Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    instrument: Mapped[str] = mapped_column(Text, primary_key=True)
    timeframe:  Mapped[str] = mapped_column(Text, primary_key=True)
    features:   Mapped[dict] = mapped_column(JSONB, nullable=False)


class TradeSignal(Base):
    __tablename__ = "trade_signals"
    signal_id:       Mapped[str] = mapped_column(Text, primary_key=True)
    ts:              Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.telegram_chat_id"))
    instrument:      Mapped[str] = mapped_column(Text, nullable=False)
    spot_price:      Mapped[float | None] = mapped_column(Float)
    trade_type:      Mapped[str | None] = mapped_column(Text)
    direction:       Mapped[str | None] = mapped_column(Text)
    fcs_score:       Mapped[float | None] = mapped_column(Float)
    confidence_pct:  Mapped[float | None] = mapped_column(Float)
    entry_price:     Mapped[float | None] = mapped_column(Float)
    stop_loss:       Mapped[float | None] = mapped_column(Float)
    target_1:        Mapped[float | None] = mapped_column(Float)
    target_2:        Mapped[float | None] = mapped_column(Float)
    risk_reward:     Mapped[float | None] = mapped_column(Float)
    session:         Mapped[str | None] = mapped_column(Text)
    market_regime:   Mapped[str | None] = mapped_column(Text)
    trend_group_score:    Mapped[float | None] = mapped_column(Float)
    momentum_group_score: Mapped[float | None] = mapped_column(Float)
    volume_group_score:   Mapped[float | None] = mapped_column(Float)
    volatility_state:     Mapped[str   | None] = mapped_column(Text)
    structure_group_score: Mapped[float | None] = mapped_column(Float)
    mtfs_score:        Mapped[float | None] = mapped_column(Float)
    pattern_detected:  Mapped[str | None] = mapped_column(Text)
    pattern_confidence: Mapped[str | None] = mapped_column(Text)
    iv_rank:           Mapped[float | None] = mapped_column(Float)
    iv_percentile:     Mapped[float | None] = mapped_column(Float)
    pcr:               Mapped[float | None] = mapped_column(Float)
    news_sentiment_score: Mapped[float | None] = mapped_column(Float)
    macro_event_flag:  Mapped[bool | None] = mapped_column(Boolean)
    vix_level:         Mapped[float | None] = mapped_column(Float)
    raw_context:       Mapped[dict | None] = mapped_column(JSONB)

    outcome: Mapped["TradeOutcome | None"] = relationship(
        "TradeOutcome", back_populates="signal", uselist=False, cascade="all, delete-orphan"
    )


class TradeOutcome(Base):
    __tablename__ = "trade_outcomes"
    signal_id:            Mapped[str] = mapped_column(Text, ForeignKey("trade_signals.signal_id", ondelete="CASCADE"), primary_key=True)
    outcome_label:        Mapped[str | None] = mapped_column(Text)
    exit_price:           Mapped[float | None] = mapped_column(Float)
    exit_ts:              Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_pnl_pts:       Mapped[float | None] = mapped_column(Float)
    actual_pnl_rs:        Mapped[float | None] = mapped_column(Float)
    max_adverse_excursion: Mapped[float | None] = mapped_column(Float)
    t1_hit: Mapped[bool | None] = mapped_column(Boolean)
    t2_hit: Mapped[bool | None] = mapped_column(Boolean)
    sl_hit: Mapped[bool | None] = mapped_column(Boolean)
    holding_period_hrs: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    signal: Mapped[TradeSignal] = relationship("TradeSignal", back_populates="outcome")


class LearningWeights(Base):
    __tablename__ = "learning_weights"
    version_id:       Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    weights:          Mapped[dict] = mapped_column(JSONB, nullable=False)
    sample_size:      Mapped[int | None] = mapped_column(Integer)
    holdout_win_rate: Mapped[float | None] = mapped_column(Float)
    active:           Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes:            Mapped[str | None] = mapped_column(Text)


class MarketContext(Base):
    __tablename__ = "market_context"
    date:       Mapped[date] = mapped_column(Date, primary_key=True)
    payload:    Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AlertLog(Base):
    __tablename__ = "alerts_log"
    id:               Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts:               Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    alert_type:       Mapped[str] = mapped_column(Text, nullable=False)
    instrument:       Mapped[str | None] = mapped_column(Text)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    payload:          Mapped[dict | None] = mapped_column(JSONB)
