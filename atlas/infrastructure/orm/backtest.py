"""ORM — BacktestRun / BacktestTrade / MonteCarloResult / WalkForwardResult。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atlas.infrastructure.orm.base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_run"

    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategy.strategy_id"), nullable=False)
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("market.market_id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
    cost_model: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    annual_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    avg_r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    metrics_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trades: Mapped[list[BacktestTrade]] = relationship(back_populates="run", cascade="all, delete-orphan")
    monte_carlo_results: Mapped[list[MonteCarloResult]] = relationship(back_populates="run", cascade="all, delete-orphan")
    walk_forward_results: Mapped[list[WalkForwardResult]] = relationship(back_populates="run", cascade="all, delete-orphan")


class BacktestTrade(Base):
    __tablename__ = "backtest_trade"

    trade_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("backtest_run.run_id", ondelete="CASCADE"), nullable=False)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stock.stock_id"), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False, server_default="LONG")
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    entry_signal: Mapped[str | None] = mapped_column(String(30), nullable=True)
    exit_signal: Mapped[str | None] = mapped_column(String(30), nullable=True)
    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    net_pnl: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    hold_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[BacktestRun] = relationship(back_populates="trades")


class MonteCarloResult(Base):
    __tablename__ = "monte_carlo_result"

    mc_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("backtest_run.run_id", ondelete="CASCADE"), nullable=False)
    num_paths: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    pct_5th_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_25th_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_50th_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_75th_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_95th_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_5th_dd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_25th_dd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_50th_dd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_75th_dd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pct_95th_dd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    input_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    input_rr_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    input_risk_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    percentiles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    path_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[BacktestRun] = relationship(back_populates="monte_carlo_results")


class WalkForwardResult(Base):
    __tablename__ = "walk_forward_result"
    __table_args__ = (UniqueConstraint("run_id", "window_index"),)

    wf_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("backtest_run.run_id", ondelete="CASCADE"), nullable=False)
    window_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_start: Mapped[date] = mapped_column(Date, nullable=False)
    is_end: Mapped[date] = mapped_column(Date, nullable=False)
    is_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    is_sharpe: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    is_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    oos_start: Mapped[date] = mapped_column(Date, nullable=False)
    oos_end: Mapped[date] = mapped_column(Date, nullable=False)
    oos_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_sharpe: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    oos_win_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    oos_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    efficiency_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_overfit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[BacktestRun] = relationship(back_populates="walk_forward_results")
