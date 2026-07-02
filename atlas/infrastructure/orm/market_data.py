"""ORM — DailyPrice / IntradayTick / InstitutionalFlow / MarginTrading / Revenue。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atlas.infrastructure.orm.base import Base


class DailyPrice(Base):
    __tablename__ = "daily_price"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "stock_id"),
        CheckConstraint("high >= low"),
        CheckConstraint("volume >= 0"),
    )

    price_id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, unique=True)
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    turnover: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntradayTick(Base):
    __tablename__ = "intraday_tick"
    __table_args__ = (
        PrimaryKeyConstraint("tick_time", "stock_id"),
        CheckConstraint("price > 0"),
        CheckConstraint("volume >= 0"),
    )

    tick_id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, unique=True)
    stock_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tick_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    bid_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ask_volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tick_type: Mapped[str | None] = mapped_column(String(1), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InstitutionalFlow(Base):
    __tablename__ = "institutional_flow"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date"),)

    flow_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    foreign_buy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    foreign_sell: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    foreign_net: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    trust_buy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    trust_sell: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    trust_net: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    dealer_buy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    dealer_sell: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    dealer_net: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_net: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MarginTrading(Base):
    __tablename__ = "margin_trading"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date"),)

    margin_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    margin_buy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    margin_sell: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    margin_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    margin_change: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    short_buy: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    short_sell: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    short_balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    short_change: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    short_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Revenue(Base):
    __tablename__ = "revenue"
    __table_args__ = (
        UniqueConstraint("stock_id", "report_year", "report_month"),
        CheckConstraint("report_month BETWEEN 1 AND 12"),
    )

    revenue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    report_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    report_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    revenue_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mom_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    yoy_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    cumulative_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
