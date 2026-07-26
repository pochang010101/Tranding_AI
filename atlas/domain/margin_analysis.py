"""融資融券籌碼分析 — 券資比、融資維持率、斷頭警戒、趨勢判斷。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarginSignal:
    """融資融券分析結果。"""

    code: str
    name: str
    margin_balance: int  # 融資餘額（張）
    short_balance: int  # 融券餘額（張）
    lending_balance: int  # 借券賣出餘額（張）
    margin_usage_pct: float  # 融資使用率 %
    short_usage_pct: float  # 融券使用率 %
    short_margin_ratio: float  # 券資比 %
    margin_maintenance: float  # 融資維持率 %（需股價）
    margin_change: int  # 融資增減（張）
    short_change: int  # 融券增減（張）
    verdict: str  # 判定：bullish / bearish / neutral / squeeze_alert / margin_call_risk
    detail: str  # 說明文字


class MarginAnalyzer:
    """融資融券籌碼分析引擎。"""

    # 閾值常數
    SQUEEZE_RATIO_THRESHOLD = 30.0  # 券資比軋空警戒線 %
    MARGIN_CALL_THRESHOLD = 130.0  # 融資維持率斷頭線 %
    LARGE_CHANGE_THRESHOLD = 200  # 大量增減判定（張）

    def analyze_single(
        self,
        code: str,
        name: str,
        margin_balance: int,
        margin_limit: int,
        short_balance: int,
        short_limit: int,
        lending_balance: int = 0,
        margin_change: int = 0,
        short_change: int = 0,
        current_price: float = 0,
        margin_cost: float = 0,
    ) -> MarginSignal:
        """分析單一個股融資融券狀況。"""
        margin_usage_pct = (
            (margin_balance / margin_limit * 100) if margin_limit > 0 else 0.0
        )
        short_usage_pct = (
            (short_balance / short_limit * 100) if short_limit > 0 else 0.0
        )
        short_margin_ratio = (
            (short_balance / margin_balance * 100) if margin_balance > 0 else 0.0
        )
        margin_maintenance = (
            (current_price * margin_balance * 1000 / margin_cost * 100)
            if margin_cost > 0
            else 0.0
        )

        # 判定邏輯（優先順序）
        verdict, detail = self._determine_verdict(
            short_margin_ratio=short_margin_ratio,
            margin_maintenance=margin_maintenance,
            margin_cost=margin_cost,
            margin_change=margin_change,
            short_change=short_change,
        )

        return MarginSignal(
            code=code,
            name=name,
            margin_balance=margin_balance,
            short_balance=short_balance,
            lending_balance=lending_balance,
            margin_usage_pct=round(margin_usage_pct, 2),
            short_usage_pct=round(short_usage_pct, 2),
            short_margin_ratio=round(short_margin_ratio, 2),
            margin_maintenance=round(margin_maintenance, 2),
            margin_change=margin_change,
            short_change=short_change,
            verdict=verdict,
            detail=detail,
        )

    def _determine_verdict(
        self,
        *,
        short_margin_ratio: float,
        margin_maintenance: float,
        margin_cost: float,
        margin_change: int,
        short_change: int,
    ) -> tuple[str, str]:
        """依優先順序判定融資融券訊號。"""
        # 1. 券資比過高 → 軋空警戒
        if short_margin_ratio > self.SQUEEZE_RATIO_THRESHOLD:
            return (
                "squeeze_alert",
                f"券資比 {short_margin_ratio:.1f}% 超過 {self.SQUEEZE_RATIO_THRESHOLD:.0f}%，具軋空潛力",
            )

        # 2. 融資維持率逼近斷頭線（需有 margin_cost 才有意義）
        if margin_cost > 0 and margin_maintenance < self.MARGIN_CALL_THRESHOLD:
            return (
                "margin_call_risk",
                f"融資維持率 {margin_maintenance:.0f}%，逼近 {self.MARGIN_CALL_THRESHOLD:.0f}% 斷頭線",
            )

        # 3. 融資增加 + 融券減少 → 散戶追多（偏空）
        if (
            margin_change > self.LARGE_CHANGE_THRESHOLD
            and short_change < 0
        ):
            return (
                "bearish",
                f"融資增加 {margin_change} 張 + 融券減少，散戶追多警戒",
            )

        # 4. 融資大減 + 融券增加 → 籌碼洗清（偏多）
        if (
            margin_change < -self.LARGE_CHANGE_THRESHOLD
            and short_change > 0
        ):
            return (
                "bullish",
                f"融資大減 {abs(margin_change)} 張，籌碼洗清，偏多",
            )

        # 5. 其他
        return ("neutral", "融資融券變化平穩，無明顯訊號")

    def analyze_batch(
        self,
        margin_df: pd.DataFrame,
        lending_df: pd.DataFrame | None = None,
    ) -> list[MarginSignal]:
        """批次分析整個 DataFrame。

        預期 margin_df 欄位：
            code, name, margin_balance, margin_limit,
            short_balance, short_limit,
            margin_change, short_change,
            current_price (optional), margin_cost (optional)
        lending_df 欄位（optional）：
            code, lending_balance
        """
        if margin_df.empty:
            return []

        # 建立借券餘額查詢表
        lending_map: dict[str, int] = {}
        if lending_df is not None and not lending_df.empty:
            for _, row in lending_df.iterrows():
                lending_map[str(row.get("code", ""))] = int(
                    row.get("lending_balance", 0)
                )

        results: list[MarginSignal] = []
        for _, row in margin_df.iterrows():
            code = str(row.get("code", ""))
            signal = self.analyze_single(
                code=code,
                name=str(row.get("name", "")),
                margin_balance=int(row.get("margin_balance", 0)),
                margin_limit=int(row.get("margin_limit", 0)),
                short_balance=int(row.get("short_balance", 0)),
                short_limit=int(row.get("short_limit", 0)),
                lending_balance=lending_map.get(code, 0),
                margin_change=int(row.get("margin_change", 0)),
                short_change=int(row.get("short_change", 0)),
                current_price=float(row.get("current_price", 0)),
                margin_cost=float(row.get("margin_cost", 0)),
            )
            results.append(signal)

        logger.info("批次分析完成，共 %d 檔", len(results))
        return results

    def market_summary(self, margin_df: pd.DataFrame) -> dict[str, Any]:
        """全市場融資融券彙總統計。"""
        if margin_df.empty:
            return {
                "total_margin_balance": 0,
                "total_short_balance": 0,
                "total_margin_change": 0,
                "total_short_change": 0,
                "market_short_margin_ratio": 0.0,
                "top_margin_increase": [],
                "top_margin_decrease": [],
                "top_short_increase": [],
                "top_squeeze_candidates": [],
            }

        total_margin = int(margin_df["margin_balance"].sum())
        total_short = int(margin_df["short_balance"].sum())
        total_margin_change = int(margin_df["margin_change"].sum())
        total_short_change = int(margin_df["short_change"].sum())
        market_ratio = (total_short / total_margin * 100) if total_margin > 0 else 0.0

        # 融資增加 top 10
        top_margin_inc = (
            margin_df.nlargest(10, "margin_change")[["code", "name", "margin_change"]]
            .to_dict("records")
        )

        # 融資減少 top 10（取 margin_change 最小的 10 筆）
        top_margin_dec = (
            margin_df.nsmallest(10, "margin_change")[["code", "name", "margin_change"]]
            .to_dict("records")
        )

        # 融券增加 top 10
        top_short_inc = (
            margin_df.nlargest(10, "short_change")[["code", "name", "short_change"]]
            .to_dict("records")
        )

        # 券資比 top 10（需先計算）
        df = margin_df.copy()
        df["short_margin_ratio"] = df.apply(
            lambda r: (r["short_balance"] / r["margin_balance"] * 100)
            if r["margin_balance"] > 0
            else 0.0,
            axis=1,
        )
        top_squeeze = (
            df.nlargest(10, "short_margin_ratio")[
                ["code", "name", "short_margin_ratio"]
            ]
            .to_dict("records")
        )

        return {
            "total_margin_balance": total_margin,
            "total_short_balance": total_short,
            "total_margin_change": total_margin_change,
            "total_short_change": total_short_change,
            "market_short_margin_ratio": round(market_ratio, 2),
            "top_margin_increase": top_margin_inc,
            "top_margin_decrease": top_margin_dec,
            "top_short_increase": top_short_inc,
            "top_squeeze_candidates": top_squeeze,
        }
