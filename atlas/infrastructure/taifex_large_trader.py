"""TAIFEX 大額交易人未沖銷部位擷取與封裝。

複用 taifex_data.fetch_top10_traders() 取得前五大/前十大資料，
封裝為 LargeTraderData dataclass 供分析模組使用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from atlas.infrastructure.taifex_data import fetch_top10_traders

logger = logging.getLogger(__name__)


@dataclass
class LargeTraderData:
    """大額交易人未沖銷部位資料。"""

    date: str
    contract: str  # "TX" 台指期
    top5_buy: int  # 前五大交易人買方未平倉
    top5_sell: int  # 前五大交易人賣方未平倉
    top10_buy: int  # 前十大交易人買方未平倉
    top10_sell: int  # 前十大交易人賣方未平倉
    top5_buy_pct: float  # 前五大買方佔全市場比例 (%)
    top5_sell_pct: float  # 前五大賣方佔全市場比例 (%)
    top10_buy_pct: float  # 前十大買方佔全市場比例 (%)
    top10_sell_pct: float  # 前十大賣方佔全市場比例 (%)
    retail_buy_pct: float  # 散戶買方比例 (100 - top10_buy_pct)
    retail_sell_pct: float  # 散戶賣方比例 (100 - top10_sell_pct)


class LargeTraderFetcher:
    """從期交所取得大額交易人資料並封裝為 LargeTraderData。"""

    def fetch(self, query_date: str | date | None = None) -> LargeTraderData | None:
        """擷取指定日期的大額交易人資料。

        Args:
            query_date: 查詢日期，接受 "YYYY-MM-DD" 字串或 date 物件，
                        None 則自動找最近交易日。

        Returns:
            LargeTraderData 或 None（無資料時）。
        """
        dt = self._parse_date(query_date)
        df = fetch_top10_traders(dt)

        if df.empty:
            logger.warning("LargeTraderFetcher: 無大額交易人資料 (%s)", dt)
            return None

        return self._dataframe_to_model(df, dt)

    def _parse_date(self, query_date: str | date | None) -> date | None:
        """將各種日期格式轉為 date 物件。"""
        if query_date is None:
            return None
        if isinstance(query_date, date):
            return query_date
        # 支援 "YYYY-MM-DD" 或 "YYYY/MM/DD"
        date_str = str(query_date).replace("/", "-")
        try:
            parts = date_str.split("-")
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            logger.warning("LargeTraderFetcher: 無法解析日期 '%s'", query_date)
            return None

    def _dataframe_to_model(
        self, df: pd.DataFrame, dt: date | None
    ) -> LargeTraderData | None:
        """將 fetch_top10_traders 回傳的 DataFrame 轉為 LargeTraderData。

        DataFrame 預期欄位: category, buy_position, sell_position, buy_pct, sell_pct
        category 值: "前五大", "前十大", "全市場"
        """
        # TODO: 確認實際 API 回應格式，以下根據 taifex_data.fetch_top10_traders 結構
        if df.empty or "category" not in df.columns:
            logger.warning("LargeTraderFetcher: DataFrame 為空或缺少 category 欄位")
            return None

        top5_row = df[df["category"] == "前五大"]
        top10_row = df[df["category"] == "前十大"]

        if top5_row.empty and top10_row.empty:
            logger.warning("LargeTraderFetcher: DataFrame 中無前五大/前十大資料")
            return None

        # 前五大
        top5_buy = int(top5_row.iloc[0]["buy_position"]) if not top5_row.empty else 0
        top5_sell = int(top5_row.iloc[0]["sell_position"]) if not top5_row.empty else 0
        top5_buy_pct = float(top5_row.iloc[0]["buy_pct"]) if not top5_row.empty else 0.0
        top5_sell_pct = float(top5_row.iloc[0]["sell_pct"]) if not top5_row.empty else 0.0

        # 前十大
        top10_buy = int(top10_row.iloc[0]["buy_position"]) if not top10_row.empty else 0
        top10_sell = (
            int(top10_row.iloc[0]["sell_position"]) if not top10_row.empty else 0
        )
        top10_buy_pct = (
            float(top10_row.iloc[0]["buy_pct"]) if not top10_row.empty else 0.0
        )
        top10_sell_pct = (
            float(top10_row.iloc[0]["sell_pct"]) if not top10_row.empty else 0.0
        )

        # 散戶 = 全市場 - 前十大
        retail_buy_pct = max(0.0, 100.0 - top10_buy_pct)
        retail_sell_pct = max(0.0, 100.0 - top10_sell_pct)

        date_str = dt.isoformat() if dt else ""

        return LargeTraderData(
            date=date_str,
            contract="TX",
            top5_buy=top5_buy,
            top5_sell=top5_sell,
            top10_buy=top10_buy,
            top10_sell=top10_sell,
            top5_buy_pct=top5_buy_pct,
            top5_sell_pct=top5_sell_pct,
            top10_buy_pct=top10_buy_pct,
            top10_sell_pct=top10_sell_pct,
            retail_buy_pct=retail_buy_pct,
            retail_sell_pct=retail_sell_pct,
        )
