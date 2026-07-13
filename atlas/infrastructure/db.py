"""PostgreSQL 連線管理 — 提供資料庫連線池與 session 管理。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from atlas.exceptions import DatabaseError

if TYPE_CHECKING:
    from sqlalchemy.engine import Result

    from atlas.config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseManager:
    """PostgreSQL 連線管理器，封裝 SQLAlchemy async engine + session。

    使用 asyncpg 驅動，提供連線池、session context manager、
    原始 SQL 執行與健康檢查。
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        # postgresql:// → postgresql+asyncpg://
        async_url = config.url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
        self._engine: AsyncEngine = create_async_engine(
            async_url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,
            echo=False,
        )
        self._session_factory = sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False

    # ── lifecycle ────────────────────────────────

    async def initialize(self) -> None:
        """初始化連線池，驗證可連線。"""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._initialized = True
            logger.info("DatabaseManager initialized — pool connected")
        except Exception as exc:
            logger.error("DatabaseManager initialization failed: %s", exc)
            raise DatabaseError(f"Cannot connect to PostgreSQL: {exc}") from exc

    async def close(self) -> None:
        """關閉連線池。"""
        await self._engine.dispose()
        self._initialized = False
        logger.info("DatabaseManager closed")

    # ── session ──────────────────────────────────

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """取得 DB session（async context manager）。

        自動 commit；例外時 rollback。
        """
        async_session: AsyncSession = self._session_factory()
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise
        finally:
            await async_session.close()

    # ── raw SQL ──────────────────────────────────

    async def execute(
        self,
        statement: str,
        params: dict[str, Any] | None = None,
    ) -> Result:
        """執行原始 SQL。

        Args:
            statement: SQL 字串（使用 :param 參數化查詢）
            params: 參數字典

        Returns:
            SQLAlchemy Result 物件
        """
        try:
            async with self.session() as sess:
                result = await sess.execute(text(statement), params or {})
                return result
        except DatabaseError:
            raise
        except Exception as exc:
            logger.error("SQL execution failed: %s", exc)
            raise DatabaseError(f"SQL execution failed: {exc}") from exc

    # ── health ───────────────────────────────────

    async def health_check(self) -> bool:
        """檢查資料庫連線是否正常。"""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("Database health check failed: %s", exc)
            return False

    # ── property ─────────────────────────────────

    @property
    def engine(self) -> AsyncEngine:
        """取得 SQLAlchemy engine。"""
        return self._engine
