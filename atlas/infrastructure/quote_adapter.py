"""即時報價適配器 — 實作 Fallback Chain 機制的多來源報價取得。

Fallback Chain:
  台股: TWSE MIS -> YFinance -> LastGoodCache
  美股: YFinance -> LastGoodCache

每次成功報價自動回寫 LastGoodCache，確保永遠有最後成功值可用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import httpx

from atlas.config import QuoteSourceConfig
from atlas.enums import DataSourceHealth, MarketType
from atlas.exceptions import DataSourceError, QuoteUnavailableError
from atlas.interfaces.infrastructure import ICacheService, IQuoteAdapter
from atlas.models.market_data import StockQuote

logger = logging.getLogger(__name__)

# 已知上櫃(OTC)股票代碼集合；TSE 查無資料時也可動態發現
_KNOWN_OTC_CODES: frozenset[str] = frozenset({
    "5269", "6488", "6669", "3293", "8069", "6147", "3529", "6770", "8454", "5871",
})


def _is_otc(code: str) -> bool:
    """判斷是否為上櫃股票（OTC）。"""
    return code in _KNOWN_OTC_CODES


# TWSE MIS API 單次批次上限
_TWSE_BATCH_LIMIT = 50
# httpx 預設逾時秒數
_HTTP_TIMEOUT = 10.0
# 快取 TTL（秒）— 報價快取 1 小時
_QUOTE_CACHE_TTL = 3600


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """安全轉換為 Decimal，失敗回傳 default。"""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _cache_key(market: MarketType, code: str) -> str:
    """產生快取鍵。"""
    return f"atlas:quote:{market.value}:{code}"


# ──────────────────────────────────────────────
# QuoteSource — 單一報價來源抽象基底
# ──────────────────────────────────────────────
class QuoteSource(ABC):
    """單一報價來源抽象基底。"""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_quote(self, code: str) -> StockQuote: ...

    @abstractmethod
    async def get_quotes_batch(self, codes: list[str]) -> list[StockQuote]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# ──────────────────────────────────────────────
# TWSEQuoteSource — TWSE MIS API（台股免費備援）
# ──────────────────────────────────────────────
class TWSEQuoteSource(QuoteSource):
    """TWSE MIS API 報價來源（台股免費備援）。

    使用 TWSE MIS API (https://mis.twse.com.tw/stock/api/...)
    - 支援批次查詢，一次最多 50 檔
    - 延遲約 5 秒（非即時）
    - 免費，無 API Key
    """

    _BASE_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "twse_mis"

    async def connect(self) -> None:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(_HTTP_TIMEOUT),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        logger.info("TWSEQuoteSource connected")

    async def disconnect(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        logger.info("TWSEQuoteSource disconnected")

    async def get_quote(self, code: str) -> StockQuote:
        quotes = await self.get_quotes_batch([code])
        if not quotes:
            raise DataSourceError(f"No quote returned for {code}", source=self.name)
        return quotes[0]

    async def get_quotes_batch(self, codes: list[str]) -> list[StockQuote]:
        if not self._client or self._client.is_closed:
            raise DataSourceError("TWSE client not connected", source=self.name)

        results: list[StockQuote] = []
        # 分批，每批最多 _TWSE_BATCH_LIMIT 檔
        for i in range(0, len(codes), _TWSE_BATCH_LIMIT):
            batch = codes[i : i + _TWSE_BATCH_LIMIT]
            results.extend(await self._fetch_batch(batch))
        return results

    async def _fetch_batch(self, codes: list[str]) -> list[StockQuote]:
        """呼叫 TWSE MIS API 取得一批報價。"""
        # 組合 ex_ch 參數：tse_{code}.tw 上市 / otc_{code}.tw 上櫃
        # 預設用 tse，6 碼開頭通常是上市；實務上可用 mapping 判斷
        ex_ch = "|".join(self._to_ex_ch(c) for c in codes)
        params = {"ex_ch": ex_ch, "json": "1", "_": str(int(time.time() * 1000))}

        try:
            resp = await self._client.get(self._BASE_URL, params=params)  # type: ignore[union-attr]
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise DataSourceError(
                f"TWSE MIS API request failed: {exc}", source=self.name
            ) from exc

        msg_array = data.get("msgArray", [])
        if not msg_array:
            raise DataSourceError("TWSE MIS returned empty msgArray", source=self.name)

        quotes: list[StockQuote] = []
        for item in msg_array:
            try:
                quotes.append(self._parse_item(item))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse TWSE item %s: %s", item.get("c", "?"), exc)
        return quotes

    @staticmethod
    def _to_ex_ch(code: str) -> str:
        """將股票代碼轉換為 TWSE MIS ex_ch 格式。

        上櫃股使用 otc_{code}.tw，上市股使用 tse_{code}.tw。
        """
        prefix = "otc" if _is_otc(code) else "tse"
        return f"{prefix}_{code}.tw"

    @staticmethod
    def _parse_item(item: dict[str, Any]) -> StockQuote:
        """將 TWSE MIS JSON item 轉為 StockQuote。

        MIS API 欄位對照：
          c=代碼, n=名稱, z=成交價, o=開盤價, h=最高, l=最低,
          v=累計成交量(張), a=五檔賣價, b=五檔買價,
          y=昨收, d=日期, t=時間
        """
        code = item.get("c", "")
        raw_z = item.get("z")
        # 非交易時段 z 為 "-" 或 None，改用昨收 y
        if raw_z is None or raw_z == "-":
            raw_z = item.get("y")
        price = _safe_decimal(raw_z)
        yesterday = _safe_decimal(item.get("y"))
        open_price = _safe_decimal(item.get("o"))
        high = _safe_decimal(item.get("h"))
        low = _safe_decimal(item.get("l"))
        # v 是成交張數，1 張 = 1000 股
        raw_vol = item.get("v", "0")
        volume = int(raw_vol) * 1000 if raw_vol and raw_vol != "-" else 0

        # 五檔最佳買賣價取第一檔
        ask_prices = (item.get("a") or "0").split("_")
        bid_prices = (item.get("b") or "0").split("_")
        ask_price = _safe_decimal(ask_prices[0] if ask_prices else "0")
        bid_price = _safe_decimal(bid_prices[0] if bid_prices else "0")

        change = price - yesterday if yesterday else Decimal("0")
        change_pct = (
            float(change / yesterday * 100) if yesterday and yesterday != 0 else 0.0
        )

        # 解析時間
        date_str = item.get("d", "")
        time_str = item.get("t", "00:00:00")
        try:
            ts = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M:%S")
        except (ValueError, TypeError):
            ts = datetime.now(tz=timezone.utc)

        return StockQuote(
            code=code,
            market=MarketType.TW,
            price=price,
            open_price=open_price,
            high=high,
            low=low,
            volume=volume,
            amount=Decimal("0"),  # MIS API 不直接提供成交金額
            bid_price=bid_price,
            ask_price=ask_price,
            change=change,
            change_pct=round(change_pct, 2),
            timestamp=ts,
            source="twse_mis",
        )

    async def health_check(self) -> bool:
        """用台積電(2330)做 health check。"""
        try:
            if not self._client or self._client.is_closed:
                return False
            resp = await self._client.get(
                self._BASE_URL,
                params={"ex_ch": "tse_2330.tw", "json": "1", "_": str(int(time.time() * 1000))},
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


# ──────────────────────────────────────────────
# YFinanceQuoteSource — Yahoo Finance（台股/美股通用備援）
# ──────────────────────────────────────────────
class YFinanceQuoteSource(QuoteSource):
    """Yahoo Finance 報價來源（台股/美股通用備援）。

    - 台股代碼加上 .TW/.TWO 後綴
    - 美股直接使用 ticker
    - 延遲較大（15-30 分鐘美股, 台股盤後）
    """

    def __init__(self, market: MarketType = MarketType.TW) -> None:
        self._market = market

    @property
    def name(self) -> str:
        return "yfinance"

    async def connect(self) -> None:
        logger.info("YFinanceQuoteSource connected (market=%s)", self._market)

    async def disconnect(self) -> None:
        logger.info("YFinanceQuoteSource disconnected")

    def _to_yf_ticker(self, code: str) -> str:
        """將股票代碼轉為 yfinance ticker 格式。"""
        if self._market == MarketType.TW:
            # 上櫃股加 .TWO，上市股加 .TW
            suffix = ".TWO" if _is_otc(code) else ".TW"
            return f"{code}{suffix}"
        return code  # 美股直接用 ticker

    async def get_quote(self, code: str) -> StockQuote:
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_get_quote, code
        )

    def _sync_get_quote(self, code: str) -> StockQuote:
        """同步取得單檔報價（在 executor 中執行）。"""
        try:
            import yfinance as yf  # noqa: PLC0415
        except ImportError as exc:
            raise DataSourceError(
                "yfinance not installed", source=self.name
            ) from exc

        ticker_str = self._to_yf_ticker(code)
        try:
            ticker = yf.Ticker(ticker_str)
            info = ticker.fast_info
        except Exception as exc:  # noqa: BLE001
            raise DataSourceError(
                f"yfinance failed for {ticker_str}: {exc}", source=self.name
            ) from exc

        price = _safe_decimal(getattr(info, "last_price", None))
        if price == Decimal("0"):
            raise DataSourceError(
                f"yfinance returned no price for {ticker_str}", source=self.name
            )

        open_price = _safe_decimal(getattr(info, "open", None))
        high = _safe_decimal(getattr(info, "day_high", None))
        low = _safe_decimal(getattr(info, "day_low", None))
        volume = int(getattr(info, "last_volume", 0) or 0)
        prev_close = _safe_decimal(getattr(info, "previous_close", None))
        change = price - prev_close if prev_close else Decimal("0")
        change_pct = (
            float(change / prev_close * 100) if prev_close and prev_close != 0 else 0.0
        )

        return StockQuote(
            code=code,
            market=self._market,
            price=price,
            open_price=open_price,
            high=high,
            low=low,
            volume=volume,
            amount=Decimal("0"),
            bid_price=price,  # yfinance fast_info 無即時五檔
            ask_price=price,
            change=change,
            change_pct=round(change_pct, 2),
            timestamp=datetime.now(tz=timezone.utc),
            source="yfinance",
        )

    async def get_quotes_batch(self, codes: list[str]) -> list[StockQuote]:
        """批次取得多檔報價（並行執行）。"""
        tasks = [self.get_quote(code) for code in codes]
        results: list[StockQuote] = []
        for coro in asyncio.as_completed(tasks):
            try:
                quote = await coro
                results.append(quote)
            except DataSourceError as exc:
                logger.warning("YFinance batch item failed: %s", exc)
        if not results:
            raise DataSourceError("YFinance batch returned no results", source=self.name)
        return results

    async def health_check(self) -> bool:
        """嘗試取得一檔報價驗證連線。"""
        try:
            test_code = "2330" if self._market == MarketType.TW else "AAPL"
            await self.get_quote(test_code)
            return True
        except Exception:  # noqa: BLE001
            return False


# ──────────────────────────────────────────────
# LastGoodCacheSource — 最後成功值快取來源
# ──────────────────────────────────────────────
class LastGoodCacheSource(QuoteSource):
    """最後成功值快取來源（Redis / in-memory fallback）。

    讀取快取中的最後成功報價，回傳時標記 is_stale=True。
    若無 ICacheService 則使用 in-memory dict。
    """

    def __init__(
        self,
        market: MarketType,
        cache: ICacheService | None = None,
        memory_store: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._market = market
        self._cache = cache
        # in-memory fallback：key -> serialized quote dict
        self._memory: dict[str, dict[str, Any]] = memory_store if memory_store is not None else {}

    @property
    def name(self) -> str:
        return "last_good_cache"

    async def connect(self) -> None:
        logger.info("LastGoodCacheSource ready (market=%s)", self._market)

    async def disconnect(self) -> None:
        pass

    async def store(self, quote: StockQuote) -> None:
        """儲存報價到快取（供 QuoteAdapter 回寫）。"""
        key = _cache_key(self._market, quote.code)
        payload = self._serialize(quote)
        if self._cache:
            try:
                await self._cache.set(key, payload, ttl_seconds=_QUOTE_CACHE_TTL)
                return
            except Exception:  # noqa: BLE001
                logger.warning("Redis cache write failed, falling back to memory")
        self._memory[key] = payload

    async def get_quote(self, code: str) -> StockQuote:
        key = _cache_key(self._market, code)
        payload: dict[str, Any] | None = None

        if self._cache:
            try:
                raw = await self._cache.get(key)
                if raw is not None:
                    payload = raw if isinstance(raw, dict) else json.loads(raw)
            except Exception:  # noqa: BLE001
                logger.warning("Redis cache read failed for %s", key)

        if payload is None:
            payload = self._memory.get(key)

        if payload is None:
            raise DataSourceError(
                f"No cached quote for {code}", source=self.name
            )

        return self._deserialize(payload, is_stale=True)

    async def get_quotes_batch(self, codes: list[str]) -> list[StockQuote]:
        results: list[StockQuote] = []
        for code in codes:
            try:
                results.append(await self.get_quote(code))
            except DataSourceError:
                logger.debug("Cache miss for %s", code)
        if not results:
            raise DataSourceError("No cached quotes available", source=self.name)
        return results

    async def health_check(self) -> bool:
        # 快取來源永遠可用（只要記憶體在）
        if self._cache:
            try:
                return await self._cache.health_check()
            except Exception:  # noqa: BLE001
                pass
        return True  # in-memory 永遠 healthy

    @staticmethod
    def _serialize(quote: StockQuote) -> dict[str, Any]:
        return {
            "code": quote.code,
            "market": quote.market.value,
            "price": str(quote.price),
            "open_price": str(quote.open_price),
            "high": str(quote.high),
            "low": str(quote.low),
            "volume": quote.volume,
            "amount": str(quote.amount),
            "bid_price": str(quote.bid_price),
            "ask_price": str(quote.ask_price),
            "change": str(quote.change),
            "change_pct": quote.change_pct,
            "timestamp": quote.timestamp.isoformat(),
            "source": quote.source,
        }

    @staticmethod
    def _deserialize(data: dict[str, Any], *, is_stale: bool = False) -> StockQuote:
        return StockQuote(
            code=data["code"],
            market=MarketType(data["market"]),
            price=Decimal(data["price"]),
            open_price=Decimal(data["open_price"]),
            high=Decimal(data["high"]),
            low=Decimal(data["low"]),
            volume=int(data["volume"]),
            amount=Decimal(data["amount"]),
            bid_price=Decimal(data["bid_price"]),
            ask_price=Decimal(data["ask_price"]),
            change=Decimal(data["change"]),
            change_pct=float(data["change_pct"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data["source"],
            is_stale=is_stale,
        )


# ──────────────────────────────────────────────
# QuoteAdapter — Fallback Chain 編排器
# ──────────────────────────────────────────────
class QuoteAdapter(IQuoteAdapter):
    """報價適配器 — Fallback Chain 實作。

    台股 Chain: TWSE MIS -> YFinance -> LastGoodCache
    美股 Chain: YFinance -> LastGoodCache

    Features:
    - 健康檢查 + 自動降級
    - 成功報價自動回寫 LastGoodCache
    - 來源健康狀態追蹤
    """

    def __init__(
        self,
        config: QuoteSourceConfig,
        cache: ICacheService | None = None,
    ) -> None:
        self._config = config
        self._cache = cache

        # 共用 in-memory store 給所有 LastGoodCacheSource
        self._memory_store: dict[str, dict[str, Any]] = {}

        # Fallback chains（connect 後初始化）
        self._tw_chain: list[QuoteSource] = []
        self._us_chain: list[QuoteSource] = []
        self._tw_cache_source: LastGoodCacheSource | None = None
        self._us_cache_source: LastGoodCacheSource | None = None

        # 來源健康狀態
        self._source_health: dict[str, DataSourceHealth] = {}

    async def connect(self, market: MarketType) -> None:
        """建立指定市場的 Fallback Chain 並連線。"""
        if market == MarketType.TW:
            if not self._tw_chain:
                self._tw_cache_source = LastGoodCacheSource(
                    MarketType.TW, self._cache, self._memory_store
                )
                self._tw_chain = [
                    TWSEQuoteSource(),
                    YFinanceQuoteSource(MarketType.TW),
                    self._tw_cache_source,
                ]
            for src in self._tw_chain:
                try:
                    await src.connect()
                    self._source_health[src.name] = DataSourceHealth.HEALTHY
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to connect %s: %s", src.name, exc)
                    self._source_health[src.name] = DataSourceHealth.UNHEALTHY

        elif market == MarketType.US:
            if not self._us_chain:
                self._us_cache_source = LastGoodCacheSource(
                    MarketType.US, self._cache, self._memory_store
                )
                self._us_chain = [
                    YFinanceQuoteSource(MarketType.US),
                    self._us_cache_source,
                ]
            for src in self._us_chain:
                try:
                    await src.connect()
                    self._source_health[src.name] = DataSourceHealth.HEALTHY
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to connect %s: %s", src.name, exc)
                    self._source_health[src.name] = DataSourceHealth.UNHEALTHY

        logger.info("QuoteAdapter connected for %s", market.value)

    async def disconnect(self) -> None:
        """斷開所有來源連線。"""
        all_sources: list[QuoteSource] = [*self._tw_chain, *self._us_chain]
        for src in all_sources:
            try:
                await src.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error disconnecting %s: %s", src.name, exc)
        self._tw_chain.clear()
        self._us_chain.clear()
        self._tw_cache_source = None
        self._us_cache_source = None
        self._source_health.clear()
        logger.info("QuoteAdapter disconnected all sources")

    async def get_quote(self, code: str, market: MarketType) -> StockQuote:
        """嘗試 Fallback Chain 中每個來源，成功則回寫快取。

        若所有即時來源皆失敗，嘗試用 yfinance 取最近收盤價作為 fallback。
        """
        chain = self._get_chain(market)
        errors: list[str] = []

        for src in chain:
            try:
                quote = await src.get_quote(code)
                # 拒絕 price=0 的報價（非交易時段常見），觸發 fallback
                if quote.price == 0:
                    raise DataSourceError(
                        f"Price is 0 from {src.name} (likely outside trading hours)",
                        source=src.name,
                    )
                self._source_health[src.name] = DataSourceHealth.HEALTHY
                # 非快取來源的成功報價回寫 LastGoodCache
                if src.name != "last_good_cache":
                    await self._write_cache(market, quote)
                logger.debug("Quote for %s from %s", code, src.name)
                return quote
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{src.name}: {exc}")
                self._source_health[src.name] = DataSourceHealth.UNHEALTHY
                logger.warning("Source %s failed for %s: %s", src.name, code, exc)

        # 最後手段：從 yfinance 取最近一筆收盤價
        try:
            quote = await self._fallback_last_close(code, market)
            if quote:
                logger.info("Fallback to last close for %s: %s", code, quote.price)
                return quote
        except Exception as exc:  # noqa: BLE001
            errors.append(f"last_close_fallback: {exc}")

        raise QuoteUnavailableError(
            f"All sources failed for {code} ({market.value}): {'; '.join(errors)}"
        )

    async def _fallback_last_close(
        self, code: str, market: MarketType
    ) -> StockQuote | None:
        """用 yfinance 取最近一筆收盤價作為非交易時段報價。"""
        import yfinance as yf

        if market == MarketType.TW:
            suffix = ".TWO" if _is_otc(code) else ".TW"
        else:
            suffix = ""
        ticker_code = f"{code}{suffix}"
        ticker = yf.Ticker(ticker_code)
        df = await asyncio.to_thread(ticker.history, period="5d")
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        close = _safe_decimal(last["Close"])
        prev_close = _safe_decimal(df.iloc[-2]["Close"]) if len(df) >= 2 else close
        change = close - prev_close
        change_pct = float(change / prev_close * 100) if prev_close else 0.0
        return StockQuote(
            code=code,
            market=market,
            price=close,
            open_price=_safe_decimal(last["Open"]),
            high=_safe_decimal(last["High"]),
            low=_safe_decimal(last["Low"]),
            volume=int(last.get("Volume", 0)),
            amount=Decimal("0"),
            bid_price=close,
            ask_price=close,
            change=change,
            change_pct=round(change_pct, 2),
            timestamp=datetime.now(tz=timezone.utc),
            source="yfinance_last_close",
            is_stale=True,
        )

    async def get_quotes_batch(
        self, codes: list[str], market: MarketType
    ) -> list[StockQuote]:
        """批次取得報價，走 Fallback Chain。

        嘗試用每個來源的 batch 方法取得全部，成功就回寫快取。
        若某來源只成功部分，收集已成功的，剩餘用下一個來源補。
        """
        chain = self._get_chain(market)
        remaining = set(codes)
        results: dict[str, StockQuote] = {}
        errors: list[str] = []

        for src in chain:
            if not remaining:
                break
            try:
                batch = await src.get_quotes_batch(list(remaining))
                self._source_health[src.name] = DataSourceHealth.HEALTHY
                for q in batch:
                    results[q.code] = q
                    remaining.discard(q.code)
                    if src.name != "last_good_cache":
                        await self._write_cache(market, q)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{src.name}: {exc}")
                self._source_health[src.name] = DataSourceHealth.UNHEALTHY
                logger.warning("Batch source %s failed: %s", src.name, exc)

        if not results:
            raise QuoteUnavailableError(
                f"All sources failed for batch ({market.value}): {'; '.join(errors)}"
            )

        if remaining:
            logger.warning(
                "Missing quotes after all sources: %s", ", ".join(remaining)
            )

        # 回傳順序與輸入一致
        return [results[c] for c in codes if c in results]

    async def subscribe(
        self,
        codes: list[str],
        market: MarketType,
        callback: Any,
    ) -> None:
        """訂閱即時報價推送（Phase 3 WebSocket，目前僅 log 警告）。"""
        logger.warning(
            "subscribe() not yet implemented (Phase 3 WebSocket). "
            "Codes: %s, Market: %s",
            codes,
            market.value,
        )

    async def unsubscribe(self, codes: list[str]) -> None:
        """取消訂閱（Phase 3）。"""
        logger.warning("unsubscribe() not yet implemented (Phase 3)")

    def get_source_health(self) -> dict[str, DataSourceHealth]:
        """取得各資料源健康狀態。"""
        return dict(self._source_health)

    # ── 內部方法 ──────────────────────────────

    def _get_chain(self, market: MarketType) -> list[QuoteSource]:
        if market == MarketType.TW:
            if not self._tw_chain:
                raise QuoteUnavailableError(
                    f"QuoteAdapter not connected for {market.value}. Call connect() first."
                )
            return self._tw_chain
        if market == MarketType.US:
            if not self._us_chain:
                raise QuoteUnavailableError(
                    f"QuoteAdapter not connected for {market.value}. Call connect() first."
                )
            return self._us_chain
        raise QuoteUnavailableError(f"Unsupported market: {market}")

    async def _write_cache(self, market: MarketType, quote: StockQuote) -> None:
        """回寫快取（同時寫 Redis 和 in-memory）。"""
        cache_src = (
            self._tw_cache_source
            if market == MarketType.TW
            else self._us_cache_source
        )
        if cache_src:
            try:
                await cache_src.store(quote)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cache write failed for %s: %s", quote.code, exc)
