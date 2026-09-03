"""AI 信心維度模組 — 多維度評估分析結果可信度。

四個維度（各 25%）：
1. 模型準確度：ML predict_proba 信心
2. 資料完整度：OHLCV 天數 + 法人資料
3. 籌碼穩定度：法人連續買賣超方向一致性
4. 策略適用度：市場環境與策略方向匹配度
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)

# ── 常數 ──────────────────────────────────────────
REQUIRED_DAYS = 120
DIMENSION_WEIGHT = 0.25

LEVEL_THRESHOLDS: list[tuple[int, str]] = [
    (85, "極高"),
    (70, "高"),
    (50, "中"),
    (35, "低"),
    (0, "極低"),
]


# ── 資料結構 ──────────────────────────────────────
@dataclass
class ConfidenceDimension:
    """單一信心維度。"""

    name: str
    score: int  # 0-100
    description: str


@dataclass
class ConfidenceResult:
    """信心評估結果。"""

    symbol: str
    overall_score: int  # 0-100 加權總分
    level: str  # "極高" / "高" / "中" / "低" / "極低"
    dimensions: list[ConfidenceDimension] = field(default_factory=list)


# ── 主類別 ────────────────────────────────────────
class ConfidenceScorer:
    """AI 信心維度評估器。

    從模型準確度、資料完整度、籌碼穩定度、策略適用度四軸
    計算加權總分，輸出 0-100 分 + 五級文字標籤。
    """

    def evaluate(
        self,
        symbol: str,
        ohlcv_df: pd.DataFrame | None = None,
        ml_confidence: float | None = None,
        fund_flow_data: dict | None = None,
        market_regime: str | None = None,
    ) -> ConfidenceResult:
        """計算 AI 信心分數。

        Args:
            symbol: 股票代碼
            ohlcv_df: OHLCV DataFrame（需含 close 欄位）
            ml_confidence: ML 模型 predict_proba 最大值 (0-1)
            fund_flow_data: 法人資料，格式:
                {"consecutive_days": {"foreign": int, "trust": int},
                 "has_institutional": bool}
            market_regime: "BULL" / "RANGE" / "BEAR"
        """
        dims: list[ConfidenceDimension] = [
            self._score_model_accuracy(ml_confidence),
            self._score_data_completeness(ohlcv_df, fund_flow_data),
            self._score_flow_stability(fund_flow_data),
            self._score_strategy_fit(market_regime),
        ]

        overall = round(sum(d.score * DIMENSION_WEIGHT for d in dims))
        overall = max(0, min(100, overall))
        level = self._map_level(overall)

        result = ConfidenceResult(
            symbol=symbol,
            overall_score=overall,
            level=level,
            dimensions=dims,
        )
        logger.debug("ConfidenceScore %s: %d (%s)", symbol, overall, level)
        return result

    # ── 維度計算 ──────────────────────────────────

    @staticmethod
    def _score_model_accuracy(ml_confidence: float | None) -> ConfidenceDimension:
        """模型準確度：ML predict_proba 信心值。"""
        if ml_confidence is None:
            return ConfidenceDimension(
                name="模型準確度",
                score=50,
                description="無 ML 模型，預設中等信心",
            )
        score = max(0, min(100, round(ml_confidence * 100)))
        if score >= 80:
            desc = "模型高度自信"
        elif score >= 60:
            desc = "模型中度自信"
        else:
            desc = "模型信心偏低"
        return ConfidenceDimension(name="模型準確度", score=score, description=desc)

    @staticmethod
    def _score_data_completeness(
        ohlcv_df: pd.DataFrame | None,
        fund_flow_data: dict | None,
    ) -> ConfidenceDimension:
        """資料完整度：OHLCV 天數比例 + 法人資料加分。"""
        if ohlcv_df is None or ohlcv_df.empty:
            return ConfidenceDimension(
                name="資料完整度",
                score=0,
                description="無 OHLCV 資料",
            )

        days = len(ohlcv_df)
        ratio = min(1.0, days / REQUIRED_DAYS)
        score = round(ratio * 100)

        # 有法人資料 +10
        has_inst = (
            fund_flow_data is not None
            and fund_flow_data.get("has_institutional", False)
        )
        if has_inst:
            score = min(100, score + 10)

        if score >= 90:
            desc = f"資料充足（{days} 日）"
        elif score >= 60:
            desc = f"資料尚可（{days} 日 / 需 {REQUIRED_DAYS} 日）"
        else:
            desc = f"資料不足（{days} 日 / 需 {REQUIRED_DAYS} 日）"
        return ConfidenceDimension(name="資料完整度", score=score, description=desc)

    @staticmethod
    def _score_flow_stability(fund_flow_data: dict | None) -> ConfidenceDimension:
        """籌碼穩定度：法人連續買賣超天數 + 方向一致性。"""
        if fund_flow_data is None:
            return ConfidenceDimension(
                name="籌碼穩定度",
                score=50,
                description="無法人資料，預設中等",
            )

        consecutive = fund_flow_data.get("consecutive_days", {})
        foreign_days = consecutive.get("foreign", 0)
        trust_days = consecutive.get("trust", 0)

        # 基礎分：連續天數越多越穩定（以較大者為主）
        max_days = max(abs(foreign_days), abs(trust_days))
        if max_days >= 10:
            base = 90
        elif max_days >= 5:
            base = 70
        elif max_days >= 3:
            base = 55
        else:
            base = 40

        # 方向一致加分：外資與投信同向
        same_direction = (
            foreign_days != 0
            and trust_days != 0
            and (foreign_days > 0) == (trust_days > 0)
        )
        if same_direction:
            base = min(100, base + 15)

        # 方向分歧扣分
        divergent = (
            foreign_days != 0
            and trust_days != 0
            and (foreign_days > 0) != (trust_days > 0)
        )
        if divergent:
            base = max(0, base - 10)

        if base >= 80:
            desc = "法人籌碼高度穩定"
        elif base >= 60:
            desc = "法人籌碼中度穩定"
        else:
            desc = "法人籌碼不穩定"
        return ConfidenceDimension(name="籌碼穩定度", score=base, description=desc)

    @staticmethod
    def _score_strategy_fit(market_regime: str | None) -> ConfidenceDimension:
        """策略適用度：市場環境與做多策略匹配度。"""
        if market_regime is None:
            return ConfidenceDimension(
                name="策略適用度",
                score=50,
                description="無市場環境資訊，預設中等",
            )

        regime = market_regime.upper()
        if regime == "BULL":
            return ConfidenceDimension(
                name="策略適用度",
                score=90,
                description="多頭環境，策略高度適用",
            )
        if regime == "RANGE":
            return ConfidenceDimension(
                name="策略適用度",
                score=60,
                description="盤整環境，策略中度適用",
            )
        if regime == "BEAR":
            return ConfidenceDimension(
                name="策略適用度",
                score=30,
                description="空頭環境，做多策略適用度低",
            )
        return ConfidenceDimension(
            name="策略適用度",
            score=50,
            description=f"未知環境（{market_regime}），預設中等",
        )

    # ── 等級映射 ──────────────────────────────────

    @staticmethod
    def _map_level(score: int) -> str:
        for threshold, label in LEVEL_THRESHOLDS:
            if score >= threshold:
                return label
        return "極低"
