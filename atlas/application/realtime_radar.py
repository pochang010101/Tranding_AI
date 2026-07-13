"""盤中雷達 — 即時監控盤中異動與訊號觸發。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import DetectorType, MarketType, SignalType
from atlas.events import DetectorTriggered
from atlas.interfaces.application import IRealtimeRadar
from atlas.models.signals import DetectorAlert, Signal

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager
    from atlas.infrastructure.event_bus import EventBus
    from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)

# 所有 11 偵測器
_ALL_DETECTORS = list(DetectorType)


class RealtimeRadar(IRealtimeRadar):
    """盤中即時監控引擎。

    管理 11 偵測器，定期掃描 watchlist，
    透過 EventBus 發布 DetectorAlert 與 Signal。
    """

    def __init__(
        self,
        data_manager: DataManager,
        indicator_lib: IndicatorLibrary,
        event_bus: EventBus | None = None,
        scan_interval: float = 30.0,
    ) -> None:
        self._dm = data_manager
        self._ind = indicator_lib
        self._event_bus = event_bus
        self._scan_interval = scan_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._enabled_detectors: set[DetectorType] = set(_ALL_DETECTORS)
        self._alerts_today: list[DetectorAlert] = []
        self._signals_today: list[Signal] = []
        self._watchlist: list[str] = []

    async def start(self, market: MarketType) -> None:
        """啟動盤中雷達。"""
        if self._running:
            return
        self._running = True
        self._alerts_today.clear()
        self._signals_today.clear()
        self._task = asyncio.create_task(self._scan_loop(market))
        logger.info("Realtime radar started for %s", market.value)

    async def stop(self) -> None:
        """停止盤中雷達。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Realtime radar stopped. Alerts=%d Signals=%d",
                     len(self._alerts_today), len(self._signals_today))

    async def is_running(self) -> bool:
        return self._running

    async def enable_detector(self, detector_type: DetectorType) -> None:
        self._enabled_detectors.add(detector_type)

    async def disable_detector(self, detector_type: DetectorType) -> None:
        self._enabled_detectors.discard(detector_type)

    async def get_active_detectors(self) -> list[DetectorType]:
        return list(self._enabled_detectors)

    async def get_alerts_today(self, market: MarketType) -> list[DetectorAlert]:
        return list(self._alerts_today)

    async def get_signals_today(self, market: MarketType) -> list[Signal]:
        return list(self._signals_today)

    async def get_intraday_summary(self, market: MarketType) -> dict[str, Any]:
        """產出盤中摘要。"""
        detector_counts: dict[str, int] = {}
        for alert in self._alerts_today:
            dt = alert.detector_type.value
            detector_counts[dt] = detector_counts.get(dt, 0) + 1

        buy_signals = [s for s in self._signals_today if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in self._signals_today if s.signal_type == SignalType.SELL]

        return {
            "market": market.value,
            "date": date.today().isoformat(),
            "total_alerts": len(self._alerts_today),
            "total_signals": len(self._signals_today),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals),
            "detector_breakdown": detector_counts,
            "top_alert_codes": self._get_top_codes(self._alerts_today, 10),
        }

    def set_watchlist(self, codes: list[str]) -> None:
        self._watchlist = codes

    # ── 內部方法 ─────────────────────────────────

    async def _scan_loop(self, market: MarketType) -> None:
        """主掃描迴圈。"""
        while self._running:
            try:
                await self._run_detectors(market)
            except Exception as exc:
                logger.error("Radar scan error: %s", exc)
            await asyncio.sleep(self._scan_interval)

    async def _run_detectors(self, market: MarketType) -> None:
        """執行所有啟用的偵測器。"""
        for code in self._watchlist:
            for detector in self._enabled_detectors:
                try:
                    alert = await self._check_detector(code, market, detector)
                    if alert:
                        self._alerts_today.append(alert)
                        if self._event_bus:
                            await self._event_bus.publish(DetectorTriggered(
                                detector_type=alert.detector_type,
                                code=alert.code,
                                market=market,
                                severity=alert.severity,
                                price=alert.price,
                                detail=alert.detail,
                            ))
                except Exception as exc:
                    logger.debug("Detector %s failed on %s: %s", detector.value, code, exc)

    async def _check_detector(
        self, code: str, market: MarketType, detector: DetectorType
    ) -> DetectorAlert | None:
        """檢查單一偵測器（簡化版，各偵測器的完整邏輯待細化）。"""
        # 此處為框架，每個偵測器的具體判斷邏輯在後續迭代中細化
        # 目前回傳 None（不觸發）
        return None

    @staticmethod
    def _get_top_codes(alerts: list[DetectorAlert], top_n: int) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for a in alerts:
            counts[a.code] = counts.get(a.code, 0) + 1
        sorted_codes = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"code": c, "count": n} for c, n in sorted_codes[:top_n]]
