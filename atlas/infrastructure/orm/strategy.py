"""ORM — Strategy / ScanResult / Signal / Conclusion / MarketRegime / DetectorAlert。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atlas.infrastructure.orm.base import Base, TimestampMixin


class Strategy(TimestampMixin, Base):
    __tablename__ = "strategy"

    strategy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_params: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class ScanResult(Base):
    __tablename__ = "scan_result"

    scan_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("strategy.strategy_id"), nullable=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    axis_industry: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    axis_catalyst: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    axis_fund_flow: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    axis_rs: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    axis_total: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    tech_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fund_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    chip_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    positive_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    aux_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    aux_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)
    exclude_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Signal(Base):
    __tablename__ = "signal"

    signal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("strategy.strategy_id"), nullable=True)
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    signal_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    price_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Conclusion(Base):
    __tablename__ = "conclusion"
    __table_args__ = (UniqueConstraint("stock_id", "eval_date"),)

    conclusion_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    eval_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    regime_downgrade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    sentiment_downgrade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    industry_downgrade: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    adjusted_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    downgrade_reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    module_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    layer_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    consensus_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarketRegimeORM(Base):
    __tablename__ = "market_regime"
    __table_args__ = (UniqueConstraint("market_id", "eval_date"),)

    regime_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=False)
    eval_date: Mapped[date] = mapped_column(Date, nullable=False)
    regime: Mapped[str] = mapped_column(String(10), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    advance_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decline_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    above_ma20_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    above_ma60_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    above_ma200_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    new_high_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_low_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breadth_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    intl_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gap_prediction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gap_actual: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DetectorAlert(Base):
    __tablename__ = "detector_alert"

    alert_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    detector_type: Mapped[str] = mapped_column(String(30), nullable=False)
    alert_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, server_default="INFO")
    price_at_alert: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    volume_at_alert: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
