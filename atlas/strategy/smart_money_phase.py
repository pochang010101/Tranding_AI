"""主力階段偵測 — 吸貨/洗盤/拉抬/出貨四階段 + 籌碼集中度。

Phase 12 A5：偵測法人連續買賣超、成交量異常、籌碼集中度變化，
判定主力目前處於哪個操作階段。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SmartMoneyPhase(StrEnum):
    ACCUMULATION = "accumulation"   # 吸貨
    SHAKEOUT = "shakeout"           # 洗盤
    MARKUP = "markup"               # 拉抬
    DISTRIBUTION = "distribution"   # 出貨
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PhaseResult:
    """主力階段偵測結果。"""

    code: str
    phase: SmartMoneyPhase = SmartMoneyPhase.UNKNOWN
    confidence: float = 0.0           # 信心度 0-1
    chip_concentration: float = 0.0   # 籌碼集中度 (正=集中, 負=分散)
    institutional_streak: int = 0     # 法人連續買賣超天數 (正=連買, 負=連賣)
    volume_ratio: float = 1.0         # 量比 (當日量/均量)
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SmartMoneyNarrative:
    """主力行為中文語義結論。"""

    headline: str      # 標題語意，如 "高檔出貨"、"底部吸貨"
    conclusion: str    # AI 結論段落（2-3句中文）
    action_tag: str    # 操作標籤："隔日沖" / "法人動作" / "觀望" / "布局"
    risk_note: str     # 風險提示


class SmartMoneyDetector:
    """主力階段偵測器。

    輸入：OHLCV + 法人買賣超資料。
    輸出：四階段判定 + 信心度 + 訊號明細。
    """

    def __init__(
        self,
        volume_ma_period: int = 20,
        streak_threshold: int = 3,
    ) -> None:
        self._vol_ma_period = volume_ma_period
        self._streak_threshold = streak_threshold

    def detect(
        self,
        df: pd.DataFrame,
        institutional_data: pd.Series | None = None,
        code: str = "",
    ) -> PhaseResult:
        """偵測主力階段。

        Args:
            df: OHLCV DataFrame。
            institutional_data: 法人每日淨買賣超金額 Series（正=買超）。
            code: 股票代碼。
        """
        if len(df) < self._vol_ma_period + 5:
            return PhaseResult(code=code)

        close = df["close"].values.astype(float)
        volume = df["volume"].values.astype(float)

        vol_ratio = self._calc_volume_ratio(volume)
        chip_conc = self._calc_chip_concentration(institutional_data)
        streak = self._calc_institutional_streak(institutional_data)
        price_trend = self._detect_price_trend(close)

        signals: list[str] = []
        phase, confidence = self._determine_phase(
            price_trend, vol_ratio, chip_conc, streak, signals
        )

        return PhaseResult(
            code=code,
            phase=phase,
            confidence=round(confidence, 2),
            chip_concentration=round(chip_conc, 4),
            institutional_streak=streak,
            volume_ratio=round(vol_ratio, 2),
            signals=signals,
        )

    def _calc_volume_ratio(self, volume: np.ndarray) -> float:
        """量比 = 最近成交量 / 均量。"""
        if len(volume) < self._vol_ma_period:
            return 1.0
        avg_vol = np.mean(volume[-self._vol_ma_period - 1 : -1])
        if avg_vol <= 0:
            return 1.0
        return float(volume[-1] / avg_vol)

    @staticmethod
    def _calc_chip_concentration(
        institutional_data: pd.Series | None,
    ) -> float:
        """籌碼集中度 = 近 N 日法人淨買超累積 / 成交量（簡化版）。

        正值 = 籌碼集中（主力吸貨），負值 = 籌碼分散（主力出貨）。
        """
        if institutional_data is None or len(institutional_data) < 5:
            return 0.0
        recent = institutional_data.values[-20:] if len(institutional_data) >= 20 else institutional_data.values
        total = float(np.sum(recent))
        # 標準化到 -1 ~ 1 區間
        abs_sum = float(np.sum(np.abs(recent)))
        if abs_sum == 0:
            return 0.0
        return total / abs_sum

    @staticmethod
    def _calc_institutional_streak(
        institutional_data: pd.Series | None,
    ) -> int:
        """法人連續買賣超天數。正=連買, 負=連賣。"""
        if institutional_data is None or len(institutional_data) == 0:
            return 0
        data = institutional_data.values
        streak = 0
        direction = 1 if data[-1] > 0 else -1

        for i in range(len(data) - 1, -1, -1):
            if (direction > 0 and data[i] > 0) or (direction < 0 and data[i] < 0):
                streak += 1
            else:
                break

        return streak * direction

    @staticmethod
    def _detect_price_trend(close: np.ndarray) -> str:
        """簡易趨勢判定：近 20 日的方向。"""
        if len(close) < 20:
            return "neutral"
        recent = close[-20:]
        change = (recent[-1] - recent[0]) / recent[0]
        if change > 0.05:
            return "up"
        elif change < -0.05:
            return "down"
        return "sideways"

    def _determine_phase(
        self,
        price_trend: str,
        vol_ratio: float,
        chip_conc: float,
        streak: int,
        signals: list[str],
    ) -> tuple[SmartMoneyPhase, float]:
        """綜合判定主力階段。"""
        score_acc = 0.0   # 吸貨分數
        score_shk = 0.0   # 洗盤分數
        score_mkp = 0.0   # 拉抬分數
        score_dis = 0.0   # 出貨分數

        # 吸貨特徵：盤整+縮量+籌碼集中+法人連買
        if price_trend == "sideways" and vol_ratio < 0.8:
            score_acc += 0.3
            signals.append("盤整縮量")
        if chip_conc > 0.3:
            score_acc += 0.3
            signals.append(f"籌碼集中({chip_conc:.2f})")
        if streak >= self._streak_threshold:
            score_acc += 0.2
            signals.append(f"法人連買{streak}日")

        # 洗盤特徵：急跌+爆量+但籌碼仍集中
        if price_trend == "down" and vol_ratio > 1.5 and chip_conc > 0:
            score_shk += 0.4
            signals.append("急跌爆量但籌碼未散")
        if price_trend == "down" and vol_ratio < 0.7:
            score_shk += 0.3
            signals.append("下跌縮量（假破真洗）")

        # 拉抬特徵：上漲+爆量+法人連買
        if price_trend == "up" and vol_ratio > 1.3:
            score_mkp += 0.3
            signals.append("上漲放量")
        if price_trend == "up" and streak >= self._streak_threshold:
            score_mkp += 0.3
            signals.append("上漲+法人連買")
        if price_trend == "up" and chip_conc > 0.3:
            score_mkp += 0.2
            signals.append("上漲+籌碼集中")

        # 出貨特徵：高位+爆量+籌碼分散+法人連賣
        if price_trend in ("up", "sideways") and vol_ratio > 2.0 and chip_conc < -0.2:
            score_dis += 0.4
            signals.append("高位爆量籌碼分散")
        if streak <= -self._streak_threshold:
            score_dis += 0.3
            signals.append(f"法人連賣{abs(streak)}日")

        scores = {
            SmartMoneyPhase.ACCUMULATION: score_acc,
            SmartMoneyPhase.SHAKEOUT: score_shk,
            SmartMoneyPhase.MARKUP: score_mkp,
            SmartMoneyPhase.DISTRIBUTION: score_dis,
        }

        best_phase = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_phase]

        if best_score < 0.2:
            return SmartMoneyPhase.UNKNOWN, 0.0

        return best_phase, min(1.0, best_score)

    # ------------------------------------------------------------------
    # 中文語義結論
    # ------------------------------------------------------------------

    def generate_narrative(self, phase_result: PhaseResult) -> SmartMoneyNarrative:
        """將主力階段分析結果轉為中文語義結論。"""
        phase = phase_result.phase
        conf = phase_result.confidence
        streak = phase_result.institutional_streak
        conc = phase_result.chip_concentration
        code = phase_result.code or "個股"
        days = abs(streak) if streak != 0 else 5

        conf_label = "高" if conf >= 0.6 else "中等" if conf >= 0.3 else "低"

        if phase == SmartMoneyPhase.ACCUMULATION:
            return self._narrative_accumulation(
                code, days, streak, conc, conf, conf_label
            )
        if phase == SmartMoneyPhase.SHAKEOUT:
            return self._narrative_shakeout(code, conf, conf_label)
        if phase == SmartMoneyPhase.MARKUP:
            return self._narrative_markup(code, conf, conf_label)
        if phase == SmartMoneyPhase.DISTRIBUTION:
            return self._narrative_distribution(code, days, conf, conf_label)

        # UNKNOWN
        return SmartMoneyNarrative(
            headline="訊號不明",
            conclusion=(
                f"{code} 目前主力動向不明確，信心度{conf_label}（{conf:.0%}）。"
                "建議持續觀察籌碼與量能變化，待訊號明朗再行動。"
            ),
            action_tag="觀望",
            risk_note="主力意圖尚未明朗，避免重倉操作",
        )

    @staticmethod
    def _narrative_accumulation(
        code: str,
        days: int,
        streak: int,
        conc: float,
        conf: float,
        conf_label: str,
    ) -> SmartMoneyNarrative:
        conclusion = (
            f"經 {days} 日主力行為綜合研判，{code} 呈現低檔量縮吸貨特徵，"
            f"法人連續買超 {abs(streak)} 日，"
            f"籌碼集中度 {conc:.0%}。"
        )
        if conf >= 0.6:
            conclusion += "吸貨訊號強烈，建議積極關注突破訊號。"
        else:
            conclusion += "建議關注突破訊號，但信心度偏低，宜小量試探。"
        return SmartMoneyNarrative(
            headline="底部吸貨",
            conclusion=conclusion,
            action_tag="布局",
            risk_note="底部吸貨階段仍有破底風險，建議分批布局並設定停損",
        )

    @staticmethod
    def _narrative_shakeout(
        code: str, conf: float, conf_label: str
    ) -> SmartMoneyNarrative:
        conclusion = (
            f"近期 {code} 出現量增價跌後迅速回穩跡象，"
            f"研判為主力洗盤行為，信心度{conf_label}（{conf:.0%}）。"
        )
        if conf >= 0.6:
            conclusion += "短線震盪但中期偏多，可逢低布局。"
        else:
            conclusion += "短線震盪劇烈，建議觀望為主，等洗盤結束再進場。"
        return SmartMoneyNarrative(
            headline="洗盤整理",
            conclusion=conclusion,
            action_tag="觀望",
            risk_note="洗盤過程波動大，勿追高殺低，等穩定後再進場",
        )

    @staticmethod
    def _narrative_markup(
        code: str, conf: float, conf_label: str
    ) -> SmartMoneyNarrative:
        conclusion = (
            f"主力進入拉抬階段，{code} 量增價漲且法人持續加碼，"
            f"動能強度{conf_label}（{conf:.0%}）。"
        )
        if conf >= 0.6:
            conclusion += "多方氣勢強勁，回檔不破支撐可加碼。"
        else:
            conclusion += "注意追高風險，建議以回檔不破支撐為進場依據。"
        return SmartMoneyNarrative(
            headline="強勢拉抬",
            conclusion=conclusion,
            action_tag="法人動作",
            risk_note="拉抬階段追高風險增加，嚴守停損紀律",
        )

    @staticmethod
    def _narrative_distribution(
        code: str, days: int, conf: float, conf_label: str
    ) -> SmartMoneyNarrative:
        conclusion = (
            f"經 {days} 日主力行為綜合研判，{code} 顯示高檔出貨跡象，"
            f"量大但價格無法創高，信心度{conf_label}（{conf:.0%}）。"
        )
        if conf >= 0.6:
            conclusion += "出貨訊號明確，需謹慎操作與資金控管。"
        else:
            conclusion += "出貨跡象初現，建議減碼觀望。"
        return SmartMoneyNarrative(
            headline="高檔出貨",
            conclusion=conclusion,
            action_tag="隔日沖",
            risk_note="⚠ 高檔出貨風險增加，建議控管倉位與停損紀律",
        )
