"""缺口預測 — 預測台股開盤跳空缺口的方向與幅度。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from atlas.interfaces.strategy import IGapPredictor

if TYPE_CHECKING:
    from atlas.domain.international import InternationalMarket
    from atlas.infrastructure.cache import CacheManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "gap_prediction:latest"
_HISTORY_KEY = "gap_prediction:history"


class GapPredictor(IGapPredictor):
    """台股開盤缺口預測器。

    根據美股四大指數、台指期夜盤、ADR 溢價率等因子，
    預測台股開盤跳空方向與幅度。盤後進行校驗累積準確率。
    """

    def __init__(
        self,
        international: InternationalMarket | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._intl = international
        self._cache = cache
        self._history: list[dict[str, Any]] = []

    async def predict(
        self, us_data: dict[str, Any], futures_data: dict[str, Any]
    ) -> dict[str, Any]:
        """預測台股開盤缺口。

        因子權重：
        - 台指期夜盤漲跌(40%)
        - 費半指數漲跌(25%)
        - S&P500 漲跌(20%)
        - ADR 溢價率(15%)
        """
        factors: dict[str, float] = {}

        # 台指期夜盤
        futures_change = futures_data.get("change_pct", 0.0)
        factors["tw_futures"] = futures_change

        # 費半指數
        indices = us_data.get("indices", {})
        sox_change = indices.get("SOX", {}).get("change_pct", 0.0)
        factors["sox"] = sox_change

        # S&P 500
        spx_change = indices.get("SPX", {}).get("change_pct", 0.0)
        factors["spx"] = spx_change

        # ADR 溢價率（平均）
        stocks = us_data.get("stocks", {})
        adr_changes = [s.get("change_pct", 0.0) for s in stocks.values() if isinstance(s, dict)]
        adr_avg = sum(adr_changes) / len(adr_changes) if adr_changes else 0.0
        factors["adr"] = adr_avg

        # 加權預測
        weighted = (
            futures_change * 0.40
            + sox_change * 0.25
            + spx_change * 0.20
            + adr_avg * 0.15
        )

        if weighted > 0.3:
            direction = "up"
        elif weighted < -0.3:
            direction = "down"
        else:
            direction = "flat"

        magnitude = abs(weighted)
        # 信心度：因子方向一致性
        signs = [1 if f > 0 else (-1 if f < 0 else 0) for f in factors.values()]
        agreement = abs(sum(signs)) / max(len(signs), 1)
        confidence = round(min(0.95, 0.5 + agreement * 0.3 + min(magnitude, 2) * 0.1), 2)

        result = {
            "direction": direction,
            "magnitude_pct": round(magnitude, 2),
            "confidence": confidence,
            "factors": {k: round(v, 4) for k, v in factors.items()},
            "predicted_at": datetime.utcnow().isoformat(),
        }

        if self._cache:
            await self._cache.set(_CACHE_KEY, result, ttl=3600 * 12)

        logger.info("Gap prediction: %s %.2f%% (confidence=%.2f)", direction, magnitude, confidence)
        return result

    async def verify(
        self,
        prediction: dict[str, Any],
        actual_open: float,
        previous_close: float,
    ) -> dict[str, Any]:
        """盤後校驗缺口預測準確度。"""
        actual_gap = (actual_open - previous_close) / previous_close * 100
        if actual_gap > 0.1:
            actual_direction = "up"
        elif actual_gap < -0.1:
            actual_direction = "down"
        else:
            actual_direction = "flat"

        is_correct = prediction.get("direction") == actual_direction

        self._history.append({
            "predicted": prediction.get("direction"),
            "actual": actual_direction,
            "correct": is_correct,
        })

        correct_count = sum(1 for h in self._history if h["correct"])
        cumulative_accuracy = correct_count / len(self._history) if self._history else 0.0

        result = {
            "predicted_direction": prediction.get("direction", ""),
            "actual_direction": actual_direction,
            "predicted_magnitude": prediction.get("magnitude_pct", 0.0),
            "actual_magnitude": round(abs(actual_gap), 2),
            "is_correct": is_correct,
            "cumulative_accuracy": round(cumulative_accuracy, 4),
            "total_predictions": len(self._history),
        }

        logger.info(
            "Gap verify: pred=%s actual=%s correct=%s cum_acc=%.1f%%",
            result["predicted_direction"],
            actual_direction,
            is_correct,
            cumulative_accuracy * 100,
        )
        return result
