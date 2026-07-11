"""IPO 工具 — 新股上市公開申購掃描與蜜月期追蹤。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from atlas.interfaces.strategy import IIPOModule

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)


def _ipo_recommendation(sub_price: float) -> str:
    """根據承銷價產生建議文字。"""
    if sub_price <= 0:
        return "待查承銷價"
    return "已有承銷價"


class IPOModule(IIPOModule):
    """IPO 分析模組。

    功能：
    - 掃描即將公開申購的標的（spread > 20% 才推薦）
    - 追蹤蜜月期（上市後 30 日表現）
    - 歷史勝率統計
    """

    def __init__(
        self,
        data_manager: DataManager | None = None,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache
        self._tracked: dict[str, dict[str, Any]] = {}

    async def scan_upcoming(self) -> list[dict[str, Any]]:
        """掃描即將公開申購的標的。

        資料源：公開資訊觀測站 (MOPS) — 公開申購公告。
        Fallback：回傳空列表。
        """
        import asyncio

        try:
            result = await asyncio.to_thread(self._fetch_upcoming_sync)
            if result:
                logger.info("IPO scan: found %d upcoming IPOs", len(result))
                return result
        except Exception as exc:
            logger.warning("IPO scan failed: %s", exc)

        return []

    @staticmethod
    def _fetch_upcoming_sync() -> list[dict[str, Any]]:
        """同步抓取公開申購資料（MOPS 公開申購 + TWSE 新上市 + TPEx）。"""
        import httpx
        from io import StringIO

        _HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        results: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        # ── 1. MOPS 公開申購公告（含承銷價）──
        try:
            resp = httpx.post(
                "https://mops.twse.com.tw/mops/web/ajax_t51sb10",
                data={
                    "encodeURIComponent": "1",
                    "step": "1",
                    "firstin": "1",
                    "off": "1",
                    "TYPEK": "all",
                },
                headers=_HEADERS,
                timeout=15,
            )
            if resp.status_code == 200:
                import pandas as pd
                try:
                    tables = pd.read_html(StringIO(resp.text))
                    for tbl in tables:
                        if len(tbl) < 1 or len(tbl.columns) < 5:
                            continue
                        cols = [str(c) for c in tbl.columns]
                        # 找含有「代號」和「承銷價」的表
                        code_col = next((c for c in cols if "代號" in c or "代碼" in c), None)
                        name_col = next((c for c in cols if "名稱" in c or "公司" in c), None)
                        price_col = next((c for c in cols if "承銷價" in c or "認購價" in c), None)
                        date_col = next((c for c in cols if "申購" in c and "起" in c), None)
                        end_col = next((c for c in cols if "申購" in c and "迄" in c), None)

                        if not code_col:
                            continue

                        for _, row in tbl.iterrows():
                            try:
                                code = str(row[code_col]).strip()
                                if not code.isdigit() or len(code) != 4:
                                    continue
                                if code in seen_codes:
                                    continue
                                seen_codes.add(code)

                                name = str(row[name_col]).strip() if name_col else ""
                                sub_price = 0.0
                                if price_col:
                                    try:
                                        sub_price = float(str(row[price_col]).replace(",", "").strip())
                                    except (ValueError, TypeError):
                                        pass
                                start_date = str(row[date_col]).strip() if date_col else ""
                                end_date = str(row[end_col]).strip() if end_col else ""

                                results.append({
                                    "code": code,
                                    "name": name,
                                    "listing_date": start_date,
                                    "end_date": end_date,
                                    "subscription_price": sub_price,
                                    "market_ref_price": 0,
                                    "spread_pct": 0.0,
                                    "recommendation": _ipo_recommendation(sub_price),
                                    "source": "mops",
                                })
                            except Exception:
                                continue
                except Exception as exc:
                    logger.debug("MOPS table parse failed: %s", exc)
        except Exception as exc:
            logger.debug("MOPS fetch failed: %s", exc)

        # ── 2. TWSE 最近上市 ──
        try:
            url = "https://www.twse.com.tw/company/newlisting"
            resp = httpx.get(url, params={"response": "json"}, timeout=15, headers=_HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                for row in data.get("data", [])[:10]:
                    try:
                        code = str(row[0]).strip()
                        if code in seen_codes:
                            continue
                        seen_codes.add(code)
                        name = str(row[1]).strip()
                        listing_date_str = str(row[2]).strip()
                        # row[3] 有時含承銷價資訊
                        sub_price = 0.0
                        if len(row) > 4:
                            try:
                                sub_price = float(str(row[4]).replace(",", "").strip())
                            except (ValueError, TypeError):
                                pass
                        results.append({
                            "code": code,
                            "name": name,
                            "listing_date": listing_date_str,
                            "subscription_price": sub_price,
                            "market_ref_price": 0,
                            "spread_pct": 0.0,
                            "recommendation": _ipo_recommendation(sub_price),
                            "source": "twse_newlisting",
                        })
                    except (IndexError, ValueError):
                        continue
        except Exception as exc:
            logger.debug("TWSE newlisting fetch failed: %s", exc)

        # ── 3. TPEx 新上櫃 ──
        try:
            url = "https://www.tpex.org.tw/web/regular_emerging/apply/latest/latest_result.php"
            resp = httpx.get(url, params={"l": "zh-tw"}, timeout=15, headers=_HEADERS)
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
                for item in data.get("reportList", [])[:5]:
                    code = str(item.get("SecuritiesCompanyCode", ""))
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    sub_price = 0.0
                    try:
                        sub_price = float(str(item.get("SubscriptionPrice", 0)).replace(",", ""))
                    except (ValueError, TypeError):
                        pass
                    results.append({
                        "code": code,
                        "name": str(item.get("CompanyName", "")),
                        "listing_date": str(item.get("ListingDate", "")),
                        "subscription_price": sub_price,
                        "market_ref_price": 0,
                        "spread_pct": 0.0,
                        "recommendation": _ipo_recommendation(sub_price),
                        "source": "tpex",
                    })
        except Exception as exc:
            logger.debug("TPEx listing fetch failed: %s", exc)

        return results

    async def track_honeymoon(
        self, code: str, ipo_date: date
    ) -> dict[str, Any]:
        """追蹤蜜月期（上市後 30 日表現）。"""
        days_since = (date.today() - ipo_date).days
        result: dict[str, Any] = {
            "code": code,
            "ipo_date": ipo_date.isoformat(),
            "days_since_ipo": days_since,
            "return_pct": 0.0,
            "pattern": "unknown",
            "status": "tracking",
        }

        if not self._dm:
            return result

        try:
            from atlas.enums import MarketType
            end = date.today()
            start = ipo_date
            bars = await self._dm.fetch_daily_bars(code, MarketType.TW, start, end)

            if len(bars) < 2:
                return result

            ipo_price = float(bars[0].close)
            current_price = float(bars[-1].close)
            return_pct = (current_price - ipo_price) / ipo_price * 100

            # 判斷蜜月期模式
            max_price = max(float(b.high) for b in bars)
            max_return = (max_price - ipo_price) / ipo_price * 100

            if return_pct > 30:
                pattern = "strong_rally"
            elif return_pct > 10:
                pattern = "steady_up"
            elif return_pct > 0:
                pattern = "mild_up"
            elif return_pct > -10:
                pattern = "flat"
            else:
                pattern = "decline"

            if days_since > 30:
                status = "honeymoon_ended"
            elif return_pct < -20:
                status = "broken"
            else:
                status = "tracking"

            result.update({
                "return_pct": round(return_pct, 2),
                "max_return_pct": round(max_return, 2),
                "current_price": current_price,
                "ipo_price": ipo_price,
                "pattern": pattern,
                "status": status,
                "trading_days": len(bars),
            })

            self._tracked[code] = result
        except Exception as exc:
            logger.warning("IPO track failed for %s: %s", code, exc)

        return result

    async def get_historical_win_rate(self) -> dict[str, float]:
        """取得 IPO 歷史勝率統計。"""
        if not self._tracked:
            return {
                "total": 0,
                "win_rate_30d": 0.0,
                "avg_return_30d": 0.0,
                "best_return": 0.0,
                "worst_return": 0.0,
            }

        returns = [t["return_pct"] for t in self._tracked.values() if "return_pct" in t]
        if not returns:
            return {
                "total": len(self._tracked),
                "win_rate_30d": 0.0,
                "avg_return_30d": 0.0,
                "best_return": 0.0,
                "worst_return": 0.0,
            }

        wins = sum(1 for r in returns if r > 0)
        return {
            "total": len(returns),
            "win_rate_30d": round(wins / len(returns) * 100, 1),
            "avg_return_30d": round(sum(returns) / len(returns), 2),
            "best_return": round(max(returns), 2),
            "worst_return": round(min(returns), 2),
        }
