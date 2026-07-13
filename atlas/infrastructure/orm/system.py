"""ORM — NotificationLog / AuditLog / SystemHealth / DataSourceStatus / ScheduleExecution / IndustryRS。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from atlas.infrastructure.orm.base import Base, TimestampMixin


class NotificationLog(Base):
    __tablename__ = "notification_log"

    notif_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user_account.user_id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    message_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    stock_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (PrimaryKeyConstraint("action_at", "audit_id"),)

    audit_id: Mapped[int] = mapped_column(BigInteger, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SystemHealth(Base):
    __tablename__ = "system_health"

    health_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    component: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataSourceStatus(TimestampMixin, Base):
    __tablename__ = "data_source_status"

    ds_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(50), nullable=False)
    market_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNKNOWN")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    consecutive_failures: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScheduleExecution(Base):
    __tablename__ = "schedule_execution"

    exec_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(String(50), nullable=False)
    market_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IndustryRS(Base):
    __tablename__ = "industry_rs"
    __table_args__ = (UniqueConstraint("industry_id", "calc_date"),)

    rs_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("industry.industry_id"), nullable=False)
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    rs_5d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rs_20d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rs_60d: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rank_5d: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    rank_20d: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    rank_60d: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    trend: Mapped[str] = mapped_column(String(10), nullable=False, server_default="FLAT")
    fund_flow_net: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
