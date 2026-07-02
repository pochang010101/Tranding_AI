"""IPO 工具 — 新股上市公開申購掃描與蜜月期追蹤。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from atlas.interfaces.strategy import IIPOModule

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)


class IPOModule(IIPOModule):
    """IPO 分析模組。

    功能：
    - 掃描即將公開申購的標的（spread > 20% 才推薦）
    - 追蹤蜜月期（上市後 30 日表現）
    - 歷史勝率統計
    """

    def __init__(
        self,
        data_manager: DataManager | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache
        self._tracked: dict[str, dict[str, Any]] = {}

    async def scan_upcoming(self) -> list[dict[str, Any]]:
        """掃描即將公開申購的標的。

        目前使用模擬資料，實際接入需串接證交所公開申購 API。
        """
        # TODO: 串接 TWSE 公開申購 API
        # 目前回傳空列表，待資料源接入
        logger.info("IPO scan: no live data source configured, returning empty")
        return []

    async def track_honeymoon(
        self, code: str, ipo_date: date
    ) -> dict[str, Any]:
        """追蹤蜜月期（上市後 30 日表現）。"""
        days_since = (date.today() - ipo_date).days
        result: dict[str, Any] = {
            "code": code,
            "ipo_date": ipo_date.isoformat(),
            "days_since_ipo": days_since,
            "return_pct": 0.0,
            "pattern": "unknown",
            "status": "tracking",
        }

        if not self._dm:
            return result

        try:
            from atlas.enums import MarketType
            end = date.today()
            start = ipo_date
            bars = await self._dm.fetch_daily_bars(code, MarketType.TW, start, end)

            if len(bars) < 2:
                return result

            ipo_price = float(bars[0].close)
            current_price = float(bars[-1].close)
            return_pct = (current_price - ipo_price) / ipo_price * 100

            # 判斷蜜月期模式
            max_price = max(float(b.high) for b in bars)
            max_return = (max_price - ipo_price) / ipo_price * 100

            if return_pct > 30:
                pattern = "strong_rally"
            elif return_pct > 10:
                pattern = "steady_up"
            elif return_pct > 0:
                pattern = "mild_up"
            elif return_pct > -10:
                pattern = "flat"
            else:
                pattern = "decline"

            if days_since > 30:
                status = "honeymoon_ended"
            elif return_pct < -20:
                status = "broken"
            else:
                status = "tracking"

            result.update({
                "return_pct": round(return_pct, 2),
                "max_return_pct": round(max_return, 2),
                "current_price": current_price,
                "ipo_price": ipo_price,
                "pattern": pattern,
                "status": status,
                "trading_days": len(bars),
            })

            self._tracked[code] = result
        except Exception as exc:
            logger.warning("IPO track failed for %s: %s", code, exc)

        return result

    async def get_historical_win_rate(self) -> dict[str, float]:
        """取得 IPO 歷史勝率統計。"""
        if not self._tracked:
            return {
                "total": 0,
                "win_rate_30d": 0.0,
                "avg_return_30d": 0.0,
                "best_return": 0.0,
                "worst_return": 0.0,
            }

        returns = [t["return_pct"] for t in self._tracked.values() if "return_pct" in t]
        if not returns:
            return {
                "total": len(self._tracked),
                "win_rate_30d": 0.0,
                "avg_return_30d": 0.0,
                "best_return": 0.0,
                "worst_return": 0.0,
            }

        wins = sum(1 for r in returns if r > 0)
        return {
            "total": len(returns),
            "win_rate_30d": round(wins / len(returns) * 100, 1),
            "avg_return_30d": round(sum(returns) / len(returns), 2),
            "best_return": round(max(returns), 2),
            "worst_return": round(min(returns), 2),
        }
