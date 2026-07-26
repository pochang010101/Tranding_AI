"""股期對沖策略引擎 — 基差分析、避險比、多空配對、策略建議。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BasisAnalysis:
    """基差分析結果。"""

    spot_price: float  # 現貨價格
    futures_price: float  # 期貨價格
    basis: float  # 基差 = 現貨 - 期貨
    basis_pct: float  # 基差率 = basis / spot * 100
    status: str  # "正價差" / "逆價差" / "平水"
    signal: str  # "套利機會" / "正常" / "市場恐慌"
    detail: str  # 中文說明


@dataclass
class HedgePosition:
    """對沖部位建議。"""

    stock_code: str
    stock_name: str
    stock_action: str  # "BUY" / "HOLD" / "SELL"
    stock_lots: int  # 現貨張數
    futures_action: str  # "BUY" / "SELL" / "NONE"
    futures_lots: int  # 期貨口數
    hedge_ratio: float  # 避險比率 (0~1)
    strategy_type: str  # "protective_put" / "covered_short" / "basis_arb" / "pair_trade"
    entry_price: float  # 建議進場價
    stop_loss: float  # 停損價
    take_profit: float  # 停利價
    risk_reward: float  # 風險報酬比
    confidence: str  # "HIGH" / "MEDIUM" / "LOW"
    reasoning: str  # 策略理由（中文）


@dataclass
class ChipFuturesSignal:
    """籌碼+期貨綜合訊號。"""

    code: str
    name: str
    # 現貨籌碼
    margin_trend: str  # "增加" / "減少" / "持平"
    institutional_trend: str  # "買超" / "賣超" / "持平"
    # 期貨籌碼
    foreign_futures_net: int  # 外資期貨淨部位
    futures_oi_change: int  # 未平倉增減
    put_call_ratio: float  # P/C ratio
    # 綜合
    direction: str  # "BULLISH" / "BEARISH" / "NEUTRAL"
    strength: int  # 1~5 強度
    detail: str  # 中文分析說明


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# 台指期每點價值（大台 200 元）
_FUTURES_POINT_VALUE = 200.0


class HedgeStrategyEngine:
    """股期對沖策略引擎。"""

    # ------------------------------------------------------------------
    # 基差分析
    # ------------------------------------------------------------------

    def analyze_basis(self, spot: float, futures: float) -> BasisAnalysis:
        """分析基差狀態。"""
        if spot <= 0:
            raise ValueError("spot price must be positive")

        basis = spot - futures
        basis_pct = (basis / spot) * 100.0

        # 狀態判定
        if basis_pct > 0.5:
            status = "正價差"
        elif basis_pct < -0.5:
            status = "逆價差"
        else:
            status = "平水"

        # 信號判定
        abs_pct = abs(basis_pct)
        if abs_pct > 1.5:
            signal = "套利機會"
        elif basis_pct < -0.5:
            signal = "市場恐慌"
        else:
            signal = "正常"

        # 中文說明
        detail_parts: list[str] = []
        detail_parts.append(f"現貨 {spot:.2f}，期貨 {futures:.2f}")
        detail_parts.append(f"基差 {basis:+.2f}（{basis_pct:+.2f}%）")
        if signal == "套利機會":
            detail_parts.append(f"基差率超過 1.5%，存在{status}套利空間")
        elif signal == "市場恐慌":
            detail_parts.append("逆價差偏大，市場情緒偏恐慌")
        else:
            detail_parts.append("基差正常，無明顯套利機會")

        return BasisAnalysis(
            spot_price=spot,
            futures_price=futures,
            basis=round(basis, 4),
            basis_pct=round(basis_pct, 4),
            status=status,
            signal=signal,
            detail="；".join(detail_parts),
        )

    # ------------------------------------------------------------------
    # 避險比
    # ------------------------------------------------------------------

    def calculate_hedge_ratio(
        self, stock_returns: pd.Series, index_returns: pd.Series
    ) -> float:
        """計算最小變異數避險比（beta 值）。

        hedge_ratio = Cov(stock, index) / Var(index)
        """
        if len(stock_returns) < 2 or len(index_returns) < 2:
            return 1.0

        # 對齊長度
        min_len = min(len(stock_returns), len(index_returns))
        s = stock_returns.iloc[:min_len].values.astype(float)
        idx = index_returns.iloc[:min_len].values.astype(float)

        var_idx = np.var(idx, ddof=1)
        if var_idx == 0:
            return 1.0

        cov = np.cov(s, idx, ddof=1)[0, 1]
        ratio = float(cov / var_idx)
        return round(max(0.0, min(ratio, 3.0)), 4)  # clamp 0~3

    # ------------------------------------------------------------------
    # 對沖建議
    # ------------------------------------------------------------------

    def suggest_hedge(
        self,
        code: str,
        name: str,
        current_price: float,
        stock_lots: int,
        beta: float,
        basis: BasisAnalysis,
        chip_signal: ChipFuturesSignal | None = None,
    ) -> HedgePosition:
        """根據籌碼與基差產出對沖建議。"""
        direction = chip_signal.direction if chip_signal else "NEUTRAL"
        chip_strength = chip_signal.strength if chip_signal else 0
        has_stock = stock_lots > 0

        # 預設值
        risk_reward = 3.0 if (chip_signal and chip_strength >= 4) else 2.0
        entry_price = current_price

        # 期貨口數計算輔助
        def _calc_futures_lots() -> int:
            notional = stock_lots * 1000 * current_price  # 張 → 股 → 市值
            lots = round(notional * beta / (basis.spot_price * _FUTURES_POINT_VALUE))
            return max(lots, 1)

        # --- 策略分派 ---

        if direction == "BEARISH" and has_stock:
            # 情境 1: 看空 + 持股 → 保護性避險
            f_lots = _calc_futures_lots()
            strategy_type = "protective_put"
            stock_action = "HOLD"
            futures_action = "SELL"
            stop_loss = round(entry_price * 1.05, 2)
            take_profit = round(entry_price * (1 - risk_reward * 0.05), 2)
            confidence = "HIGH" if chip_strength >= 4 else "MEDIUM"
            reasoning = (
                f"籌碼面偏空（強度 {chip_strength}），建議以期貨空單避險。"
                f"避險比 {beta:.2f}，期貨 {f_lots} 口對應 {stock_lots} 張現貨。"
            )

        elif direction == "BULLISH" and basis.status == "逆價差":
            # 情境 2: 看多 + 逆價差 → 基差套利
            f_lots = max(1, round(stock_lots * beta)) if has_stock else 1
            strategy_type = "basis_arb"
            stock_action = "BUY"
            futures_action = "SELL"
            stop_loss = round(entry_price * 0.95, 2)
            take_profit = round(entry_price * (1 + risk_reward * 0.05), 2)
            confidence = "HIGH" if abs(basis.basis_pct) > 1.5 else "MEDIUM"
            reasoning = (
                f"逆價差 {basis.basis_pct:+.2f}%，搭配籌碼偏多，"
                f"建議買現貨賣期貨，等基差收斂獲利。"
            )

        elif direction == "BULLISH" and not has_stock:
            # 情境 3: 看多 + 無持股 → 單純做多
            f_lots = 0
            strategy_type = "pair_trade"
            stock_action = "BUY"
            futures_action = "NONE"
            stop_loss = round(entry_price * 0.95, 2)
            take_profit = round(entry_price * (1 + risk_reward * 0.05), 2)
            confidence = "HIGH" if chip_strength >= 4 else "MEDIUM"
            reasoning = f"籌碼面偏多（強度 {chip_strength}），建議直接買進現貨。"

        elif direction == "BEARISH" and not has_stock:
            # 情境 4: 看空 + 無持股 → 期貨放空
            f_lots = 1
            strategy_type = "covered_short"
            stock_action = "NONE"
            futures_action = "SELL"
            stop_loss = round(entry_price * 1.05, 2)
            take_profit = round(entry_price * (1 - risk_reward * 0.05), 2)
            confidence = "HIGH" if chip_strength >= 4 else "MEDIUM"
            reasoning = (
                f"籌碼面偏空（強度 {chip_strength}），無持股，建議以期貨放空操作。"
            )

        else:
            # 中性 → 觀望
            f_lots = 0
            strategy_type = "pair_trade"
            stock_action = "HOLD" if has_stock else "NONE"
            futures_action = "NONE"
            stop_loss = round(entry_price * 0.95, 2)
            take_profit = round(entry_price * 1.10, 2)
            risk_reward = 2.0
            confidence = "LOW"
            reasoning = "籌碼中性，建議觀望，暫不建立對沖部位。"

        return HedgePosition(
            stock_code=code,
            stock_name=name,
            stock_action=stock_action,
            stock_lots=stock_lots,
            futures_action=futures_action,
            futures_lots=f_lots,
            hedge_ratio=round(beta, 4),
            strategy_type=strategy_type,
            entry_price=round(entry_price, 2),
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=round(risk_reward, 2),
            confidence=confidence,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # 籌碼 + 期貨 綜合訊號
    # ------------------------------------------------------------------

    def combine_chip_futures(
        self,
        margin_change: int,
        institutional_net: int,
        foreign_futures_net: int,
        futures_oi_change: int,
        put_call_ratio: float,
        code: str = "",
        name: str = "",
    ) -> ChipFuturesSignal:
        """整合現貨籌碼 + 期貨籌碼 → 方向判定。"""
        score = 0
        factors: list[str] = []

        # 1. 融資
        if margin_change < 0:
            score += 1
            factors.append("融資減少 → 籌碼洗清(+1)")
        elif margin_change > 0:
            score -= 1
            factors.append("融資增加 → 散戶追多(-1)")
        else:
            factors.append("融資持平(0)")

        # 2. 法人
        if institutional_net > 0:
            score += 1
            factors.append("法人買超(+1)")
        elif institutional_net < 0:
            score -= 1
            factors.append("法人賣超(-1)")
        else:
            factors.append("法人持平(0)")

        # 3. 外資期貨
        if foreign_futures_net > 0:
            score += 1
            factors.append("外資期貨淨多(+1)")
        elif foreign_futures_net < 0:
            score -= 1
            factors.append("外資期貨淨空(-1)")
        else:
            factors.append("外資期貨持平(0)")

        # 4. 未平倉（方向由 foreign_futures_net 代理）
        if futures_oi_change > 0 and foreign_futures_net > 0:
            score += 1
            factors.append("未平倉增+多方加碼(+1)")
        elif futures_oi_change > 0 and foreign_futures_net < 0:
            score -= 1
            factors.append("未平倉增+空方加碼(-1)")
        else:
            factors.append(f"未平倉變化 {futures_oi_change:+d}(0)")

        # 5. P/C ratio（反向指標）
        if put_call_ratio > 1.0:
            score += 1
            factors.append(f"P/C ratio {put_call_ratio:.2f} > 1.0 → 過度恐慌，反向偏多(+1)")
        elif put_call_ratio < 0.6:
            score -= 1
            factors.append(f"P/C ratio {put_call_ratio:.2f} < 0.6 → 過度樂觀，反向偏空(-1)")
        else:
            factors.append(f"P/C ratio {put_call_ratio:.2f} 正常(0)")

        # 方向
        if score >= 3:
            direction = "BULLISH"
        elif score <= -3:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        strength = min(abs(score), 5)

        # 趨勢標籤
        margin_trend = "減少" if margin_change < 0 else ("增加" if margin_change > 0 else "持平")
        inst_trend = (
            "買超"
            if institutional_net > 0
            else ("賣超" if institutional_net < 0 else "持平")
        )

        detail = f"綜合評分 {score:+d}（{direction}）。" + "｜".join(factors)

        return ChipFuturesSignal(
            code=code,
            name=name,
            margin_trend=margin_trend,
            institutional_trend=inst_trend,
            foreign_futures_net=foreign_futures_net,
            futures_oi_change=futures_oi_change,
            put_call_ratio=round(put_call_ratio, 4),
            direction=direction,
            strength=strength,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # 綜合報告
    # ------------------------------------------------------------------

    def generate_report(
        self,
        positions: list[HedgePosition],
        basis: BasisAnalysis,
        chip_signal: ChipFuturesSignal,
    ) -> dict[str, Any]:
        """產生綜合策略報告。"""
        # 市場觀點
        if chip_signal.direction == "BULLISH":
            market_view = "偏多"
        elif chip_signal.direction == "BEARISH":
            market_view = "偏空"
        else:
            market_view = "中性"

        # 風險提示
        warnings: list[str] = []
        if basis.signal == "市場恐慌":
            warnings.append("市場處於恐慌狀態，逆價差擴大，注意系統性風險")
        if chip_signal.strength >= 4 and chip_signal.direction == "BEARISH":
            warnings.append("籌碼面強烈偏空，建議降低持股水位或加大避險比重")
        if chip_signal.put_call_ratio > 1.3:
            warnings.append("P/C ratio 偏高，市場恐慌情緒濃厚，可能出現超跌反彈")
        if not warnings:
            warnings.append("目前無特殊風險警示")

        # 操作步驟
        action_plan: list[str] = []
        for pos in positions:
            steps: list[str] = []
            if pos.stock_action == "BUY":
                steps.append(f"買進 {pos.stock_code} {pos.stock_name} {pos.stock_lots} 張")
            elif pos.stock_action == "SELL":
                steps.append(f"賣出 {pos.stock_code} {pos.stock_name} {pos.stock_lots} 張")
            if pos.futures_action == "SELL":
                steps.append(f"賣出（放空）期貨 {pos.futures_lots} 口")
            elif pos.futures_action == "BUY":
                steps.append(f"買進期貨 {pos.futures_lots} 口")
            if steps:
                steps.append(f"停損 {pos.stop_loss}，停利 {pos.take_profit}")
                action_plan.append("→".join(steps))

        if not action_plan:
            action_plan.append("目前建議觀望，不建立新部位")

        return {
            "market_view": market_view,
            "basis_status": basis.detail,
            "chip_summary": chip_signal.detail,
            "positions": positions,
            "risk_warning": "；".join(warnings),
            "action_plan": action_plan,
        }
