"""統一資料管理 — 負責所有資料來源的取得、清洗與快取。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd
import yfinance as yf

from atlas.enums import MarketType
from atlas.exceptions import (
    AllSourcesExhaustedError,
    DataFormatError,
    DataSourceError,
    ValidationError,
)
from atlas.interfaces.infrastructure import IDataManager
from atlas.models.market_data import DailyBar

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.db import DatabaseManager

logger = logging.getLogger(__name__)

# TWSE API 常數
_TWSE_BASE = "https://www.twse.com.tw"
_TWSE_STOCK_DAY = f"{_TWSE_BASE}/exchangeReport/STOCK_DAY"
_TWSE_STOCK_DAY_ALL = f"{_TWSE_BASE}/exchangeReport/STOCK_DAY_ALL"
_TWSE_T86 = f"{_TWSE_BASE}/fund/T86"
_TWSE_MARGIN = f"{_TWSE_BASE}/exchangeReport/MI_MARGN"
_TPEX_BASE = "https://www.tpex.org.tw"

_CACHE_TTL_DAILY = 3600  # 1 小時
_CACHE_TTL_ALL = 1800  # 30 分鐘
_HTTP_TIMEOUT = 30.0


# 已知上櫃(OTC)股票代碼集合；TSE 查無資料時也可動態發現
_KNOWN_OTC_CODES: frozenset[str] = frozenset({
    "5269", "6488", "6669", "3293", "8069", "6147", "3529", "6770", "8454", "5871",
})


def _is_otc(code: str) -> bool:
    """判斷是否為上櫃股票（OTC）。"""
    return code in _KNOWN_OTC_CODES


def _tw_code_to_yf(code: str) -> str:
    """台股代碼轉 yfinance ticker（上市加 .TW，上櫃加 .TWO）。"""
    suffix = ".TWO" if _is_otc(code) else ".TW"
    return f"{code}{suffix}"


def _safe_decimal(value: Any) -> Decimal:
    """安全轉換為 Decimal，處理逗號與空值。"""
    if value is None or value == "--" or value == "":
        return Decimal("0")
    try:
        cleaned = str(value).replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _safe_int(value: Any) -> int:
    """安全轉換為 int。"""
    if value is None or value == "--" or value == "":
        return 0
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


class DataManager(IDataManager):
    """統一資料管理器，整合多來源資料存取。

    Responsibilities:
    1. 從多種資料源取得歷史行情 (TWSE API, yfinance)
    2. 取得法人/融資券/營收資料
    3. 寫入 PostgreSQL (via DatabaseManager)
    4. 快取熱資料 (via CacheManager)
    5. Fallback chain for data sources
    """

    def __init__(
        self,
        db: DatabaseManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._db = db
        self._cache = cache
        self._logger = logging.getLogger(__name__)

    # ──────────────────────────────────────────────
    # Public API — IDataManager
    # ──────────────────────────────────────────────

    async def fetch_daily_bars(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """取得歷史日 K 線，走 cache → DB → external source fallback。"""
        self._validate_code(code, market)

        # 1. Cache check
        cache_key = f"daily:{market}:{code}:{start_date}:{end_date}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached:
                self._logger.debug("Cache hit for %s", cache_key)
                return [self._dict_to_daily_bar(d) for d in cached]

        # 2. DB check
        bars = await self._load_from_db(code, market, start_date, end_date)
        if bars:
            self._logger.debug("DB hit for %s %s", code, market)
            if self._cache:
                await self._cache.set(
                    cache_key,
                    [self._daily_bar_to_dict(b) for b in bars],
                    _CACHE_TTL_DAILY,
                )
            return bars

        # 3. External source fallback chain
        bars = await self._fetch_with_fallback(code, market, start_date, end_date)

        # 4. Save to DB + cache
        if bars:
            saved = await self.save_daily_bars(bars)
            self._logger.info("Saved %d bars for %s to DB", saved, code)
            if self._cache:
                await self._cache.set(
                    cache_key,
                    [self._daily_bar_to_dict(b) for b in bars],
                    _CACHE_TTL_DAILY,
                )

        return bars

    async def fetch_daily_all(
        self,
        market: MarketType,
        trade_date: date,
    ) -> list[DailyBar]:
        """取得全市場當日收盤行情。"""
        cache_key = f"daily_all:{market}:{trade_date}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached:
                return [self._dict_to_daily_bar(d) for d in cached]

        if market == MarketType.TW:
            bars = await self._fetch_twse_all(trade_date)
        else:
            self._logger.warning("fetch_daily_all not yet supported for %s", market)
            return []

        if bars and self._cache:
            await self._cache.set(
                cache_key,
                [self._daily_bar_to_dict(b) for b in bars],
                _CACHE_TTL_ALL,
            )
        return bars

    async def fetch_institutional_flow(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """取得三大法人買賣超資料（TWSE T86 API）。"""
        self._validate_code(code, market)

        if market != MarketType.TW:
            self._logger.warning(
                "Institutional flow not yet supported for %s", market
            )
            return pd.DataFrame()

        try:
            records: list[dict[str, Any]] = []
            current = start_date
            while current <= end_date:
                date_str = current.strftime("%Y%m%d")
                params = {
                    "response": "json",
                    "date": date_str,
                    "selectType": "ALLBUT0999",
                }
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    resp = await client.get(_TWSE_T86, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                if "data" in data:
                    for row in data["data"]:
                        row_code = str(row[0]).strip()
                        if row_code == code:
                            records.append(
                                {
                                    "date": current,
                                    "foreign_buy": _safe_int(row[2]),
                                    "foreign_sell": _safe_int(row[3]),
                                    "foreign_net": _safe_int(row[4]),
                                    "trust_buy": _safe_int(row[5]),
                                    "trust_sell": _safe_int(row[6]),
                                    "trust_net": _safe_int(row[7]),
                                    "dealer_buy": _safe_int(row[8]),
                                    "dealer_sell": _safe_int(row[9]),
                                    "dealer_net": _safe_int(row[10]),
                                }
                            )
                            break

                current += timedelta(days=1)
                # 避免 TWSE rate limit
                await asyncio.sleep(3.0)

            if not records:
                return pd.DataFrame(
                    columns=[
                        "date", "foreign_buy", "foreign_sell", "trust_buy",
                        "trust_sell", "dealer_buy", "dealer_sell",
                        "foreign_net", "trust_net", "dealer_net",
                    ]
                )
            return pd.DataFrame(records)

        except httpx.HTTPError as exc:
            self._logger.error("TWSE T86 fetch failed: %s", exc)
            raise DataSourceError(
                f"Institutional flow fetch failed: {exc}", source="twse"
            ) from exc

    async def fetch_margin_trading(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """取得融資融券餘額資料（TWSE MI_MARGN API）。"""
        self._validate_code(code, market)

        if market != MarketType.TW:
            self._logger.warning("Margin trading not yet supported for %s", market)
            return pd.DataFrame()

        try:
            records: list[dict[str, Any]] = []
            current = start_date
            while current <= end_date:
                date_str = current.strftime("%Y%m%d")
                params = {
                    "response": "json",
                    "date": date_str,
                    "selectType": "ALL",
                }
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    resp = await client.get(_TWSE_MARGIN, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                # MI_MARGN 的 creditList
                credit_list = data.get("creditList", [])
                for row in credit_list:
                    row_code = str(row[0]).strip()
                    if row_code == code:
                        records.append(
                            {
                                "date": current,
                                "margin_balance": _safe_int(row[6]),
                                "margin_change": _safe_int(row[5]),
                                "short_balance": _safe_int(row[12]),
                                "short_change": _safe_int(row[11]),
                                "margin_short_ratio": (
                                    round(
                                        _safe_int(row[6]) / max(_safe_int(row[12]), 1),
                                        2,
                                    )
                                ),
                            }
                        )
                        break

                current += timedelta(days=1)
                await asyncio.sleep(3.0)

            if not records:
                return pd.DataFrame(
                    columns=[
                        "date", "margin_balance", "margin_change",
                        "short_balance", "short_change", "margin_short_ratio",
                    ]
                )
            return pd.DataFrame(records)

        except httpx.HTTPError as exc:
            self._logger.error("TWSE MI_MARGN fetch failed: %s", exc)
            raise DataSourceError(
                f"Margin trading fetch failed: {exc}", source="twse"
            ) from exc

    async def fetch_revenue(
        self,
        code: str,
        market: MarketType,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        """取得月營收資料（公開資訊觀測站）。"""
        self._validate_code(code, market)

        if market != MarketType.TW:
            self._logger.warning("Revenue fetch not yet supported for %s", market)
            return {}

        try:
            # 公開資訊觀測站 — 營收統計
            tw_year = year - 1911  # 轉民國年
            url = "https://mops.twse.com.tw/nas/t21/sii/t21sc03_{}_{}_0.html".format(
                tw_year, month
            )
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            # 嘗試用 pandas 解析 HTML 表格
            tables = pd.read_html(resp.text, encoding="utf-8")
            for table in tables:
                # 尋找包含股票代碼的表格
                for _, row in table.iterrows():
                    row_values = [str(v).strip() for v in row.values]
                    if code in row_values:
                        code_idx = row_values.index(code)
                        return {
                            "code": code,
                            "year": year,
                            "month": month,
                            "revenue": _safe_int(row_values[code_idx + 2])
                            if len(row_values) > code_idx + 2
                            else 0,
                            "yoy_growth": float(
                                row_values[code_idx + 5].replace(",", "")
                            )
                            if len(row_values) > code_idx + 5
                            else 0.0,
                            "mom_growth": float(
                                row_values[code_idx + 4].replace(",", "")
                            )
                            if len(row_values) > code_idx + 4
                            else 0.0,
                        }

            self._logger.warning("Revenue data not found for %s %d/%d", code, year, month)
            return {"code": code, "year": year, "month": month, "revenue": 0}

        except Exception as exc:
            self._logger.error("Revenue fetch failed for %s: %s", code, exc)
            raise DataSourceError(
                f"Revenue fetch failed: {exc}", source="mops"
            ) from exc

    async def fetch_quarterly_financials(
        self,
        code: str,
        market: MarketType,
        year: int,
        quarter: int,
    ) -> dict[str, Any]:
        """取得季財報資料（EPS、毛利率、營益率、稅後淨利、營業收入）。

        主要來源：公開資訊觀測站 (MOPS) ajax_t163sb04。
        Fallback：yfinance quarterly_financials。
        """
        self._validate_code(code, market)

        if market != MarketType.TW:
            self._logger.warning("Quarterly financials not yet supported for %s", market)
            return {}

        if not (1 <= quarter <= 4):
            raise ValidationError(
                f"quarter must be 1-4, got {quarter}", field="quarter"
            )

        tw_year = year - 1911  # 轉民國年
        empty: dict[str, Any] = {
            "code": code,
            "year": year,
            "quarter": quarter,
            "eps": None,
            "gross_margin": None,
            "operating_margin": None,
            "net_income": None,
            "revenue": None,
        }

        # ── 主要來源：MOPS HTML ──────────────────────────────────────────
        try:
            url = "https://mops.twse.com.tw/mops/web/ajax_t163sb04"
            post_data = (
                f"encodeURIComponent=1&step=1&firstin=1&off=1"
                f"&co_id={code}&year={tw_year}&season={quarter}"
            )
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    url,
                    content=post_data.encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()

            from io import StringIO
            tables = pd.read_html(StringIO(resp.text))
            result = dict(empty)

            for table in tables:
                str_table = table.astype(str)
                for _, row in str_table.iterrows():
                    row_vals = list(row.values)
                    label = row_vals[0] if row_vals else ""

                    # 每股盈餘
                    if "每股盈餘" in label and result["eps"] is None:
                        for v in row_vals[1:]:
                            try:
                                result["eps"] = float(v.replace(",", ""))
                                break
                            except (ValueError, AttributeError):
                                continue

                    # 營業收入
                    elif "營業收入" in label and result["revenue"] is None:
                        for v in row_vals[1:]:
                            try:
                                result["revenue"] = int(v.replace(",", ""))
                                break
                            except (ValueError, AttributeError):
                                continue

                    # 毛利率
                    elif "毛利率" in label and result["gross_margin"] is None:
                        for v in row_vals[1:]:
                            try:
                                result["gross_margin"] = float(v.replace(",", "").rstrip("%"))
                                break
                            except (ValueError, AttributeError):
                                continue

                    # 營益率 / 營業利益率
                    elif any(k in label for k in ("營益率", "營業利益率")) and result["operating_margin"] is None:
                        for v in row_vals[1:]:
                            try:
                                result["operating_margin"] = float(v.replace(",", "").rstrip("%"))
                                break
                            except (ValueError, AttributeError):
                                continue

                    # 稅後淨利 / 本期淨利
                    elif any(k in label for k in ("稅後淨利", "本期淨利", "本期稅後淨利")) and result["net_income"] is None:
                        for v in row_vals[1:]:
                            try:
                                result["net_income"] = int(v.replace(",", ""))
                                break
                            except (ValueError, AttributeError):
                                continue

            # 至少解析到一個欄位視為成功
            if any(result[k] is not None for k in ("eps", "revenue", "gross_margin", "operating_margin", "net_income")):
                self._logger.info("MOPS quarterly financials fetched for %s %dQ%d", code, year, quarter)
                return result

        except Exception as exc:
            self._logger.warning(
                "MOPS quarterly fetch failed for %s: %s — trying yfinance", code, exc
            )

        # ── Fallback：yfinance ────────────────────────────────────────────
        try:
            def _yf_fetch() -> dict[str, Any]:
                ticker = yf.Ticker(f"{code}.TW")
                info = ticker.info or {}
                qf = ticker.quarterly_financials  # columns=periods, index=line items

                res = dict(empty)
                res["eps"] = info.get("trailingEps") or info.get("forwardEps")

                if qf is not None and not qf.empty:
                    col = qf.columns[0]
                    idx_lower = [str(i).lower() for i in qf.index]

                    def _get(keywords: list[str]) -> float | None:
                        for kw in keywords:
                            matches = [i for i, n in enumerate(idx_lower) if kw in n]
                            if matches:
                                val = qf.iloc[matches[0]][col]
                                try:
                                    return float(val)
                                except (TypeError, ValueError):
                                    pass
                        return None

                    total_rev = _get(["total revenue", "operating revenue"])
                    gross = _get(["gross profit"])
                    op_income = _get(["operating income", "ebit"])
                    net = _get(["net income"])

                    res["revenue"] = int(total_rev) if total_rev else None
                    res["net_income"] = int(net) if net else None
                    if total_rev:
                        if gross is not None:
                            res["gross_margin"] = round(gross / total_rev * 100, 2)
                        if op_income is not None:
                            res["operating_margin"] = round(op_income / total_rev * 100, 2)

                return res

            yf_result = await asyncio.to_thread(_yf_fetch)
            self._logger.info("yfinance quarterly financials fetched for %s", code)
            return yf_result

        except Exception as exc:
            self._logger.error("yfinance quarterly fetch failed for %s: %s", code, exc)
            raise DataSourceError(
                f"Quarterly financials fetch failed for {code}: {exc}", source="yfinance"
            ) from exc

    async def save_daily_bars(self, bars: list[DailyBar]) -> int:
        """批次 upsert 日 K 線至 PostgreSQL。"""
        if not bars:
            return 0

        upsert_sql = """
            INSERT INTO daily_bars (
                code, market, trade_date, open_price, high, low, close,
                volume, amount, adj_close, turnover
            ) VALUES (
                :code, :market, :trade_date, :open_price, :high, :low, :close,
                :volume, :amount, :adj_close, :turnover
            )
            ON CONFLICT (code, market, trade_date)
            DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                amount = EXCLUDED.amount,
                adj_close = EXCLUDED.adj_close,
                turnover = EXCLUDED.turnover
        """
        count = 0
        try:
            async with self._db.session() as sess:
                from sqlalchemy import text

                for bar in bars:
                    params = {
                        "code": bar.code,
                        "market": bar.market.value,
                        "trade_date": bar.trade_date,
                        "open_price": str(bar.open_price),
                        "high": str(bar.high),
                        "low": str(bar.low),
                        "close": str(bar.close),
                        "volume": bar.volume,
                        "amount": str(bar.amount),
                        "adj_close": str(bar.adj_close) if bar.adj_close else None,
                        "turnover": bar.turnover,
                    }
                    await sess.execute(text(upsert_sql), params)
                    count += 1
            return count
        except Exception as exc:
            self._logger.error("save_daily_bars failed: %s", exc)
            raise DataSourceError(
                f"Failed to save daily bars: {exc}", source="postgresql"
            ) from exc

    async def validate_data_completeness(
        self,
        market: MarketType,
        trade_date: date,
    ) -> dict[str, bool]:
        """校驗盤後資料完整性。"""
        result: dict[str, bool] = {
            "daily_price": False,
            "institutional": False,
            "margin": False,
            "revenue": False,
        }

        try:
            # 檢查日 K 是否有資料
            count_sql = """
                SELECT COUNT(*) FROM daily_bars
                WHERE market = :market AND trade_date = :trade_date
            """
            from sqlalchemy import text

            res = await self._db.execute(
                count_sql,
                {"market": market.value, "trade_date": trade_date},
            )
            row = res.scalar()
            result["daily_price"] = (row or 0) > 0

        except Exception as exc:
            self._logger.warning("Data completeness check failed: %s", exc)

        return result

    # ──────────────────────────────────────────────
    # Fallback chain
    # ──────────────────────────────────────────────

    async def _fetch_with_fallback(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """Fallback chain: yfinance → TWSE → raise AllSourcesExhaustedError。"""
        tried: list[str] = []
        errors: list[str] = []

        # Source 1: yfinance
        try:
            bars = await self._fetch_via_yfinance(code, market, start_date, end_date)
            if bars:
                self._logger.info(
                    "Fetched %d bars for %s via yfinance", len(bars), code
                )
                return bars
        except Exception as exc:
            tried.append("yfinance")
            errors.append(f"yfinance: {exc}")
            self._logger.warning("yfinance failed for %s: %s", code, exc)

        # Source 2: TWSE (台股 only)
        if market == MarketType.TW:
            try:
                bars = await self._fetch_via_twse(code, start_date, end_date)
                if bars:
                    self._logger.info(
                        "Fetched %d bars for %s via TWSE", len(bars), code
                    )
                    return bars
            except Exception as exc:
                tried.append("twse")
                errors.append(f"twse: {exc}")
                self._logger.warning("TWSE failed for %s: %s", code, exc)

        raise AllSourcesExhaustedError(
            message=f"All sources failed for {code}: {'; '.join(errors)}",
            tried_sources=tried,
        )

    # ──────────────────────────────────────────────
    # Concrete fetchers
    # ──────────────────────────────────────────────

    async def _fetch_via_yfinance(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """使用 yfinance 取得歷史日 K 線。"""
        ticker_symbol = (
            _tw_code_to_yf(code) if market == MarketType.TW else code
        )

        # yfinance 是同步 API，用 asyncio.to_thread 避免阻塞
        def _download() -> pd.DataFrame:
            ticker = yf.Ticker(ticker_symbol)
            # end_date + 1 day because yfinance end is exclusive
            df = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                auto_adjust=False,
            )
            return df

        df = await asyncio.to_thread(_download)

        if df is None or df.empty:
            raise DataSourceError(
                f"yfinance returned no data for {ticker_symbol}",
                source="yfinance",
            )

        bars: list[DailyBar] = []
        for idx, row in df.iterrows():
            trade_date_val = idx.date() if hasattr(idx, "date") else idx
            bars.append(
                DailyBar(
                    code=code,
                    market=market,
                    trade_date=trade_date_val,
                    open_price=_safe_decimal(row.get("Open")),
                    high=_safe_decimal(row.get("High")),
                    low=_safe_decimal(row.get("Low")),
                    close=_safe_decimal(row.get("Close")),
                    volume=_safe_int(row.get("Volume")),
                    amount=Decimal("0"),  # yfinance 不提供成交金額
                    adj_close=_safe_decimal(row.get("Adj Close")),
                    turnover=None,
                )
            )

        bars.sort(key=lambda b: b.trade_date)
        return bars

    async def _fetch_via_twse(
        self,
        code: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """使用 TWSE STOCK_DAY API 取得台股歷史日 K 線。

        TWSE API 每次回傳一個月的資料，需逐月查詢。
        """
        bars: list[DailyBar] = []
        current = start_date.replace(day=1)

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            while current <= end_date:
                date_str = current.strftime("%Y%m%d")
                params = {
                    "response": "json",
                    "date": date_str,
                    "stockNo": code,
                }

                try:
                    resp = await client.get(_TWSE_STOCK_DAY, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as exc:
                    raise DataSourceError(
                        f"TWSE STOCK_DAY request failed: {exc}",
                        source="twse",
                    ) from exc
                except Exception as exc:
                    raise DataFormatError(
                        f"TWSE STOCK_DAY response parse failed: {exc}",
                        source="twse",
                    ) from exc

                if "data" not in data:
                    self._logger.debug(
                        "No TWSE data for %s on %s", code, date_str
                    )
                else:
                    for row in data["data"]:
                        # row: [日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數]
                        try:
                            # 民國年日期 "112/01/03"
                            parts = str(row[0]).strip().split("/")
                            tw_year = int(parts[0])
                            ad_year = tw_year + 1911
                            trade_d = date(ad_year, int(parts[1]), int(parts[2]))
                        except (ValueError, IndexError):
                            continue

                        if trade_d < start_date or trade_d > end_date:
                            continue

                        bars.append(
                            DailyBar(
                                code=code,
                                market=MarketType.TW,
                                trade_date=trade_d,
                                open_price=_safe_decimal(row[3]),
                                high=_safe_decimal(row[4]),
                                low=_safe_decimal(row[5]),
                                close=_safe_decimal(row[6]),
                                volume=_safe_int(row[1]),
                                amount=_safe_decimal(row[2]),
                                adj_close=None,
                                turnover=None,
                            )
                        )

                # 前進一個月
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)

                # 避免 TWSE rate limit（每 5 秒一次）
                await asyncio.sleep(3.0)

        if not bars:
            raise DataSourceError(
                f"TWSE returned no data for {code} ({start_date} ~ {end_date})",
                source="twse",
            )

        bars.sort(key=lambda b: b.trade_date)
        return bars

    async def _fetch_twse_all(self, trade_date: date) -> list[DailyBar]:
        """TWSE STOCK_DAY_ALL — 取得全市場當日收盤行情。"""
        date_str = trade_date.strftime("%Y%m%d")
        params = {"response": "json", "date": date_str}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(_TWSE_STOCK_DAY_ALL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            self._logger.error("TWSE STOCK_DAY_ALL failed: %s", exc)
            raise DataSourceError(
                f"TWSE all-market fetch failed: {exc}", source="twse"
            ) from exc

        bars: list[DailyBar] = []
        for row in data.get("data", []):
            try:
                bars.append(
                    DailyBar(
                        code=str(row[0]).strip(),
                        market=MarketType.TW,
                        trade_date=trade_date,
                        open_price=_safe_decimal(row[4]),
                        high=_safe_decimal(row[5]),
                        low=_safe_decimal(row[6]),
                        close=_safe_decimal(row[7]),
                        volume=_safe_int(row[2]),
                        amount=_safe_decimal(row[3]),
                        adj_close=None,
                        turnover=None,
                    )
                )
            except (IndexError, ValueError) as exc:
                self._logger.debug("Skipping malformed row: %s", exc)
                continue

        self._logger.info(
            "TWSE ALL fetched %d bars for %s", len(bars), trade_date
        )
        return bars

    # ──────────────────────────────────────────────
    # DB helpers
    # ──────────────────────────────────────────────

    async def _load_from_db(
        self,
        code: str,
        market: MarketType,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        """從 PostgreSQL 載入日 K 線。"""
        sql = """
            SELECT code, market, trade_date, open_price, high, low, close,
                   volume, amount, adj_close, turnover
            FROM daily_bars
            WHERE code = :code
              AND market = :market
              AND trade_date BETWEEN :start_date AND :end_date
            ORDER BY trade_date ASC
        """
        try:
            from sqlalchemy import text

            result = await self._db.execute(
                sql,
                {
                    "code": code,
                    "market": market.value,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            rows = result.fetchall()
            if not rows:
                return []

            return [
                DailyBar(
                    code=r[0],
                    market=MarketType(r[1]),
                    trade_date=r[2],
                    open_price=Decimal(str(r[3])),
                    high=Decimal(str(r[4])),
                    low=Decimal(str(r[5])),
                    close=Decimal(str(r[6])),
                    volume=int(r[7]),
                    amount=Decimal(str(r[8])),
                    adj_close=Decimal(str(r[9])) if r[9] else None,
                    turnover=float(r[10]) if r[10] else None,
                )
                for r in rows
            ]
        except Exception as exc:
            self._logger.warning("DB load failed for %s: %s", code, exc)
            return []

    # ──────────────────────────────────────────────
    # Validation helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _validate_code(code: str, market: MarketType) -> None:
        """驗證股票代碼格式。"""
        if not code or not code.strip():
            raise ValidationError("Stock code cannot be empty", field="code")

        if market == MarketType.TW:
            cleaned = code.strip()
            if not (4 <= len(cleaned) <= 6) or not cleaned.isdigit():
                raise ValidationError(
                    f"Invalid TW stock code: {code} (expected 4-6 digits)",
                    field="code",
                )
        elif market == MarketType.US:
            cleaned = code.strip().upper()
            if not (1 <= len(cleaned) <= 5) or not cleaned.isalpha():
                raise ValidationError(
                    f"Invalid US stock code: {code} (expected 1-5 letters)",
                    field="code",
                )

    # ──────────────────────────────────────────────
    # Serialization helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _daily_bar_to_dict(bar: DailyBar) -> dict[str, Any]:
        """DailyBar → dict（用於 cache 序列化）。"""
        return {
            "code": bar.code,
            "market": bar.market.value,
            "trade_date": bar.trade_date.isoformat(),
            "open_price": str(bar.open_price),
            "high": str(bar.high),
            "low": str(bar.low),
            "close": str(bar.close),
            "volume": bar.volume,
            "amount": str(bar.amount),
            "adj_close": str(bar.adj_close) if bar.adj_close else None,
            "turnover": bar.turnover,
        }

    @staticmethod
    def _dict_to_daily_bar(d: dict[str, Any]) -> DailyBar:
        """dict → DailyBar（從 cache 反序列化）。"""
        return DailyBar(
            code=d["code"],
            market=MarketType(d["market"]),
            trade_date=date.fromisoformat(d["trade_date"]),
            open_price=Decimal(d["open_price"]),
            high=Decimal(d["high"]),
            low=Decimal(d["low"]),
            close=Decimal(d["close"]),
            volume=int(d["volume"]),
            amount=Decimal(d["amount"]),
            adj_close=Decimal(d["adj_close"]) if d.get("adj_close") else None,
            turnover=float(d["turnover"]) if d.get("turnover") else None,
        )
