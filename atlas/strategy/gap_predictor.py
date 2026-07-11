"""缺口預測 — 預測台股開盤跳空缺口的方向與幅度。

Phase 11 A2 強化：
- 新增 VIX 恐慌因子（第 5 因子）
- 缺口分類（完全/部分/島型反轉）
- 歷史缺口填補率統計
"""

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

# 因子權重（5 因子版本）
_WEIGHTS = {
    "tw_futures": 0.35,
    "sox": 0.22,
    "spx": 0.18,
    "adr": 0.15,
    "vix": 0.10,
}


class GapPredictor(IGapPredictor):
    """台股開盤缺口預測器。

    根據美股四大指數、台指期夜盤、ADR 溢價率、VIX 等因子，
    預測台股開盤跳空方向與幅度。盤後進行校驗累積準確率。
    支援缺口分類（完全/部分/島型反轉）與歷史填補率統計。
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

        因子權重（5 因子）：
        - 台指期夜盤漲跌(35%)
        - 費半指數漲跌(22%)
        - S&P500 漲跌(18%)
        - ADR 溢價率(15%)
        - VIX 變動(10%)，VIX 上升→利空
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
        adr_changes = [
            s.get("change_pct", 0.0) for s in stocks.values() if isinstance(s, dict)
        ]
        adr_avg = sum(adr_changes) / len(adr_changes) if adr_changes else 0.0
        factors["adr"] = adr_avg

        # VIX 恐慌指數（上升=利空，取反）
        vix_change = indices.get("VIX", {}).get("change_pct", 0.0)
        factors["vix"] = -vix_change  # VIX 漲 → 負面影響

        # 加權預測
        weighted = sum(factors[k] * _WEIGHTS[k] for k in _WEIGHTS)

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
        confidence = round(
            min(0.95, 0.5 + agreement * 0.3 + min(magnitude, 2) * 0.1), 2
        )

        result = {
            "direction": direction,
            "magnitude_pct": round(magnitude, 2),
            "confidence": confidence,
            "factors": {k: round(v, 4) for k, v in factors.items()},
            "predicted_at": datetime.utcnow().isoformat(),
        }

        if self._cache:
            await self._cache.set(_CACHE_KEY, result, ttl=3600 * 12)

        logger.info(
            "Gap prediction: %s %.2f%% (confidence=%.2f)",
            direction, magnitude, confidence,
        )
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
            "actual_gap_pct": round(actual_gap, 4),
            "correct": is_correct,
        })

        correct_count = sum(1 for h in self._history if h["correct"])
        cumulative_accuracy = (
            correct_count / len(self._history) if self._history else 0.0
        )

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

    @staticmethod
    def classify_gap(
        actual_open: float,
        previous_close: float,
        previous_high: float,
        previous_low: float,
        day_low: float | None = None,
        day_high: float | None = None,
    ) -> dict[str, Any]:
        """分類缺口型態。

        Returns:
            {
                'type': 'full_up' | 'full_down' | 'partial_up' | 'partial_down' | 'none',
                'gap_pct': float,
                'filled': bool（盤中是否回補），
                'island': bool（是否為島型反轉候選），
            }
        """
        gap_pct = (actual_open - previous_close) / previous_close * 100

        if actual_open > previous_high:
            gap_type = "full_up"
        elif actual_open > previous_close:
            gap_type = "partial_up"
        elif actual_open < previous_low:
            gap_type = "full_down"
        elif actual_open < previous_close:
            gap_type = "partial_down"
        else:
            gap_type = "none"

        # 缺口是否盤中回補
        filled = False
        if day_low is not None and gap_type in ("full_up", "partial_up"):
            filled = day_low <= previous_close
        if day_high is not None and gap_type in ("full_down", "partial_down"):
            filled = day_high >= previous_close

        # 島型反轉候選：完全缺口 + 未回補
        island = gap_type.startswith("full") and not filled

        return {
            "type": gap_type,
            "gap_pct": round(gap_pct, 4),
            "filled": filled,
            "island": island,
        }

    def get_fill_rate(self) -> dict[str, float]:
        """統計歷史缺口填補率（需先 verify 累積資料）。

        Returns:
            {'up_fill_rate': float, 'down_fill_rate': float, 'overall_fill_rate': float}
        """
        up_gaps = [h for h in self._history if h.get("actual") == "up"]
        down_gaps = [h for h in self._history if h.get("actual") == "down"]
        all_directional = up_gaps + down_gaps

        def _rate(subset: list[dict]) -> float:
            filled = [h for h in subset if h.get("filled", False)]
            return round(len(filled) / len(subset), 4) if subset else 0.0

        return {
            "up_fill_rate": _rate(up_gaps),
            "down_fill_rate": _rate(down_gaps),
            "overall_fill_rate": _rate(all_directional),
            "total_records": len(self._history),
        }
