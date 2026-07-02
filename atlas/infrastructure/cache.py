"""Redis 快取 — 提供統一的快取存取介面。"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

import redis.asyncio as aioredis

from atlas.config import RedisConfig
from atlas.exceptions import CacheError
from atlas.interfaces.infrastructure import ICacheService

logger = logging.getLogger(__name__)

_KEY_PREFIX = "atlas:"


class CacheManager(ICacheService):
    """Redis 快取管理器。

    所有 key 自動加上 ``atlas:`` 前綴做 namespace 隔離。
    值以 JSON 序列化/反序列化。
    """

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._client: aioredis.Redis = aioredis.Redis(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password or None,
            decode_responses=True,
        )
        self._initialized = False

    # ── helpers ──────────────────────────────────

    def _prefixed(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize(raw: str | None) -> Any | None:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    # ── lifecycle ────────────────────────────────

    async def initialize(self) -> None:
        """驗證 Redis 連線。"""
        try:
            await self._client.ping()
            self._initialized = True
            logger.info("CacheManager initialized — Redis connected")
        except Exception as exc:
            logger.error("CacheManager initialization failed: %s", exc)
            raise CacheError(f"Cannot connect to Redis: {exc}") from exc

    async def close(self) -> None:
        """關閉連線。"""
        await self._client.aclose()
        self._initialized = False
        logger.info("CacheManager closed")

    # ── CRUD ─────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        """取得快取值（自動 JSON 反序列化）。"""
        try:
            raw = await self._client.get(self._prefixed(key))
            return self._deserialize(raw)
        except Exception as exc:
            logger.warning("Cache GET failed for key=%s: %s", key, exc)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """寫入快取值（自動 JSON 序列化）。"""
        try:
            serialized = self._serialize(value)
            if ttl_seconds is not None:
                await self._client.setex(
                    self._prefixed(key), ttl_seconds, serialized
                )
            else:
                await self._client.set(self._prefixed(key), serialized)
        except Exception as exc:
            logger.warning("Cache SET failed for key=%s: %s", key, exc)

    async def delete(self, key: str) -> None:
        """刪除快取。"""
        try:
            await self._client.delete(self._prefixed(key))
        except Exception as exc:
            logger.warning("Cache DELETE failed for key=%s: %s", key, exc)

    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在。"""
        try:
            return bool(await self._client.exists(self._prefixed(key)))
        except Exception as exc:
            logger.warning("Cache EXISTS failed for key=%s: %s", key, exc)
            return False

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl_seconds: int | None = None,
    ) -> Any:
        """Cache-aside pattern: miss 時呼叫 factory 計算並寫入。"""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory()
        await self.set(key, value, ttl_seconds)
        return value

    # ── health ───────────────────────────────────

    async def health_check(self) -> bool:
        """Redis 健康檢查。"""
        try:
            return await self._client.ping()
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)
            return False

    # ── pattern ops ──────────────────────────────

    async def flush_pattern(self, pattern: str) -> int:
        """刪除符合 pattern 的所有 key（自動加前綴）。

        Returns:
            刪除的 key 數量
        """
        full_pattern = self._prefixed(pattern)
        deleted = 0
        try:
            async for key in self._client.scan_iter(match=full_pattern):
                await self._client.delete(key)
                deleted += 1
        except Exception as exc:
            logger.warning(
                "Cache flush_pattern failed for pattern=%s: %s", pattern, exc
            )
        return deleted
