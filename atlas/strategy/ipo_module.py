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


def _roc_to_ad(roc_str: str) -> str:
    """將 ROC 日期（如 115.05.29）轉為西元日期字串（2026-05-29）。"""
    try:
        parts = roc_str.split(".")
        if len(parts) == 3:
            year = int(parts[0]) + 1911
            return f"{year}-{parts[1]}-{parts[2]}"
    except (ValueError, IndexError):
        pass
    return roc_str


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
        """同步抓取公開申購資料（Histock 為主，TWSE 新上市為輔）。

        只回傳尚未截止的申購（申購迄日 >= 今天）。
        """
        import httpx
        from datetime import date as _date
        from io import StringIO

        import pandas as pd

        _HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        results: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        today = _date.today()

        # ── 1. Histock 公開申購（含申購期間、承銷價、市價、價差率）──
        try:
            resp = httpx.get(
                "https://histock.tw/stock/public.aspx",
                headers=_HEADERS,
                timeout=15,
                verify=False,
            )
            if resp.status_code == 200:
                text = resp.content.decode("utf-8", errors="replace")
                tables = pd.read_html(StringIO(text))
                if tables:
                    tbl = tables[0]
                    for _, row in tbl.iterrows():
                        try:
                            # [1] = "代碼\xa0名稱"
                            cn = str(row.iloc[1]).replace(chr(160), " ").strip()
                            parts = cn.split()
                            code = parts[0] if parts else ""
                            if not code.isdigit() or len(code) != 4:
                                continue
                            if code in seen_codes:
                                continue
                            name = parts[1] if len(parts) > 1 else ""

                            # [13] = 備註（申購中/已截止/nan）
                            note = str(row.iloc[13]).strip().lower() if pd.notna(row.iloc[13]) else ""
                            if "截止" in note:
                                continue

                            # [3] = 申購期間 "MM/DD~MM/DD"
                            sub_period = str(row.iloc[3]).strip()
                            start_date_str = ""
                            end_date_str = ""
                            if "~" in sub_period:
                                s_part, e_part = sub_period.split("~")
                                start_date_str = f"{today.year}/{s_part.strip()}"
                                end_date_str = f"{today.year}/{e_part.strip()}"
                                # 用申購迄日判斷是否過期（備註為空時 fallback）
                                try:
                                    em, ed = e_part.strip().split("/")
                                    end_dt = _date(today.year, int(em), int(ed))
                                    if today > end_dt:
                                        continue
                                except (ValueError, IndexError):
                                    pass

                            seen_codes.add(code)

                            # [6]=承銷價 [7]=市價 [9]=價差率%
                            sub_price = float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0.0
                            market_price = float(row.iloc[7]) if pd.notna(row.iloc[7]) else 0.0
                            spread_pct = float(row.iloc[9]) if pd.notna(row.iloc[9]) else 0.0

                            # [0]=掛牌日
                            listing_date_str = str(row.iloc[0]).strip()

                            if spread_pct > 20:
                                rec = "值得申購"
                            elif spread_pct > 0:
                                rec = "小利空間"
                            else:
                                rec = "已破發"

                            results.append({
                                "code": code,
                                "name": name,
                                "listing_date": listing_date_str,
                                "start_date": start_date_str,
                                "end_date": end_date_str,
                                "subscription_price": sub_price,
                                "market_ref_price": market_price,
                                "spread_pct": spread_pct,
                                "recommendation": rec,
                                "source": "histock",
                            })
                        except Exception:
                            continue
                logger.info("Histock IPO: %d active subscriptions", len(results))
        except Exception as exc:
            logger.debug("Histock IPO fetch failed: %s", exc)

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
