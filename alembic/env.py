"""Alembic migration 環境設定。"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 從環境變數讀取 DB URL，覆蓋 alembic.ini 的 placeholder
db_url = os.getenv("ATLAS_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

import atlas.infrastructure.orm  # noqa: F401, E402 — register all models
from atlas.infrastructure.orm.base import Base  # noqa: E402
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以 'offline' 模式執行 migration（產生 SQL 而不實際連線）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以 'online' 模式執行 migration（直接連線資料庫）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
