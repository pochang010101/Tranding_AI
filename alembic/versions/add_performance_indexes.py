"""Add performance indexes for common queries.

Revision ID: b1c2d3e4f5a6
Revises: 3aaabeb0e950
Create Date: 2026-07-02
"""

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "3aaabeb0e950"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # daily_price: time-series queries (most queried table)
    op.create_index("ix_daily_price_stock_date", "daily_price", ["stock_id", "trade_date"])
    op.create_index("ix_daily_price_trade_date", "daily_price", ["trade_date"])

    # signal: strategy lookups by time
    op.create_index("ix_signal_stock_time", "signal", ["stock_id", "signal_time"])
    op.create_index("ix_signal_time_strategy", "signal", ["signal_time", "strategy_id"])

    # backtest_trade: grouped by run
    op.create_index("ix_backtest_trade_run_id", "backtest_trade", ["run_id"])

    # scan_result: daily screener queries
    op.create_index("ix_scan_result_date", "scan_result", ["scan_date"])

    # detector_alert: radar alert timeline
    op.create_index("ix_detector_alert_time", "detector_alert", ["alert_time"])

    # notification_log: log browsing
    op.create_index("ix_notification_log_sent_at", "notification_log", ["sent_at"])

    # trade_journal: portfolio queries
    op.create_index("ix_trade_journal_stock_entry", "trade_journal", ["stock_id", "entry_date"])
    op.create_index("ix_trade_journal_is_open", "trade_journal", ["is_open"])

    # institutional_flow: daily scans
    op.create_index("ix_institutional_flow_date", "institutional_flow", ["trade_date"])

    # system_health: monitoring
    op.create_index("ix_system_health_checked_at", "system_health", ["checked_at"])


def downgrade() -> None:
    op.drop_index("ix_system_health_checked_at")
    op.drop_index("ix_institutional_flow_date")
    op.drop_index("ix_trade_journal_is_open")
    op.drop_index("ix_trade_journal_stock_entry")
    op.drop_index("ix_notification_log_sent_at")
    op.drop_index("ix_detector_alert_time")
    op.drop_index("ix_scan_result_date")
    op.drop_index("ix_backtest_trade_run_id")
    op.drop_index("ix_signal_time_strategy")
    op.drop_index("ix_signal_stock_time")
    op.drop_index("ix_daily_price_trade_date")
    op.drop_index("ix_daily_price_stock_date")
