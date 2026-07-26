"""股期對沖綜合建議引擎 — 整合籌碼+期貨+技術面產出買賣策略。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------


@dataclass
class HedgeAdvice:
    """單一標的完整對沖建議。"""

    code: str
    name: str
    current_price: float
    # 籌碼面
    margin_balance: int
    margin_change: int
    short_balance: int
    short_margin_ratio: float
    institutional_net: int  # 法人買賣超
    # 期貨面
    basis_pct: float
    foreign_futures_net: int
    put_call_ratio: float
    # 綜合判定
    direction: str  # BULLISH / BEARISH / NEUTRAL
    confidence: str  # HIGH / MEDIUM / LOW
    # 策略建議
    stock_action: str  # BUY / HOLD / SELL / NONE
    futures_action: str  # BUY / SELL / NONE
    hedge_type: str  # 策略類型名稱
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    # 說明
    reasoning: str  # 完整中文分析（多行）
    risk_warning: str  # 風險提示
    action_steps: list[str] = field(default_factory=list)  # 具體操作步驟


# ---------------------------------------------------------------------------
# HedgeAdvisor
# ---------------------------------------------------------------------------


class HedgeAdvisor:
    """股期對沖綜合建議引擎。

    整合資料來源：
    1. atlas.infrastructure.margin_data — 融資融券
    2. atlas.infrastructure.taifex_data — 期貨行情/法人未平倉
    3. atlas.domain.margin_analysis — 籌碼分析
    4. atlas.strategy.hedge_strategy — 對沖策略
    5. atlas.infrastructure.twse_bulk — 法人買賣超（T86）
    """

    # ── 方向/信心判定閾值 ──────────────────────────────

    _BULLISH_SCORE = 2
    _BEARISH_SCORE = -2
    _HIGH_CONF_ABS = 3
    _STOP_LOSS_PCT = 0.05
    _TAKE_PROFIT_PCT = 0.10

    # ── public API ────────────────────────────────────

    def analyze_stock(self, code: str, stock_lots: int = 0) -> HedgeAdvice:
        """分析單一個股，產出完整對沖建議。

        步驟：
        1. 抓融資融券資料（margin_data）
        2. 抓法人買賣超（twse_bulk T86）
        3. 抓期貨資料（taifex_data）
        4. 用 MarginAnalyzer 分析籌碼
        5. 用 HedgeStrategyEngine.combine_chip_futures 整合訊號（若可用）
        6. 用 HedgeStrategyEngine.suggest_hedge 產出建議（若可用）
        7. 組裝 HedgeAdvice

        所有資料抓取都用 try/except，缺失資料用預設值（0 或 neutral）。
        """

        # 1. 融資融券
        margin_balance, margin_change, short_balance, short_margin_ratio = (
            self._fetch_margin(code)
        )

        # 2. 法人買賣超
        institutional_net = self._fetch_institutional_net(code)

        # 3. 期貨 (taifex_data — 可能尚未實作)
        basis_pct, foreign_futures_net, put_call_ratio = self._fetch_futures_data()

        # 4. 籌碼分析
        chip_verdict = self._run_margin_analysis(
            code, margin_balance, short_balance, margin_change,
        )

        # 5. 現價
        current_price = self._fetch_stock_price(code)

        # 6. 取得股票名稱
        name = self._fetch_stock_name(code)

        # 7. 綜合方向 / 信心
        direction, confidence, score = self._compute_direction(
            chip_verdict=chip_verdict,
            institutional_net=institutional_net,
            basis_pct=basis_pct,
            foreign_futures_net=foreign_futures_net,
            put_call_ratio=put_call_ratio,
        )

        # 8. 策略建議
        stock_action, futures_action, hedge_type = self._decide_actions(
            direction, confidence, stock_lots,
        )

        # 9. 價位計算
        entry_price = current_price
        stop_loss = round(current_price * (1 - self._STOP_LOSS_PCT), 2)
        take_profit = round(current_price * (1 + self._TAKE_PROFIT_PCT), 2)
        risk_reward = round(
            self._TAKE_PROFIT_PCT / self._STOP_LOSS_PCT, 2
        ) if self._STOP_LOSS_PCT > 0 else 0.0

        # 10. reasoning / risk_warning / action_steps
        reasoning = self._build_reasoning(
            code=code,
            name=name,
            chip_verdict=chip_verdict,
            margin_change=margin_change,
            institutional_net=institutional_net,
            basis_pct=basis_pct,
            foreign_futures_net=foreign_futures_net,
            direction=direction,
            confidence=confidence,
        )
        risk_warning = self._build_risk_warning(direction, confidence)
        action_steps = self._build_action_steps(
            code=code,
            name=name,
            stock_action=stock_action,
            futures_action=futures_action,
            stock_lots=stock_lots,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        return HedgeAdvice(
            code=code,
            name=name,
            current_price=current_price,
            margin_balance=margin_balance,
            margin_change=margin_change,
            short_balance=short_balance,
            short_margin_ratio=short_margin_ratio,
            institutional_net=institutional_net,
            basis_pct=basis_pct,
            foreign_futures_net=foreign_futures_net,
            put_call_ratio=put_call_ratio,
            direction=direction,
            confidence=confidence,
            stock_action=stock_action,
            futures_action=futures_action,
            hedge_type=hedge_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            reasoning=reasoning,
            risk_warning=risk_warning,
            action_steps=action_steps,
        )

    def analyze_batch(self, codes: list[str]) -> list[HedgeAdvice]:
        """批次分析多檔股票。"""
        results: list[HedgeAdvice] = []
        for code in codes:
            try:
                advice = self.analyze_stock(code)
                results.append(advice)
            except Exception as exc:
                logger.warning("analyze_stock(%s) failed: %s", code, exc)
        return results

    def market_overview(self) -> dict[str, Any]:
        """大盤對沖概覽。

        回傳：
        {
            "basis": 基差分析結果,
            "institutional_futures": 三大法人期貨未平倉,
            "put_call_ratio": P/C ratio,
            "top10_traders": 大額交易人,
            "market_direction": "BULLISH" / "BEARISH" / "NEUTRAL",
            "market_detail": 中文大盤分析,
            "hedge_suggestion": 大盤層面的避險建議,
        }
        """
        basis_pct, foreign_futures_net, put_call_ratio = self._fetch_futures_data()

        # 大盤方向判定
        bull_pts = 0
        if basis_pct > 0.1:
            bull_pts += 1
        elif basis_pct < -0.1:
            bull_pts -= 1
        if foreign_futures_net > 5000:
            bull_pts += 1
        elif foreign_futures_net < -5000:
            bull_pts -= 1
        if put_call_ratio < 0.8:
            bull_pts += 1
        elif put_call_ratio > 1.2:
            bull_pts -= 1

        if bull_pts >= 2:
            market_direction = "BULLISH"
        elif bull_pts <= -2:
            market_direction = "BEARISH"
        else:
            market_direction = "NEUTRAL"

        # 中文分析
        details: list[str] = []
        if basis_pct != 0:
            sign = "正" if basis_pct > 0 else "逆"
            details.append(f"台指期{sign}價差 {basis_pct:.2f}%")
        if foreign_futures_net != 0:
            side = "淨多" if foreign_futures_net > 0 else "淨空"
            details.append(f"外資期貨{side} {abs(foreign_futures_net):,} 口")
        if put_call_ratio > 0:
            details.append(f"Put/Call Ratio {put_call_ratio:.2f}")
        market_detail = "；".join(details) if details else "期貨資料暫無法取得"

        # 避險建議
        if market_direction == "BULLISH":
            hedge_suggestion = "大盤偏多，可降低避險部位至 20-30%，以免錯失漲幅"
        elif market_direction == "BEARISH":
            hedge_suggestion = "大盤偏空，建議提高避險至 60-80%，賣出台指期或買進 Put"
        else:
            hedge_suggestion = "大盤中性，維持基本避險 40-50%，觀望為主"

        return {
            "basis": {"basis_pct": basis_pct},
            "institutional_futures": {"foreign_net": foreign_futures_net},
            "put_call_ratio": put_call_ratio,
            "top10_traders": {},
            "market_direction": market_direction,
            "market_detail": market_detail,
            "hedge_suggestion": hedge_suggestion,
        }

    # ── private: data fetching ────────────────────────

    def _fetch_stock_price(self, code: str) -> float:
        """取得個股現價（TWSE/TPEx → yfinance fallback）。"""
        # 優先從 TWSE/TPEx 全市場行情取收盤價（快取，不需網路）
        try:
            from atlas.infrastructure.twse_bulk import fetch_twse_daily_all, fetch_tpex_daily_all
            for fetch_fn in [fetch_twse_daily_all, fetch_tpex_daily_all]:
                df = fetch_fn()
                if not df.empty and "code" in df.columns and "close" in df.columns:
                    match = df[df["code"] == code]
                    if not match.empty:
                        price = float(match.iloc[0]["close"])
                        if price > 0:
                            return price
        except Exception:
            pass

        # Fallback: yfinance
        try:
            import yfinance as yf
            from atlas.constants import is_otc
            ticker = f"{code}.TWO" if is_otc(code) else f"{code}.TW"
            data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
            if not data.empty:
                return float(data["Close"].iloc[-1])
        except Exception:
            pass
        return 0.0

    def _fetch_stock_name(self, code: str) -> str:
        """從融資融券資料取得股票名稱。"""
        try:
            from atlas.infrastructure.margin_data import fetch_twse_margin_all

            df = fetch_twse_margin_all()
            if not df.empty:
                match = df[df["code"] == code]
                if not match.empty:
                    return str(match.iloc[0].get("name", code))
        except Exception:
            pass
        return code

    def _fetch_institutional_net(self, code: str) -> int:
        """取得法人買賣超淨額。"""
        try:
            from atlas.infrastructure.twse_bulk import fetch_twse_institutional

            df = fetch_twse_institutional()
            if not df.empty:
                match = df[df["code"] == code]
                if not match.empty:
                    return int(match.iloc[0].get("foreign_net", 0))
        except Exception:
            pass
        return 0

    def _fetch_margin(self, code: str) -> tuple[int, int, int, float]:
        """取得融資融券資料，回傳 (margin_balance, margin_change, short_balance, short_margin_ratio)。"""
        try:
            from atlas.infrastructure.margin_data import fetch_twse_margin_all, fetch_tpex_margin_all

            twse = fetch_twse_margin_all()
            tpex = fetch_tpex_margin_all()
            combined = pd.concat([twse, tpex], ignore_index=True) if not twse.empty or not tpex.empty else pd.DataFrame()

            if not combined.empty:
                match = combined[combined["code"] == code]
                if not match.empty:
                    row = match.iloc[0]
                    mb = int(row.get("margin_balance", 0))
                    sb = int(row.get("short_balance", 0))
                    # margin_change = margin_buy - margin_sell
                    mc = int(row.get("margin_buy", 0)) - int(row.get("margin_sell", 0))
                    smr = round((sb / mb * 100), 2) if mb > 0 else 0.0
                    return mb, mc, sb, smr
        except Exception as exc:
            logger.debug("_fetch_margin(%s) failed: %s", code, exc)
        return 0, 0, 0, 0.0

    def _fetch_futures_data(self) -> tuple[float, int, float]:
        """取得期貨資料 (basis_pct, foreign_futures_net, put_call_ratio)。

        嘗試從 atlas.infrastructure.taifex_data 取得，若模組不存在則回傳預設值。
        """
        basis_pct = 0.0
        foreign_futures_net = 0
        put_call_ratio = 0.0

        try:
            from atlas.infrastructure.taifex_data import (
                fetch_futures_basis,
                fetch_futures_institutional,
                fetch_put_call_ratio,
            )

            basis = fetch_futures_basis()
            if isinstance(basis, dict):
                basis_pct = float(basis.get("basis_pct", 0.0))

            inst_df = fetch_futures_institutional()
            if isinstance(inst_df, pd.DataFrame) and not inst_df.empty:
                foreign_row = inst_df[inst_df["identity"] == "外資"]
                if not foreign_row.empty:
                    foreign_futures_net = int(foreign_row.iloc[0].get("net_position", 0))

            pcr = fetch_put_call_ratio()
            if isinstance(pcr, dict):
                put_call_ratio = float(pcr.get("pc_ratio_oi", 0.0)) / 100.0 if pcr.get("pc_ratio_oi", 0) > 10 else float(pcr.get("pc_ratio_oi", 0.0))
        except ImportError:
            logger.info("taifex_data 模組尚未實作，期貨資料使用預設值")
        except Exception as exc:
            logger.warning("取得期貨資料失敗: %s", exc)

        return basis_pct, foreign_futures_net, put_call_ratio

    # ── private: analysis ─────────────────────────────

    def _run_margin_analysis(
        self,
        code: str,
        margin_balance: int,
        short_balance: int,
        margin_change: int,
    ) -> str:
        """用 MarginAnalyzer 分析籌碼，回傳 verdict 字串。"""
        try:
            from atlas.domain.margin_analysis import MarginAnalyzer

            analyzer = MarginAnalyzer()
            signal = analyzer.analyze_single(
                code=code,
                name=code,
                margin_balance=margin_balance,
                margin_limit=0,
                short_balance=short_balance,
                short_limit=0,
                margin_change=margin_change,
            )
            return signal.verdict
        except Exception as exc:
            logger.debug("_run_margin_analysis(%s) failed: %s", code, exc)
        return "neutral"

    def _compute_direction(
        self,
        *,
        chip_verdict: str,
        institutional_net: int,
        basis_pct: float,
        foreign_futures_net: int,
        put_call_ratio: float,
    ) -> tuple[str, str, int]:
        """綜合評分產出方向與信心。回傳 (direction, confidence, score)。"""
        score = 0

        # 籌碼面
        if chip_verdict in ("bullish", "squeeze_alert"):
            score += 1
        elif chip_verdict in ("bearish", "margin_call_risk"):
            score -= 1

        # 法人買賣超
        if institutional_net > 0:
            score += 1
        elif institutional_net < 0:
            score -= 1

        # 期貨基差
        if basis_pct > 0.1:
            score += 1
        elif basis_pct < -0.1:
            score -= 1

        # 外資期貨
        if foreign_futures_net > 3000:
            score += 1
        elif foreign_futures_net < -3000:
            score -= 1

        # Put/Call ratio
        if 0 < put_call_ratio < 0.8:
            score += 1
        elif put_call_ratio > 1.2:
            score -= 1

        # 方向
        if score >= self._BULLISH_SCORE:
            direction = "BULLISH"
        elif score <= self._BEARISH_SCORE:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # 信心
        if abs(score) >= self._HIGH_CONF_ABS:
            confidence = "HIGH"
        elif abs(score) >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return direction, confidence, score

    def _decide_actions(
        self,
        direction: str,
        confidence: str,
        stock_lots: int,
    ) -> tuple[str, str, str]:
        """依方向與信心決定股票/期貨操作及策略類型。"""
        if direction == "BULLISH":
            if confidence == "HIGH":
                stock_action = "BUY"
                futures_action = "BUY"
                hedge_type = "積極做多 + 期貨加碼"
            elif confidence == "MEDIUM":
                stock_action = "BUY" if stock_lots == 0 else "HOLD"
                futures_action = "NONE"
                hedge_type = "現貨做多" if stock_lots == 0 else "持股續抱"
            else:
                stock_action = "HOLD" if stock_lots > 0 else "NONE"
                futures_action = "NONE"
                hedge_type = "觀望偏多"
        elif direction == "BEARISH":
            if confidence == "HIGH":
                stock_action = "SELL"
                futures_action = "SELL"
                hedge_type = "現貨減碼 + 期貨避險"
            elif confidence == "MEDIUM":
                stock_action = "HOLD" if stock_lots > 0 else "NONE"
                futures_action = "SELL"
                hedge_type = "期貨避險" if stock_lots > 0 else "放空期貨"
            else:
                stock_action = "HOLD" if stock_lots > 0 else "NONE"
                futures_action = "NONE"
                hedge_type = "觀望偏空"
        else:
            stock_action = "HOLD" if stock_lots > 0 else "NONE"
            futures_action = "NONE"
            hedge_type = "中性觀望"

        return stock_action, futures_action, hedge_type

    # ── private: text builders ────────────────────────

    def _build_reasoning(
        self,
        *,
        code: str,
        name: str,
        chip_verdict: str,
        margin_change: int,
        institutional_net: int,
        basis_pct: float,
        foreign_futures_net: int,
        direction: str,
        confidence: str,
    ) -> str:
        direction_zh = {"BULLISH": "偏多", "BEARISH": "偏空", "NEUTRAL": "中性"}.get(
            direction, direction
        )
        lines = [f"{name}({code}) 綜合分析："]

        # 籌碼面
        chip_zh = {
            "bullish": "正面",
            "bearish": "負面",
            "neutral": "中性",
            "squeeze_alert": "軋空警戒",
            "margin_call_risk": "斷頭風險",
        }.get(chip_verdict, chip_verdict)
        margin_dir = "增加" if margin_change >= 0 else "減少"
        # institutional_net 是股數，轉為張數顯示
        inst_lots = abs(institutional_net) // 1000
        lines.append(
            f"籌碼面：融資{margin_dir} {abs(margin_change)} 張（{chip_zh}），"
            f"法人{'買超' if institutional_net >= 0 else '賣超'} {inst_lots:,} 張"
        )

        # 期貨面
        futures_parts: list[str] = []
        if basis_pct != 0:
            sign = "正" if basis_pct > 0 else "逆"
            futures_parts.append(f"台指期{sign}價差 {basis_pct:.2f}%")
        if foreign_futures_net != 0:
            side = "淨多" if foreign_futures_net > 0 else "淨空"
            futures_parts.append(f"外資期貨{side} {abs(foreign_futures_net):,} 口")
        if futures_parts:
            lines.append(f"期貨面：{'，'.join(futures_parts)}")
        else:
            lines.append("期貨面：資料暫無")

        lines.append(f"綜合判定：{direction_zh}（信心度 {confidence}）")
        return "\n".join(lines)

    def _build_risk_warning(self, direction: str, confidence: str) -> str:
        warnings: list[str] = []
        if confidence == "LOW":
            warnings.append("信號強度不足，建議觀望或輕倉操作")
        if direction == "BULLISH":
            warnings.append("注意追高風險，設定嚴格停損")
        elif direction == "BEARISH":
            warnings.append("空方行情中避免抄底，等待止穩訊號")
        warnings.append("期貨具槓桿風險，務必控制部位大小")
        return "；".join(warnings)

    def _build_action_steps(
        self,
        *,
        code: str,
        name: str,
        stock_action: str,
        futures_action: str,
        stock_lots: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> list[str]:
        steps: list[str] = []
        step_no = 1

        if stock_action == "BUY":
            steps.append(f"{step_no}. 買進 {name}({code})，參考進場價 {entry_price:.1f}")
            step_no += 1
        elif stock_action == "SELL":
            steps.append(f"{step_no}. 減碼或出清 {name}({code}) 現貨持股")
            step_no += 1
        elif stock_action == "HOLD" and stock_lots > 0:
            steps.append(f"{step_no}. 現貨持有 {stock_lots} 張 {name}({code})，續抱")
            step_no += 1

        if futures_action == "BUY":
            steps.append(f"{step_no}. 買進台指期或小台（近月合約）加碼多單")
            step_no += 1
        elif futures_action == "SELL":
            hedge_lots = max(1, stock_lots // 2) if stock_lots > 0 else 1
            steps.append(f"{step_no}. 賣出 {hedge_lots} 口小台（近月合約）避險")
            step_no += 1

        if entry_price > 0:
            steps.append(
                f"{step_no}. 停損：現貨跌破 {stop_loss:.1f}"
                f"（-{self._STOP_LOSS_PCT * 100:.0f}%），執行停損"
            )
            step_no += 1
            steps.append(
                f"{step_no}. 停利：現貨達 {take_profit:.1f}"
                f"（+{self._TAKE_PROFIT_PCT * 100:.0f}%），先獲利了結 50%"
            )
            step_no += 1

        steps.append(f"{step_no}. 每日監控：融資增減 > 1000 張時重新評估策略")
        return steps
