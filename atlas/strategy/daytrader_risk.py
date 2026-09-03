"""隔日沖風險偵測模組 — 法人買超 / 量比 / 週轉率 / 振幅綜合評分。

偵測台股常見的隔日沖主力操作：當日大買、隔日倒貨。
根據法人買賣超、成交量異常、週轉率、日內振幅等特徵給出風險分數。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 評分權重
_W_MAIN_FORCE = 0.30   # 主力買超
_W_VOLUME_RATIO = 0.25  # 量比
_W_TURNOVER = 0.20      # 週轉率
_W_SWING = 0.15         # 日內振幅
_W_FD_RATIO = 0.10      # 外資+自營佔比

# 滿分門檻
_MAIN_FORCE_CAP = 5000    # 張
_VOLUME_RATIO_CAP = 3.0
_TURNOVER_CAP = 8.0       # %
_SWING_CAP = 5.0          # %
_FD_RATIO_CAP = 0.80      # 80%


@dataclass
class DaytraderRiskResult:
    """隔日沖風險偵測結果。"""

    symbol: str
    risk_level: str = "低"          # "高" / "中" / "低"
    risk_score: int = 0             # 0-100
    main_force_buy: int = 0         # 主力買超量（張）
    foreign_buy: int = 0            # 外資買超
    dealer_buy: int = 0             # 自營買超
    trust_buy: int = 0              # 投信買超
    turnover_rate: float = 0.0      # 週轉率%
    volume_ratio: float = 0.0       # 量比（今量/5日均量）
    intraday_swing: float = 0.0     # 日內振幅%
    signals: list[str] = field(default_factory=list)


class DaytraderRiskAnalyzer:
    """隔日沖風險分析器。

    輸入：OHLCV + 法人買賣超資料。
    輸出：風險分數 + 風險等級 + 訊號明細。
    """

    def __init__(
        self,
        volume_ma_period: int = 5,
        turnover_est_period: int = 60,
    ) -> None:
        self._vol_ma_period = volume_ma_period
        self._turnover_est_period = turnover_est_period

    def analyze(
        self,
        symbol: str,
        ohlcv_df: pd.DataFrame,
        fund_flow_data: dict | None = None,
        shares_outstanding: int | None = None,
    ) -> DaytraderRiskResult:
        """分析個股隔日沖風險。

        Args:
            symbol: 股票代碼。
            ohlcv_df: OHLCV DataFrame（需含 open/high/low/close/volume）。
            fund_flow_data: 當日法人買賣超（張），
                keys: foreign, trust, dealer, total。
            shares_outstanding: 在外流通股數（張）。若無則用均量估算。
        """
        if ohlcv_df is None or len(ohlcv_df) == 0:
            return DaytraderRiskResult(symbol=symbol)

        flow = fund_flow_data or {}
        foreign = int(flow.get("foreign", 0))
        trust = int(flow.get("trust", 0))
        dealer = int(flow.get("dealer", 0))
        total = int(flow.get("total", foreign + trust + dealer))

        volume_ratio = self._calc_volume_ratio(ohlcv_df)
        turnover = self._calc_turnover_rate(
            int(ohlcv_df["volume"].iloc[-1]),
            shares_outstanding,
            ohlcv_df,
        )
        swing = self._calc_intraday_swing(ohlcv_df)

        # --- 各項子分數（0-100） ---
        score_main = min(1.0, max(total, 0) / _MAIN_FORCE_CAP) * 100
        score_vol = min(1.0, max(volume_ratio, 0) / _VOLUME_RATIO_CAP) * 100
        score_turn = min(1.0, max(turnover, 0) / _TURNOVER_CAP) * 100
        score_swing = min(1.0, max(swing, 0) / _SWING_CAP) * 100
        score_fd = self._calc_fd_ratio_score(foreign, dealer, total)

        weighted = (
            score_main * _W_MAIN_FORCE
            + score_vol * _W_VOLUME_RATIO
            + score_turn * _W_TURNOVER
            + score_swing * _W_SWING
            + score_fd * _W_FD_RATIO
        )
        risk_score = int(round(weighted))
        risk_score = max(0, min(100, risk_score))

        if risk_score >= 70:
            risk_level = "高"
        elif risk_score >= 40:
            risk_level = "中"
        else:
            risk_level = "低"

        result = DaytraderRiskResult(
            symbol=symbol,
            risk_level=risk_level,
            risk_score=risk_score,
            main_force_buy=total,
            foreign_buy=foreign,
            dealer_buy=dealer,
            trust_buy=trust,
            turnover_rate=round(turnover, 2),
            volume_ratio=round(volume_ratio, 2),
            intraday_swing=round(swing, 2),
        )

        result.signals = self._detect_signals(result)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calc_turnover_rate(
        self,
        volume: int,
        shares_outstanding: int | None,
        ohlcv_df: pd.DataFrame,
    ) -> float:
        """週轉率(%) = 今日成交量 / 流通股數 * 100。

        若無流通股數，以近 60 日均量 * 5 估算流通股數。
        """
        if shares_outstanding and shares_outstanding > 0:
            return volume / shares_outstanding * 100

        # 估算
        n = min(len(ohlcv_df), self._turnover_est_period)
        if n <= 1:
            return 0.0
        avg_vol = float(np.mean(ohlcv_df["volume"].iloc[-n:-1].values))
        estimated = avg_vol * 5
        if estimated <= 0:
            return 0.0
        return volume / estimated * 100

    def _calc_volume_ratio(self, ohlcv_df: pd.DataFrame) -> float:
        """量比 = 今日量 / 5 日均量。"""
        if len(ohlcv_df) < 2:
            return 1.0
        n = min(len(ohlcv_df) - 1, self._vol_ma_period)
        avg_vol = float(np.mean(ohlcv_df["volume"].iloc[-n - 1 : -1].values))
        if avg_vol <= 0:
            return 1.0
        return float(ohlcv_df["volume"].iloc[-1]) / avg_vol

    @staticmethod
    def _calc_intraday_swing(ohlcv_df: pd.DataFrame) -> float:
        """日內振幅(%) = (最高 - 最低) / 最低 * 100。"""
        row = ohlcv_df.iloc[-1]
        low = float(row["low"])
        if low <= 0:
            return 0.0
        return (float(row["high"]) - low) / low * 100

    @staticmethod
    def _calc_fd_ratio_score(foreign: int, dealer: int, total: int) -> float:
        """外資+自營佔總買超比例的分數（0-100）。"""
        if total <= 0:
            return 0.0
        fd_sum = max(foreign, 0) + max(dealer, 0)
        ratio = fd_sum / total
        return min(1.0, ratio / _FD_RATIO_CAP) * 100

    @staticmethod
    def _detect_signals(result: DaytraderRiskResult) -> list[str]:
        """根據結果產生中文風險訊號。"""
        signals: list[str] = []

        if result.main_force_buy > 1000:
            signals.append(
                f"主力買超異常（+{result.main_force_buy:,} 張），隔日沖機率高"
            )

        if result.turnover_rate > 5.0:
            signals.append(f"換手率 {result.turnover_rate}%，籌碼鬆動")

        if result.intraday_swing > 3.0:
            signals.append(f"日內振幅 {result.intraday_swing}%，波動劇烈")

        if result.volume_ratio > 2.0:
            signals.append(f"量比 {result.volume_ratio}，成交量異常放大")

        if result.risk_score >= 70:
            signals.append(f"隔日回檔風險 {result.risk_score}%")

        return signals
