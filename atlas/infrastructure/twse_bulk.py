"""TWSE / TPEx 全市場批次資料擷取 — 每日行情 + 三大法人 + 處置股。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


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


# 模組層級變數，記錄最近一次成功取得資料的交易日期
last_trading_date: date | None = None


_twse_daily_cache: dict[date, pd.DataFrame] = {}


def fetch_twse_daily_all(dt: date | None = None) -> pd.DataFrame:
    """取得 TWSE 全市場當日收盤行情（同日期快取）。

    非交易日（假日/週末）自動往前回退，最多 7 天。

    Returns DataFrame with columns:
        code, name, volume(股), open, high, low, close, change, trade_count
    """
    global last_trading_date
    start_dt = dt or _find_trading_date(date.today())
    cache_key = start_dt
    if cache_key in _twse_daily_cache:
        return _twse_daily_cache[cache_key]
    max_retries = 1 if dt else 7  # 指定日期只試一次，自動模式往前找 7 天

    for attempt in range(max_retries):
        candidate = start_dt - timedelta(days=attempt)
        if candidate.weekday() >= 5:
            continue
        date_str = candidate.strftime("%Y%m%d")

        try:
            resp = httpx.get(
                "https://www.twse.com.tw/exchangeReport/MI_INDEX",
                params={"response": "json", "date": date_str, "type": "ALLBUT0999"},
                timeout=_TIMEOUT,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TWSE MI_INDEX fetch failed for %s: %s", date_str, exc)
            continue

        if data.get("stat") != "OK":
            logger.info("TWSE MI_INDEX stat=%s for %s, trying previous day", data.get("stat"), date_str)
            continue

        last_trading_date = candidate
        logger.info("TWSE daily: using trading date %s", candidate)
        break
    else:
        logger.warning("TWSE MI_INDEX: no valid trading date found within lookback")
        return pd.DataFrame()

    # data9 (舊版) 或 tables[8].data (新版 2025+)
    rows_data = data.get("data9") or data.get("data") or []
    if not rows_data:
        # 新版 API：個股行情在 tables 陣列中資料量最大的那張表
        tables = data.get("tables") or []
        for tbl in tables:
            if isinstance(tbl, dict) and len(tbl.get("data", [])) > 100:
                rows_data = tbl["data"]
                break
    if not rows_data:
        # Fallback: 搜尋 data* 開頭的 key
        for key in data:
            if key.startswith("data") and isinstance(data[key], list) and len(data[key]) > 100:
                rows_data = data[key]
                break

    records = []
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            # Skip non-stock codes (ETFs starting with 00, warrants, etc.)
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            volume = _safe_int(row[2])  # 成交股數
            trade_count = _safe_int(row[3])  # 成交筆數
            open_p = _safe_num(row[5])
            high = _safe_num(row[6])
            low = _safe_num(row[7])
            close = _safe_num(row[8])
            change_sign = str(row[9]).strip()
            change_val = _safe_num(row[10])
            # 漲跌符號：舊版用 "-"/"▼"，新版用 HTML <p style= color:green>-</p>
            if "-" in change_sign or "▼" in change_sign or "green" in change_sign:
                change_val = -abs(change_val)

            if close <= 0:
                continue

            records.append({
                "code": code,
                "name": name,
                "volume": volume,
                "volume_lots": volume // 1000,  # 張
                "trade_count": trade_count,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "change": change_val,
                "change_pct": round(change_val / (close - change_val) * 100, 2)
                if (close - change_val) > 0 else 0.0,
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TWSE daily: fetched %d stocks for %s", len(df), date_str)
    _twse_daily_cache[cache_key] = df
    return df


_twse_inst_cache: dict[date, pd.DataFrame] = {}


def fetch_twse_institutional(dt: date | None = None) -> pd.DataFrame:
    """取得 TWSE 三大法人全市場買賣超。

    Returns DataFrame with columns:
        code, name, foreign_buy, foreign_sell, foreign_net,
        trust_buy, trust_sell, trust_net,
        dealer_buy, dealer_sell, dealer_net, total_net
    """
    # 使用 last_trading_date 確保與行情資料同一天
    dt = dt or last_trading_date or _find_trading_date(date.today())
    if dt in _twse_inst_cache:
        return _twse_inst_cache[dt]
    date_str = dt.strftime("%Y%m%d")

    try:
        resp = httpx.get(
            "https://www.twse.com.tw/fund/T86",
            params={"response": "json", "date": date_str, "selectType": "ALLBUT0999"},
            timeout=_TIMEOUT,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("TWSE T86 fetch failed: %s", exc)
        return pd.DataFrame()

    if data.get("stat") != "OK":
        return pd.DataFrame()

    records = []
    # 新版 T86 (19欄): [0]代號 [1]名稱
    #   [2-4]外資(不含自營商) [5-7]外資自營商
    #   [8-10]投信 [11]自營商合計淨 [12-14]自營商(自行) [15-17]自營商(避險) [18]三大法人合計
    has_new_format = len(data.get("data", [[]])[0]) >= 19 if data.get("data") else False
    for row in data.get("data", []):
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            if has_new_format:
                foreign_buy = _safe_int(row[2])
                foreign_sell = _safe_int(row[3])
                foreign_net = _safe_int(row[4]) + _safe_int(row[7])  # 外資+外資自營商
                trust_buy = _safe_int(row[8])
                trust_sell = _safe_int(row[9])
                trust_net = _safe_int(row[10])
                dealer_buy = 0
                dealer_sell = 0
                dealer_net = _safe_int(row[11])
                total_net = _safe_int(row[18])
            else:
                foreign_buy = _safe_int(row[2])
                foreign_sell = _safe_int(row[3])
                foreign_net = _safe_int(row[4])
                trust_buy = _safe_int(row[5])
                trust_sell = _safe_int(row[6])
                trust_net = _safe_int(row[7])
                dealer_buy = _safe_int(row[8])
                dealer_sell = _safe_int(row[9])
                dealer_net = _safe_int(row[10])
                total_net = foreign_net + trust_net + dealer_net

            records.append({
                "code": code,
                "name": name,
                "foreign_buy": foreign_buy,
                "foreign_sell": foreign_sell,
                "foreign_net": foreign_net,
                "trust_buy": trust_buy,
                "trust_sell": trust_sell,
                "trust_net": trust_net,
                "dealer_buy": dealer_buy,
                "dealer_sell": dealer_sell,
                "dealer_net": dealer_net,
                "total_net": total_net,
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TWSE institutional: fetched %d stocks for %s", len(df), date_str)
    _twse_inst_cache[dt] = df
    return df


_disposition_cache: set[str] | None = None
_disposition_cache_date: date | None = None


def fetch_disposition_list() -> set[str]:
    """取得目前處置股代碼清單（同一天快取，不重複呼叫）。"""
    global _disposition_cache, _disposition_cache_date
    today = date.today()
    if _disposition_cache is not None and _disposition_cache_date == today:
        return _disposition_cache
    try:
        resp = httpx.get(
            "https://www.twse.com.tw/announcement/punish",
            params={"response": "json"},
            timeout=_TIMEOUT,
            headers=_HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        codes = set()
        for row in data.get("data", []):
            code = str(row[0]).strip()
            if code.isdigit() and len(code) == 4:
                codes.add(code)
        logger.info("Disposition list: %d stocks", len(codes))
        _disposition_cache = codes
        _disposition_cache_date = today
        return codes
    except Exception as exc:
        logger.warning("Disposition list fetch failed: %s", exc)
        return set()


_tpex_daily_cache: dict[date, pd.DataFrame] = {}


def fetch_tpex_daily_all(dt: date | None = None) -> pd.DataFrame:
    """取得 TPEx (上櫃) 全市場當日收盤行情（同日期快取）。"""
    dt = dt or last_trading_date or _find_trading_date(date.today())
    if dt in _tpex_daily_cache:
        return _tpex_daily_cache[dt]
    # TPEx uses ROC year
    roc_year = dt.year - 1911
    date_str = f"{roc_year}/{dt.month:02d}/{dt.day:02d}"

    try:
        resp = httpx.get(
            "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php",
            params={"l": "zh-tw", "d": date_str, "se": "EW"},
            timeout=_TIMEOUT,
            headers=_HEADERS,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("TPEx daily fetch failed: %s", exc)
        return pd.DataFrame()

    # aaData (舊版) 或 tables[0].data (新版 2025+)
    rows_data = data.get("aaData") or []
    if not rows_data:
        for tbl in data.get("tables", []):
            if isinstance(tbl, dict) and len(tbl.get("data", [])) > 100:
                rows_data = tbl["data"]
                break

    records = []
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            close = _safe_num(row[2])
            change = _safe_num(row[3])
            open_p = _safe_num(row[4])
            high = _safe_num(row[5])
            low = _safe_num(row[6])
            volume = _safe_int(row[7])  # 成交股數

            if close <= 0:
                continue

            records.append({
                "code": code,
                "name": name,
                "volume": volume,
                "volume_lots": volume // 1000,
                "trade_count": 0,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "change": change,
                "change_pct": round(change / (close - change) * 100, 2)
                if (close - change) > 0 else 0.0,
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TPEx daily: fetched %d stocks for %s", len(df), date_str)
    _tpex_daily_cache[dt] = df
    return df


_tpex_inst_cache: dict[date, pd.DataFrame] = {}


def fetch_tpex_institutional(dt: date | None = None) -> pd.DataFrame:
    """取得 TPEx 三大法人全市場買賣超。"""
    dt = dt or last_trading_date or _find_trading_date(date.today())
    if dt in _tpex_inst_cache:
        return _tpex_inst_cache[dt]
    roc_year = dt.year - 1911
    date_str = f"{roc_year}/{dt.month:02d}/{dt.day:02d}"

    try:
        resp = httpx.get(
            "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php",
            params={"l": "zh-tw", "d": date_str, "se": "EW", "t": "D"},
            timeout=_TIMEOUT,
            headers=_HEADERS,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("TPEx institutional fetch failed: %s", exc)
        return pd.DataFrame()

    # aaData (舊版) 或 tables[0].data (新版 2025+)
    rows_data = data.get("aaData") or []
    if not rows_data:
        for tbl in data.get("tables", []):
            if isinstance(tbl, dict) and len(tbl.get("data", [])) > 100:
                rows_data = tbl["data"]
                break

    records = []
    # 新版 (24欄): [0]代號 [1]名稱
    #   [2-4]外資(不含自營商) [5-7]外資自營商 [8-10]外資合計
    #   [11-13]投信 [14-16]自營商(自行) [17-19]自營商(避險) [20-22]自營商合計 [23]三大法人合計
    has_new_format = len(rows_data[0]) >= 24 if rows_data else False
    for row in rows_data:
        try:
            code = str(row[0]).strip()
            if not code.isdigit() or len(code) != 4:
                continue
            name = str(row[1]).strip()
            if has_new_format:
                foreign_buy = _safe_int(row[8])
                foreign_sell = _safe_int(row[9])
                foreign_net = _safe_int(row[10])   # 外資合計
                trust_buy = _safe_int(row[11])
                trust_sell = _safe_int(row[12])
                trust_net = _safe_int(row[13])
                dealer_buy = _safe_int(row[20])
                dealer_sell = _safe_int(row[21])
                dealer_net = _safe_int(row[22])    # 自營商合計
            else:
                foreign_buy = _safe_int(row[2])
                foreign_sell = _safe_int(row[3])
                foreign_net = _safe_int(row[4])
                trust_buy = _safe_int(row[5])
                trust_sell = _safe_int(row[6])
                trust_net = _safe_int(row[7])
                dealer_buy = _safe_int(row[8])
                dealer_sell = _safe_int(row[9])
                dealer_net = _safe_int(row[10])

            records.append({
                "code": code,
                "name": name,
                "foreign_buy": foreign_buy,
                "foreign_sell": foreign_sell,
                "foreign_net": foreign_net,
                "trust_buy": trust_buy,
                "trust_sell": trust_sell,
                "trust_net": trust_net,
                "dealer_buy": dealer_buy,
                "dealer_sell": dealer_sell,
                "dealer_net": dealer_net,
                "total_net": foreign_net + trust_net + dealer_net,
            })
        except (IndexError, ValueError):
            continue

    df = pd.DataFrame(records)
    logger.info("TPEx institutional: fetched %d stocks for %s", len(df), date_str)
    _tpex_inst_cache[dt] = df
    return df
