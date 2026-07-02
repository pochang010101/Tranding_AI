"""ORM — Market / Industry / Stock。"""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atlas.infrastructure.orm.base import Base, TimestampMixin


class Market(TimestampMixin, Base):
    __tablename__ = "market"

    market_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, server_default="Asia/Taipei")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="TWD")
    open_time: Mapped[time] = mapped_column(Time, nullable=False, server_default="09:00")
    close_time: Mapped[time] = mapped_column(Time, nullable=False, server_default="13:30")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    stocks: Mapped[list[Stock]] = relationship(back_populates="market")
    industries: Mapped[list[Industry]] = relationship(back_populates="market")


class Industry(TimestampMixin, Base):
    __tablename__ = "industry"
    __table_args__ = (UniqueConstraint("market_id", "code"),)

    industry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    market: Mapped[Market] = relationship(back_populates="industries")
    stocks: Mapped[list[Stock]] = relationship(back_populates="industry")


class Stock(TimestampMixin, Base):
    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("market_id", "symbol"),)

    stock_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    industry_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("industry.industry_id"), nullable=True)
    listing_type: Mapped[str] = mapped_column(String(10), nullable=False)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_disposal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_full_cash: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    market: Mapped[Market] = relationship(back_populates="stocks")
    industry: Mapped[Industry | None] = relationship(back_populates="stocks")
