"""TWSE / TPEx 融資融券 + 借券資料擷取。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── helpers (獨立複製，不 import twse_bulk) ─────────────────────


def _safe_num(v: Any) -> float:
    if v is None or v == "--" or v == "" or v == "-":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _safe_int(v: Any) -> int:
    return int(_safe_num(v))


def _find_trading_date(start: date, max_lookback: int = 7) -> date:
    """向前找最近的交易日（跳過週末）。"""
    dt = start
    for _ in range(max_lookback):
        if dt.weekday() < 5:
            return dt
        dt -= timedelta(days=1)
    return start


# ── TWSE 融資融券 ───────────────────────────────────

_twse_margin_cache: dict[date, pd.DataFrame] = {}


def fetch_twse_margin_all(dt: date | None = None) -> pd.DataFrame:
    """取得 TWSE 全市場融資融券餘額（同日期快取）。

    非交易日自動往前找，最多 7 天。

    Returns DataFrame with columns:
        code, name, margin_buy, margin_sell, margin_balance, margin_limit,
        short_buy, short_sell, short_balance, short_limit
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _twse_margin_cache:
        return _twse_margin_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = candidate.strftime("%Y%m%d")

        try:
            resp = httpx.get(
                "https://www.twse.com.tw/exchangeReport/MI_MARGN",
                params={"response": "json", "date": date_str, "selectType": "ALL"},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TWSE MI_MARGN fetch failed for %s: %s", date_str, exc)
            continue

        if data.get("stat") != "OK":
            logger.info(
                "TWSE MI_MARGN stat=%s for %s, trying previous day",
                data.get("stat"),
                date_str,
            )
            continue

        # 找到有效交易日
        logger.info("TWSE margin: using trading date %s", candidate)
        break
    else:
        logger.warning("TWSE MI_MARGN: no valid trading date found within lookback")
        return pd.DataFrame()

    # 資料在 data 或 tables 中
    rows_data: list = data.get("data") or []
    if not rows_data:
        for tbl in data.get("tables", []):
            if isinstance(tbl, dict) and len(tbl.get("data", [])) > 50:
                rows_data = tbl["data"]
                break

    # MI_MARGN 欄位順序（ALL）：
    # [0]代號 [1]名稱
    # [2]融資買進 [3]融資賣出 [4]融資現金償還 [5]融資前日餘額 [6]融資今日餘額 [7]融資限額
    # [8]融券買進 [9]融券賣出 [10]融券現券償還 [11]融券前日餘額 [12]融券今日餘額 [13]融券限額
    # [14]資券互抵
    records: list[dict[str, Any]] = []
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            records.append({
                "code": code,
                "name": name,
                "margin_buy": _safe_int(row[2]),
                "margin_sell": _safe_int(row[3]),
                "margin_balance": _safe_int(row[6]),
                "margin_limit": _safe_int(row[7]),
                "short_buy": _safe_int(row[8]),
                "short_sell": _safe_int(row[9]),
                "short_balance": _safe_int(row[12]),
                "short_limit": _safe_int(row[13]),
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TWSE margin: fetched %d stocks for %s", len(df), date_str)
    _twse_margin_cache[start_dt] = df
    return df


# ── TPEx 融資融券 ───────────────────────────────────

_tpex_margin_cache: dict[date, pd.DataFrame] = {}


def fetch_tpex_margin_all(dt: date | None = None) -> pd.DataFrame:
    """取得 TPEx (上櫃) 全市場融資融券餘額（同日期快取）。

    Returns DataFrame with columns:
        code, name, margin_buy, margin_sell, margin_balance, margin_limit,
        short_buy, short_sell, short_balance, short_limit
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _tpex_margin_cache:
        return _tpex_margin_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        roc_year = candidate.year - 1911
        date_str = f"{roc_year}/{candidate.month:02d}/{candidate.day:02d}"

        try:
            resp = httpx.get(
                "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php",
                params={"l": "zh-tw", "d": date_str, "o": "json"},
                timeout=_TIMEOUT,
                headers=_HEADERS,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TPEx margin fetch failed for %s: %s", date_str, exc)
            continue

        # TPEx 回傳 aaData 或 tables
        rows_data: list = data.get("aaData") or []
        if not rows_data:
            for tbl in data.get("tables", []):
                if isinstance(tbl, dict) and len(tbl.get("data", [])) > 50:
                    rows_data = tbl["data"]
                    break

        if not rows_data:
            logger.info("TPEx margin: no data for %s, trying previous day", date_str)
            continue

        logger.info("TPEx margin: using trading date %s", candidate)
        break
    else:
        logger.warning("TPEx margin: no valid trading date found within lookback")
        return pd.DataFrame()

    # TPEx 融資融券欄位順序：
    # [0]代號 [1]名稱
    # [2]融資買進 [3]融資賣出 [4]融資現償 [5]融資前餘額 [6]融資今餘額 [7]融資限額 [8]融資使用率
    # [9]融券買進 [10]融券賣出 [11]融券現償 [12]融券前餘額 [13]融券今餘額 [14]融券限額 [15]融券使用率
    # [16]資券互抵 [17]備註
    records: list[dict[str, Any]] = []
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            records.append({
                "code": code,
                "name": name,
                "margin_buy": _safe_int(row[2]),
                "margin_sell": _safe_int(row[3]),
                "margin_balance": _safe_int(row[6]),
                "margin_limit": _safe_int(row[7]),
                "short_buy": _safe_int(row[9]),
                "short_sell": _safe_int(row[10]),
                "short_balance": _safe_int(row[13]),
                "short_limit": _safe_int(row[14]),
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TPEx margin: fetched %d stocks for %s", len(df), date_str)
    _tpex_margin_cache[start_dt] = df
    return df


# ── TWSE 借券 ──────────────────────────────────────

_twse_lending_cache: dict[date, pd.DataFrame] = {}


def fetch_twse_lending(dt: date | None = None) -> pd.DataFrame:
    """取得 TWSE 借券賣出餘額（同日期快取）。

    Returns DataFrame with columns:
        code, name, lending_balance, lending_volume
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _twse_lending_cache:
        return _twse_lending_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = candidate.strftime("%Y%m%d")

        try:
            resp = httpx.get(
                "https://www.twse.com.tw/SBL/TWT96U",
                params={"response": "json", "date": date_str},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TWSE TWT96U (lending) fetch failed for %s: %s", date_str, exc)
            continue

        if data.get("stat") != "OK":
            logger.info(
                "TWSE TWT96U stat=%s for %s, trying previous day",
                data.get("stat"),
                date_str,
            )
            continue

        logger.info("TWSE lending: using trading date %s", candidate)
        break
    else:
        logger.warning("TWSE TWT96U: no valid trading date found within lookback")
        return pd.DataFrame()

    rows_data: list = data.get("data") or []
    if not rows_data:
        for tbl in data.get("tables", []):
            if isinstance(tbl, dict) and len(tbl.get("data", [])) > 20:
                rows_data = tbl["data"]
                break

    # TWT96U 欄位：
    # [0]代號 [1]名稱 [2]當日賣出 [3]當日還券 [4]前日餘額 [5]今日餘額
    # [6]限額 [7]備註  (欄位可能依版本不同，取賣出與餘額)
    records: list[dict[str, Any]] = []
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            records.append({
                "code": code,
                "name": name,
                "lending_volume": _safe_int(row[2]),
                "lending_balance": _safe_int(row[5]),
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TWSE lending: fetched %d stocks for %s", len(df), date_str)
    _twse_lending_cache[start_dt] = df
    return df


# ── 全市場彙總 ─────────────────────────────────────


def fetch_margin_summary(dt: date | None = None) -> dict[str, float]:
    """全市場融資融券彙總：總餘額與增減。

    Returns:
        {
            "total_margin_balance": ...,
            "total_short_balance": ...,
            "margin_change": ...,
            "short_change": ...,
        }
    """
    try:
        twse = fetch_twse_margin_all(dt)
        tpex = fetch_tpex_margin_all(dt)
    except Exception as exc:
        logger.warning("fetch_margin_summary failed: %s", exc)
        return {}

    if twse.empty and tpex.empty:
        return {}

    combined = pd.concat([twse, tpex], ignore_index=True)

    total_margin = int(combined["margin_balance"].sum()) if "margin_balance" in combined.columns else 0
    total_short = int(combined["short_balance"].sum()) if "short_balance" in combined.columns else 0

    # 計算增減：今日餘額 - (餘額 - 買進 + 賣出) ≈ 買進 - 賣出
    margin_buy = int(combined["margin_buy"].sum()) if "margin_buy" in combined.columns else 0
    margin_sell = int(combined["margin_sell"].sum()) if "margin_sell" in combined.columns else 0
    short_buy = int(combined["short_buy"].sum()) if "short_buy" in combined.columns else 0
    short_sell = int(combined["short_sell"].sum()) if "short_sell" in combined.columns else 0

    return {
        "total_margin_balance": total_margin,
        "total_short_balance": total_short,
        "margin_change": margin_buy - margin_sell,
        "short_change": short_sell - short_buy,
    }
