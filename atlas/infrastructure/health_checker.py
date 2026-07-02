"""系統健康檢查器 — 定期 heartbeat + 自動恢復機制。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

from atlas.enums import DataSourceHealth

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.db import DatabaseManager

logger = logging.getLogger(__name__)

_RECOVER_THRESHOLD = 3  # 連續成功 N 次 → HEALTHY
_DEGRADE_THRESHOLD = 1  # 連續失敗 N 次 → DEGRADED
_UNHEALTHY_THRESHOLD = 3  # 連續失敗 N 次 → UNHEALTHY


@dataclass
class ComponentHealth:
    """單一組件的健康狀態追蹤。"""

    name: str
    status: DataSourceHealth = DataSourceHealth.HEALTHY
    last_check: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    latency_ms: float | None = None


class HealthChecker:
    """系統健康檢查器。

    - 註冊多個組件的健康檢查函式
    - 並行執行檢查
    - 連續 3 次成功 → HEALTHY, 1 次失敗 → DEGRADED, 3 次失敗 → UNHEALTHY
    - 支援定期 heartbeat (asyncio.Task)
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._components: dict[str, ComponentHealth] = {}
        self._check_fns: dict[str, Callable[[], Awaitable[bool]]] = {}
        self._periodic_task: asyncio.Task[None] | None = None
        self._running = False

        if db is not None:
            self.register_component("database", db.health_check)
        if cache is not None:
            self.register_component("redis", cache.health_check)

    def register_component(
        self, name: str, check_fn: Callable[[], Awaitable[bool]]
    ) -> None:
        """註冊健康檢查組件。"""
        self._components[name] = ComponentHealth(name=name)
        self._check_fns[name] = check_fn
        logger.debug("Registered health check: %s", name)

    async def check_component(self, name: str) -> ComponentHealth:
        """檢查單一組件並更新狀態。"""
        comp = self._components.get(name)
        if comp is None or name not in self._check_fns:
            raise KeyError(f"Unknown component: {name}")

        check_fn = self._check_fns[name]
        now = datetime.now(tz=timezone.utc)
        start = time.perf_counter()

        try:
            result = await check_fn()
            elapsed = (time.perf_counter() - start) * 1000
            comp.latency_ms = round(elapsed, 2)
            comp.last_check = now

            if result:
                comp.consecutive_successes += 1
                comp.consecutive_failures = 0
                comp.last_success = now
                comp.last_error = None
                if comp.consecutive_successes >= _RECOVER_THRESHOLD:
                    comp.status = DataSourceHealth.HEALTHY
                elif comp.status == DataSourceHealth.UNHEALTHY:
                    comp.status = DataSourceHealth.DEGRADED
            else:
                self._mark_failure(comp, "check returned False")

        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            comp.latency_ms = round(elapsed, 2)
            comp.last_check = now
            self._mark_failure(comp, str(exc))

        return comp

    async def check_all(self) -> dict[str, ComponentHealth]:
        """並行檢查所有已註冊組件。

        Prometheus 整合建議：
            若需將健康狀態暴露給 Prometheus，可在此方法呼叫後
            透過 ``prometheus_client`` 更新 Gauge/Counter：

            .. code-block:: python

                from prometheus_client import Gauge

                _health_gauge = Gauge(
                    "atlas_component_healthy",
                    "1 = HEALTHY, 0 = DEGRADED/UNHEALTHY",
                    labelnames=["component"],
                )
                _latency_gauge = Gauge(
                    "atlas_component_latency_ms",
                    "Last health-check latency in milliseconds",
                    labelnames=["component"],
                )

                results = await checker.check_all()
                for name, comp in results.items():
                    _health_gauge.labels(component=name).set(
                        1 if comp.status == DataSourceHealth.HEALTHY else 0
                    )
                    if comp.latency_ms is not None:
                        _latency_gauge.labels(component=name).set(comp.latency_ms)

            接著在 Streamlit app 啟動時呼叫：
                ``prometheus_client.start_http_server(port=9091)``
            並在 ``docker/prometheus.yml`` 的 streamlit job 中指向 port 9091。
        """
        if not self._check_fns:
            return {}

        tasks = [self.check_component(name) for name in self._check_fns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("Health check gather error: %s", result)

        return dict(self._components)

    def get_status(self, name: str) -> ComponentHealth | None:
        """取得組件最新狀態。"""
        return self._components.get(name)

    def get_all_status(self) -> dict[str, ComponentHealth]:
        """取得所有組件狀態。"""
        return dict(self._components)

    def is_system_healthy(self) -> bool:
        """任一組件 UNHEALTHY → False。"""
        return all(
            c.status != DataSourceHealth.UNHEALTHY for c in self._components.values()
        )

    async def start_periodic(self, interval: int = 60) -> None:
        """啟動定期健康檢查。"""
        if self._running:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    await self.check_all()
                    unhealthy = [
                        n for n, c in self._components.items()
                        if c.status == DataSourceHealth.UNHEALTHY
                    ]
                    if unhealthy:
                        logger.warning("Unhealthy components: %s", unhealthy)
                except Exception:
                    logger.error("Periodic health check error", exc_info=True)
                await asyncio.sleep(interval)

        self._periodic_task = asyncio.create_task(_loop())
        logger.info("Periodic health check started (interval=%ds)", interval)

    async def stop_periodic(self) -> None:
        """停止定期檢查。"""
        self._running = False
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
        self._periodic_task = None
        logger.info("Periodic health check stopped")

    @staticmethod
    def _mark_failure(comp: ComponentHealth, error: str) -> None:
        comp.consecutive_failures += 1
        comp.consecutive_successes = 0
        comp.last_error = error
        if comp.consecutive_failures >= _UNHEALTHY_THRESHOLD:
            comp.status = DataSourceHealth.UNHEALTHY
        elif comp.consecutive_failures >= _DEGRADE_THRESHOLD:
            comp.status = DataSourceHealth.DEGRADED
