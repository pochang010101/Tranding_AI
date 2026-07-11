"""智慧選股引擎 — 全市場掃描 + 多條件篩選 + 標籤化輸出。

篩選邏輯：
1. 去除處置股、水餃股 (<$10)、冷門股 (<500張)
2. 法人面：外資/投信買超
3. 量能面：成交量突增
4. 價格面：站上均線、突破近高
5. 輸出標籤化結果供盤中雷達使用
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ScreenerHit:
    """單支股票的選股結果。"""
    code: str
    name: str
    close: float
    change_pct: float
    volume_lots: int
    foreign_net: int = 0       # 外資淨買賣 (股)
    trust_net: int = 0         # 投信淨買賣 (股)
    dealer_net: int = 0        # 自營淨買賣 (股)
    total_inst_net: int = 0    # 三大法人合計
    foreign_net_lots: int = 0  # 外資淨買賣 (張)
    trust_net_lots: int = 0    # 投信淨買賣 (張)
    tags: list[str] = field(default_factory=list)
    score: float = 0.0


class SmartScreener:
    """全市場智慧選股引擎。"""

    def __init__(
        self,
        min_price: float = 10.0,
        min_volume_lots: int = 500,
        exclude_disposition: bool = True,
    ) -> None:
        self.min_price = min_price
        self.min_volume_lots = min_volume_lots
        self.exclude_disposition = exclude_disposition

    def scan(self, dt: date | None = None) -> list[ScreenerHit]:
        """執行全市場掃描。

        Steps:
        1. 取得全市場行情 (TWSE + TPEx)
        2. 取得三大法人買賣超
        3. 取得處置股清單
        4. Pre-filter (去除水餃/冷門/處置)
        5. 計算標籤與評分
        6. 排序回傳
        """
        from atlas.infrastructure.twse_bulk import (
            fetch_disposition_list,
            fetch_tpex_daily_all,
            fetch_tpex_institutional,
            fetch_twse_daily_all,
            fetch_twse_institutional,
        )

        # 1. 取得行情 (TWSE + TPEx)
        df_twse = fetch_twse_daily_all(dt)
        df_tpex = fetch_tpex_daily_all(dt)
        df_daily = pd.concat([df_twse, df_tpex], ignore_index=True) if not df_tpex.empty else df_twse

        if df_daily.empty:
            logger.warning("No daily data available")
            return []

        # 2. 取得法人資料
        df_inst_twse = fetch_twse_institutional(dt)
        df_inst_tpex = fetch_tpex_institutional(dt)
        df_inst = pd.concat([df_inst_twse, df_inst_tpex], ignore_index=True) if not df_inst_tpex.empty else df_inst_twse

        # 3. 處置股清單
        disposition = fetch_disposition_list() if self.exclude_disposition else set()

        # 4. Pre-filter
        df_daily = df_daily[
            (df_daily["close"] >= self.min_price)
            & (df_daily["volume_lots"] >= self.min_volume_lots)
        ].copy()

        if self.exclude_disposition and disposition:
            df_daily = df_daily[~df_daily["code"].isin(disposition)]

        logger.info("After pre-filter: %d stocks", len(df_daily))

        # 5. Merge institutional data
        if not df_inst.empty:
            inst_cols = ["code", "foreign_net", "trust_net", "dealer_net", "total_net"]
            available_cols = [c for c in inst_cols if c in df_inst.columns]
            df_merged = df_daily.merge(df_inst[available_cols], on="code", how="left")
        else:
            df_merged = df_daily.copy()
            for col in ["foreign_net", "trust_net", "dealer_net", "total_net"]:
                df_merged[col] = 0

        df_merged = df_merged.fillna(0)

        # 6. 計算標籤與評分
        results = []
        for _, row in df_merged.iterrows():
            tags = []
            score = 0.0

            close = float(row["close"])
            vol_lots = int(row["volume_lots"])
            change_pct = float(row.get("change_pct", 0))
            foreign_net = int(row.get("foreign_net", 0))
            trust_net = int(row.get("trust_net", 0))
            dealer_net = int(row.get("dealer_net", 0))
            total_net = int(row.get("total_net", 0))

            # 法人面
            foreign_lots = foreign_net // 1000
            trust_lots = trust_net // 1000
            if foreign_net > 0:
                tags.append("外資買超")
                score += 20
                if foreign_lots >= 500:
                    tags.append("外資大買")
                    score += 10
            if trust_net > 0:
                tags.append("投信買超")
                score += 25  # 投信買超比外資更有指標性
                if trust_lots >= 100:
                    tags.append("投信大買")
                    score += 10
            if foreign_net > 0 and trust_net > 0:
                tags.append("雙法人")
                score += 15

            # 量能面
            if vol_lots >= 3000:
                tags.append("大量")
                score += 10
            if vol_lots >= 10000:
                tags.append("爆量")
                score += 5

            # 價格面
            if change_pct >= 3.0:
                tags.append("強勢")
                score += 15
            elif change_pct >= 1.0:
                tags.append("上漲")
                score += 5
            elif change_pct <= -3.0:
                tags.append("弱勢")
                score -= 10

            # 漲停 / 跌停
            if change_pct >= 9.5:
                tags.append("漲停")
                score += 5
            elif change_pct <= -9.5:
                tags.append("跌停")
                score -= 20

            # 只保留有標籤的（至少符合一個正面條件）
            if not tags or score <= 0:
                continue

            results.append(ScreenerHit(
                code=str(row["code"]),
                name=str(row["name"]),
                close=close,
                change_pct=change_pct,
                volume_lots=vol_lots,
                foreign_net=foreign_net,
                trust_net=trust_net,
                dealer_net=dealer_net,
                total_inst_net=total_net,
                foreign_net_lots=foreign_lots,
                trust_net_lots=trust_lots,
                tags=tags,
                score=score,
            ))

        # 按分數排序
        results.sort(key=lambda x: x.score, reverse=True)
        logger.info("Smart screener: %d hits", len(results))
        return results

    def scan_to_dataframe(self, dt: date | None = None) -> pd.DataFrame:
        """掃描並回傳 DataFrame 格式（供 UI 使用）。"""
        hits = self.scan(dt)
        if not hits:
            return pd.DataFrame()

        rows = []
        for i, h in enumerate(hits, 1):
            rows.append({
                "排名": i,
                "代碼": h.code,
                "名稱": h.name,
                "收盤": h.close,
                "漲跌%": h.change_pct,
                "成交量(張)": h.volume_lots,
                "外資(張)": h.foreign_net_lots,
                "投信(張)": h.trust_net_lots,
                "法人合計(張)": h.total_inst_net // 1000,
                "選股分數": h.score,
                "訊號標籤": " | ".join(h.tags),
            })
        return pd.DataFrame(rows)
