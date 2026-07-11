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
