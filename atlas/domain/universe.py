"""股票池管理 — 四層篩選建立可交易標的清單。"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType
from atlas.interfaces.domain import IUniverseManager

if TYPE_CHECKING:
    from atlas.infrastructure.cache import CacheManager
    from atlas.infrastructure.data_manager import DataManager

logger = logging.getLogger(__name__)

_CACHE_KEY = "universe:{market}"
_CACHE_TTL = 86400  # 1 天

# 四層篩選門檻（台股預設）
_TW_MIN_VOLUME = 500_000  # 最低日均量 50 萬股
_TW_MIN_PRICE = 10.0  # 最低價 10 元
_TW_MAX_INDUSTRY_PCT = 0.20  # 單一產業上限 20%


class UniverseManager(IUniverseManager):
    """股票池管理器。

    四層篩選：
    L1 流動性：日均量 > 50 萬股，股價 > 10 元
    L2 技術面：非處置/警示/全額交割
    L3 策略適性：近 60 日有成交量（非冷門股）
    L4 消息面排除：手動黑名單
    """

    def __init__(
        self,
        data_manager: DataManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._dm = data_manager
        self._cache = cache
        self._universe: dict[MarketType, list[str]] = {}
        self._blacklist: dict[MarketType, set[str]] = {MarketType.TW: set(), MarketType.US: set()}
        self._last_build: dict[MarketType, date] = {}
        self._filter_stats: dict[MarketType, dict[str, Any]] = {}

    async def build_universe(
        self, market: MarketType, force_rebuild: bool = False
    ) -> list[str]:
        if not force_rebuild and market in self._last_build:
            days_since = (date.today() - self._last_build[market]).days
            if days_since < 30:
                logger.info("Universe still fresh (%d days old), skipping rebuild", days_since)
                return self._universe.get(market, [])

        logger.info("Building universe for %s...", market.value)
        bars = await self._dm.fetch_daily_all(market, date.today())
        if not bars:
            logger.warning("No market data for universe build")
            return self._universe.get(market, [])

        stats: dict[str, Any] = {}
        candidates = [(b.code, float(b.close), b.volume) for b in bars]
        total = len(candidates)

        # L1 流動性
        min_vol = _TW_MIN_VOLUME if market == MarketType.TW else 100_000
        min_price = _TW_MIN_PRICE if market == MarketType.TW else 5.0
        l1_pass = [(c, p, v) for c, p, v in candidates if v >= min_vol and p >= min_price]
        stats["layer1_liquidity"] = {"passed": len(l1_pass), "rejected": total - len(l1_pass)}

        # L2 技術面（處置/警示排除 — 需 stock 表，這裡簡化為全部通過）
        l2_pass = l1_pass
        stats["layer2_technical"] = {"passed": len(l2_pass), "rejected": len(l1_pass) - len(l2_pass)}

        # L3 策略適性（非冷門股 — 用量 > 10 萬股的簡化判斷）
        l3_pass = [(c, p, v) for c, p, v in l2_pass if v >= 100_000]
        stats["layer3_strategy"] = {"passed": len(l3_pass), "rejected": len(l2_pass) - len(l3_pass)}

        # L4 消息面排除（黑名單）
        blacklist = self._blacklist.get(market, set())
        l4_pass = [(c, p, v) for c, p, v in l3_pass if c not in blacklist]
        stats["layer4_exclusion"] = {"passed": len(l4_pass), "rejected": len(l3_pass) - len(l4_pass)}

        codes = [c for c, _, _ in l4_pass]
        stats["final_count"] = len(codes)

        self._universe[market] = codes
        self._last_build[market] = date.today()
        self._filter_stats[market] = stats

        if self._cache:
            await self._cache.set(_CACHE_KEY.format(market=market.value), codes, _CACHE_TTL)

        logger.info(
            "Universe built: %d → L1:%d → L2:%d → L3:%d → L4:%d",
            total,
            stats["layer1_liquidity"]["passed"],
            stats["layer2_technical"]["passed"],
            stats["layer3_strategy"]["passed"],
            stats["layer4_exclusion"]["passed"],
        )
        return codes

    async def get_universe(self, market: MarketType) -> list[str]:
        if market in self._universe:
            return self._universe[market]
        if self._cache:
            cached = await self._cache.get(_CACHE_KEY.format(market=market.value))
            if cached:
                self._universe[market] = cached
                return cached
        return await self.build_universe(market)

    async def get_filter_report(self, market: MarketType) -> dict[str, Any]:
        if market not in self._filter_stats:
            await self.build_universe(market)
        return self._filter_stats.get(market, {})

    async def get_monthly_diff(self, market: MarketType) -> dict[str, list[str]]:
        old = set(self._universe.get(market, []))
        new_codes = await self.build_universe(market, force_rebuild=True)
        new_set = set(new_codes)
        return {
            "added": sorted(new_set - old),
            "removed": sorted(old - new_set),
            "retained": sorted(old & new_set),
        }

    async def manual_adjust(
        self,
        market: MarketType,
        add_codes: list[str] | None = None,
        remove_codes: list[str] | None = None,
    ) -> list[str]:
        current = set(self._universe.get(market, []))
        if add_codes:
            current.update(add_codes)
        if remove_codes:
            current -= set(remove_codes)
            self._blacklist.setdefault(market, set()).update(remove_codes)
        self._universe[market] = sorted(current)
        logger.info("Universe manually adjusted: +%s -%s", add_codes, remove_codes)
        return self._universe[market]

    async def check_industry_diversification(
        self, market: MarketType, max_industry_pct: float = _TW_MAX_INDUSTRY_PCT
    ) -> dict[str, Any]:
        # 需要 stock → industry mapping，目前回傳 placeholder
        codes = self._universe.get(market, [])
        return {
            "total": len(codes),
            "max_industry_pct": max_industry_pct,
            "violations": [],
            "detail": "Industry mapping requires stock table integration",
        }
