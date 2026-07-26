"""TAIFEX（台灣期交所）期貨/選擇權資料擷取。"""

from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from io import StringIO
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── helpers ───────────────────────────────────────────


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


def _taifex_date_str(dt: date) -> str:
    """TAIFEX 日期格式：2026/07/25。"""
    return dt.strftime("%Y/%m/%d")


def _try_read_html(text: str) -> list[pd.DataFrame]:
    """嘗試 pd.read_html，Python 3.14 相容（StringIO）。"""
    try:
        return pd.read_html(StringIO(text))
    except Exception:
        return []


def _try_read_csv(text: str) -> list[list[str]]:
    """CSV fallback 解析。"""
    try:
        reader = csv.reader(StringIO(text))
        return [row for row in reader if row]
    except Exception:
        return []


def _decode_response(resp: httpx.Response) -> str:
    """嘗試 big5 → utf-8 解碼。"""
    for enc in ("big5", "utf-8", "cp950"):
        try:
            resp.encoding = enc
            return resp.text
        except Exception:
            continue
    return resp.text


# ── 1. 台指期每日行情 ─────────────────────────────────

_futures_daily_cache: dict[date, pd.DataFrame] = {}


def fetch_futures_daily(dt: date | None = None) -> pd.DataFrame:
    """台指期/小台每日行情。

    Returns DataFrame columns:
        commodity, month, open, high, low, close, change, volume,
        open_interest, settlement
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _futures_daily_cache:
        return _futures_daily_cache[start_dt]

    max_retries = 1 if dt else 7
    all_records: list[dict[str, Any]] = []

    for commodity_id, commodity_name in [("TX", "台指期"), ("MTX", "小台")]:
        found = False
        for attempt in range(max_retries):
            candidate = start_dt - timedelta(days=attempt)
            if candidate.weekday() >= 5:
                continue
            date_str = _taifex_date_str(candidate)

            try:
                resp = httpx.get(
                    "https://www.taifex.com.tw/cht/3/futDataDown",
                    params={
                        "down_type": "1",
                        "commodity_id": commodity_id,
                        "queryStartDate": date_str,
                        "queryEndDate": date_str,
                    },
                    timeout=_TIMEOUT,
                    headers=_HEADERS,
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("TAIFEX futDataDown(%s) fetch failed for %s: %s",
                               commodity_id, date_str, exc)
                continue

            text = _decode_response(resp)

            # 嘗試 read_html
            tables = _try_read_html(text)
            if tables:
                df_raw = tables[0]
                for _, row in df_raw.iterrows():
                    vals = list(row)
                    if len(vals) < 10:
                        continue
                    # 跳過標題列
                    if str(vals[0]).strip() in ("契約", "商品"):
                        continue
                    all_records.append({
                        "commodity": commodity_name,
                        "month": str(vals[1]).strip() if len(vals) > 1 else "",
                        "open": _safe_num(vals[2]) if len(vals) > 2 else 0.0,
                        "high": _safe_num(vals[3]) if len(vals) > 3 else 0.0,
                        "low": _safe_num(vals[4]) if len(vals) > 4 else 0.0,
                        "close": _safe_num(vals[5]) if len(vals) > 5 else 0.0,
                        "change": _safe_num(vals[6]) if len(vals) > 6 else 0.0,
                        "volume": _safe_int(vals[7]) if len(vals) > 7 else 0,
                        "settlement": _safe_num(vals[8]) if len(vals) > 8 else 0.0,
                        "open_interest": _safe_int(vals[9]) if len(vals) > 9 else 0,
                    })
                found = True
                break

            # CSV fallback
            rows = _try_read_csv(text)
            if len(rows) > 1:
                for row in rows[1:]:
                    if len(row) < 10:
                        continue
                    if row[0].strip() in ("契約", "商品", ""):
                        continue
                    all_records.append({
                        "commodity": commodity_name,
                        "month": row[1].strip(),
                        "open": _safe_num(row[2]),
                        "high": _safe_num(row[3]),
                        "low": _safe_num(row[4]),
                        "close": _safe_num(row[5]),
                        "change": _safe_num(row[6]),
                        "volume": _safe_int(row[7]),
                        "settlement": _safe_num(row[8]),
                        "open_interest": _safe_int(row[9]),
                    })
                found = True
                break

        if not found:
            logger.warning("TAIFEX futDataDown(%s): no data within lookback", commodity_id)

    df = pd.DataFrame(all_records)
    if not df.empty:
        logger.info("TAIFEX futures daily: fetched %d rows", len(df))
    _futures_daily_cache[start_dt] = df
    return df


# ── 2. 三大法人期貨未平倉 ────────────────────────────

_futures_institutional_cache: dict[date, pd.DataFrame] = {}


def fetch_futures_institutional(dt: date | None = None) -> pd.DataFrame:
    """三大法人期貨未平倉部位。

    從 TAIFEX futContractsDate 頁面 HTML 表格解析。

    Returns DataFrame columns:
        identity, long_volume, long_position, short_volume,
        short_position, net_position
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _futures_institutional_cache:
        return _futures_institutional_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = _taifex_date_str(candidate)

        try:
            resp = httpx.get(
                "https://www.taifex.com.tw/cht/3/futContractsDate",
                params={"queryDate": date_str, "commodityId": "TXF"},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("TAIFEX futContractsDate fetch failed for %s: %s",
                           date_str, exc)
            continue

        text = resp.text
        if "查無資料" in text or "alert" in text[:500]:
            logger.info("TAIFEX futContractsDate: no data for %s", date_str)
            continue

        tables = _try_read_html(text)
        if not tables:
            continue

        records: list[dict[str, Any]] = []
        identity_map = {"外資": "外資", "投信": "投信", "自營商": "自營商"}

        # 表格結構（多層表頭已被 flatten）：
        # 序號 | 商品名稱 | 身份別 | 交易多方口數 | 交易多方金額 |
        # 交易空方口數 | 交易空方金額 | 交易淨口數 | 交易淨金額 |
        # 未平倉多方口數 | 未平倉多方金額 | 未平倉空方口數 | 未平倉空方金額 |
        # 未平倉淨口數 | 未平倉淨金額
        tbl = tables[0]
        for _, row in tbl.iterrows():
            vals = [str(v).strip() for v in row]
            # 只取「臺股期貨」的列（跳過小計/合計）
            if "期貨" in vals[1] and "小計" not in vals[1] and "合計" not in vals[1]:
                identity_raw = vals[2] if len(vals) > 2 else ""
                for key, label in identity_map.items():
                    if key in identity_raw:
                        # 從 row 中提取數值欄位
                        nums = [_safe_num(v) for v in vals[3:]]
                        if len(nums) >= 12:
                            records.append({
                                "identity": label,
                                "long_volume": _safe_int(nums[0]),
                                "short_volume": _safe_int(nums[2]),
                                "net_volume": _safe_int(nums[4]),
                                "long_position": _safe_int(nums[6]),
                                "short_position": _safe_int(nums[8]),
                                "net_position": _safe_int(nums[10]),
                            })
                        elif len(nums) >= 6:
                            records.append({
                                "identity": label,
                                "long_volume": _safe_int(nums[0]),
                                "short_volume": _safe_int(nums[2]),
                                "net_volume": _safe_int(nums[0]) - _safe_int(nums[2]),
                                "long_position": _safe_int(nums[3]),
                                "short_position": _safe_int(nums[4]),
                                "net_position": _safe_int(nums[3]) - _safe_int(nums[4]),
                            })
                        break

        if records:
            logger.info("TAIFEX institutional: using trading date %s", candidate)
            break
    else:
        logger.warning("TAIFEX futContractsDate: no valid data within lookback")
        df = pd.DataFrame()
        _futures_institutional_cache[start_dt] = df
        return df

    df = pd.DataFrame(records)
    logger.info("TAIFEX institutional: fetched %d identities", len(df))
    _futures_institutional_cache[start_dt] = df
    return df


# ── 3. PUT/CALL Ratio ────────────────────────────────

_pc_ratio_cache: dict[date, dict] = {}


def fetch_put_call_ratio(dt: date | None = None) -> dict:
    """選擇權 PUT/CALL ratio。

    Returns:
        {"date": str, "put_volume": int, "call_volume": int,
         "pc_ratio_volume": float, "put_oi": int, "call_oi": int,
         "pc_ratio_oi": float}
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _pc_ratio_cache:
        return _pc_ratio_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = _taifex_date_str(candidate)

        try:
            resp = httpx.get(
                "https://www.taifex.com.tw/cht/3/pcRatioDown",
                params={"queryStartDate": date_str, "queryEndDate": date_str},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("TAIFEX pcRatioDown fetch failed for %s: %s", date_str, exc)
            continue

        text = _decode_response(resp)

        # 嘗試 read_html
        tables = _try_read_html(text)
        if tables:
            df_raw = tables[0]
            if len(df_raw) > 0:
                # 取最後一列資料（跳過可能的標題）
                for idx in range(len(df_raw) - 1, -1, -1):
                    row = list(df_raw.iloc[idx])
                    nums = [_safe_num(v) for v in row]
                    if any(n > 0 for n in nums):
                        put_vol = _safe_int(row[1]) if len(row) > 1 else 0
                        call_vol = _safe_int(row[2]) if len(row) > 2 else 0
                        pc_vol = _safe_num(row[3]) if len(row) > 3 else 0.0
                        put_oi = _safe_int(row[4]) if len(row) > 4 else 0
                        call_oi = _safe_int(row[5]) if len(row) > 5 else 0
                        pc_oi = _safe_num(row[6]) if len(row) > 6 else 0.0
                        result = {
                            "date": str(row[0]).strip() if len(row) > 0 else date_str,
                            "put_volume": put_vol,
                            "call_volume": call_vol,
                            "pc_ratio_volume": pc_vol,
                            "put_oi": put_oi,
                            "call_oi": call_oi,
                            "pc_ratio_oi": pc_oi,
                        }
                        logger.info("TAIFEX P/C ratio: date=%s, ratio_oi=%.2f",
                                    result["date"], pc_oi)
                        _pc_ratio_cache[start_dt] = result
                        return result

        # CSV fallback
        rows = _try_read_csv(text)
        for row in reversed(rows):
            if len(row) >= 7:
                nums = [_safe_num(c) for c in row[1:]]
                if any(n > 0 for n in nums):
                    result = {
                        "date": row[0].strip(),
                        "put_volume": _safe_int(row[1]),
                        "call_volume": _safe_int(row[2]),
                        "pc_ratio_volume": _safe_num(row[3]),
                        "put_oi": _safe_int(row[4]),
                        "call_oi": _safe_int(row[5]),
                        "pc_ratio_oi": _safe_num(row[6]),
                    }
                    logger.info("TAIFEX P/C ratio (csv): date=%s, ratio_oi=%.2f",
                                result["date"], result["pc_ratio_oi"])
                    _pc_ratio_cache[start_dt] = result
                    return result

        logger.info("TAIFEX pcRatioDown: no data for %s, trying previous day", date_str)

    logger.warning("TAIFEX pcRatioDown: no valid data within lookback")
    empty: dict = {}
    _pc_ratio_cache[start_dt] = empty
    return empty


# ── 4. 大額交易人未沖銷部位 ──────────────────────────

_top10_cache: dict[date, pd.DataFrame] = {}


def fetch_top10_traders(dt: date | None = None) -> pd.DataFrame:
    """大額交易人（前五大/前十大）未沖銷部位。

    Returns DataFrame columns:
        category, buy_position, sell_position, buy_pct, sell_pct
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _top10_cache:
        return _top10_cache[start_dt]

    max_retries = 1 if dt else 7

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = _taifex_date_str(candidate)

        try:
            resp = httpx.get(
                "https://www.taifex.com.tw/cht/3/largeTraderFutDown",
                params={"queryDate": date_str, "contractId": "TX"},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("TAIFEX largeTraderFutDown fetch failed for %s: %s",
                           date_str, exc)
            continue

        text = _decode_response(resp)
        records: list[dict[str, Any]] = []

        category_keywords = {
            "前五大": "前五大",
            "前十大": "前十大",
            "全市場": "全市場",
        }

        # 嘗試 read_html
        tables = _try_read_html(text)
        if tables:
            for tbl in tables:
                for _, row in tbl.iterrows():
                    vals = [str(v).strip() for v in row]
                    row_text = " ".join(vals)
                    for key, label in category_keywords.items():
                        if key in row_text:
                            nums = [_safe_num(v) for v in vals]
                            nums_nonzero = [n for n in nums if n != 0.0]
                            if len(nums_nonzero) >= 4:
                                records.append({
                                    "category": label,
                                    "buy_position": _safe_int(nums_nonzero[0]),
                                    "sell_position": _safe_int(nums_nonzero[1]),
                                    "buy_pct": _safe_num(nums_nonzero[2]),
                                    "sell_pct": _safe_num(nums_nonzero[3]),
                                })
                            break

        # CSV fallback
        if not records:
            rows = _try_read_csv(text)
            for row in rows:
                row_text = ",".join(row)
                for key, label in category_keywords.items():
                    if key in row_text:
                        nums = [_safe_num(c) for c in row]
                        nums = [n for n in nums if n != 0.0]
                        if len(nums) >= 4:
                            records.append({
                                "category": label,
                                "buy_position": _safe_int(nums[0]),
                                "sell_position": _safe_int(nums[1]),
                                "buy_pct": _safe_num(nums[2]),
                                "sell_pct": _safe_num(nums[3]),
                            })
                        break

        if records:
            logger.info("TAIFEX top10 traders: using trading date %s", candidate)
            break
    else:
        logger.warning("TAIFEX largeTraderFutDown: no valid data within lookback")
        df = pd.DataFrame()
        _top10_cache[start_dt] = df
        return df

    df = pd.DataFrame(records)
    logger.info("TAIFEX top10 traders: fetched %d categories", len(df))
    _top10_cache[start_dt] = df
    return df


# ── 5. 基差計算 ──────────────────────────────────────

_basis_cache: dict[date, dict] = {}


def fetch_futures_basis(dt: date | None = None) -> dict:
    """計算基差（現貨 - 期貨）。

    取台指期近月收盤價，嘗試從 TWSE MI_INDEX 取加權指數收盤。

    Returns:
        {"spot": float, "futures": float, "basis": float,
         "basis_pct": float, "status": "正價差"/"逆價差"/"平水"}
    """
    start_dt = dt or _find_trading_date(date.today())
    if start_dt in _basis_cache:
        return _basis_cache[start_dt]

    # 取台指期近月收盤
    futures_df = fetch_futures_daily(start_dt)
    futures_close = 0.0
    if not futures_df.empty:
        tx_rows = futures_df[futures_df["commodity"] == "台指期"]
        if not tx_rows.empty:
            # 取第一筆（近月）
            futures_close = float(tx_rows.iloc[0]["close"])

    if futures_close == 0.0:
        logger.warning("TAIFEX basis: cannot get futures close price")
        empty: dict = {}
        _basis_cache[start_dt] = empty
        return empty

    # 取加權指數收盤
    spot = 0.0
    try:
        from atlas.infrastructure.twse_bulk import fetch_mi_index

        mi_data = fetch_mi_index(start_dt)
        if mi_data:
            spot = mi_data.get("close", 0.0)
    except ImportError:
        pass

    # 如果 twse_bulk 不可用或無資料，嘗試直接從 TWSE API 抓
    if spot == 0.0:
        for attempt in range(7):
            candidate = start_dt - timedelta(days=attempt)
            if candidate.weekday() >= 5:
                continue
            date_str = candidate.strftime("%Y%m%d")
            try:
                resp = httpx.get(
                    "https://www.twse.com.tw/exchangeReport/MI_INDEX",
                    params={"response": "json", "date": date_str, "type": "IND"},
                    timeout=_TIMEOUT,
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("stat") == "OK":
                    for tbl in data.get("tables", []):
                        if not isinstance(tbl, dict):
                            continue
                        for row in tbl.get("data", []):
                            if not isinstance(row, list) or len(row) < 2:
                                continue
                            name = str(row[0])
                            if "發行量加權" in name and "報酬" not in name:
                                # row[0]=名稱, row[1]=收盤指數, row[2]=漲跌符號, row[3]=漲跌點數
                                spot = _safe_num(row[1])
                                break
                        if spot > 0:
                            break
                    if spot > 0:
                        break
            except Exception:
                continue

    if spot == 0.0:
        logger.warning("TAIFEX basis: cannot get spot index")
        result = {
            "spot": 0.0,
            "futures": futures_close,
            "basis": 0.0,
            "basis_pct": 0.0,
            "status": "無法計算",
        }
        _basis_cache[start_dt] = result
        return result

    basis = spot - futures_close
    basis_pct = (basis / spot * 100) if spot != 0 else 0.0

    if abs(basis_pct) < 0.05:
        status = "平水"
    elif basis > 0:
        status = "逆價差"
    else:
        status = "正價差"

    result = {
        "spot": spot,
        "futures": futures_close,
        "basis": round(basis, 2),
        "basis_pct": round(basis_pct, 4),
        "status": status,
    }
    logger.info("TAIFEX basis: spot=%.2f futures=%.2f basis=%.2f (%s)",
                spot, futures_close, basis, status)
    _basis_cache[start_dt] = result
    return result
