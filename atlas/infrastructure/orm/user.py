"""ORM — UserAccount / Watchlist / TradeJournal。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atlas.infrastructure.orm.base import Base, TimestampMixin


class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_account"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "tab_name", "stock_id"),)

    watchlist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_account.user_id"), nullable=False)
    tab_name: Mapped[str] = mapped_column(String(50), nullable=False, server_default="default")
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TradeJournal(TimestampMixin, Base):
    __tablename__ = "trade_journal"

    journal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_account.user_id"), nullable=False)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False, server_default="LONG")
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    r_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    net_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    entry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_used: Mapped[str | None] = mapped_column(String(30), nullable=True)
    conclusion_at_entry: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
