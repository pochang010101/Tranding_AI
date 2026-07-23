"""盤中雷達 — 即時監控盤中異動與訊號觸發。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

from atlas.enums import DetectorType, MarketType, SignalType
from atlas.events import DetectorTriggered
from atlas.interfaces.application import IRealtimeRadar
from atlas.models.signals import DetectorAlert, Signal

if TYPE_CHECKING:
    from atlas.infrastructure.data_manager import DataManager
    from atlas.infrastructure.event_bus import EventBus
    from atlas.strategy.indicator_lib import IndicatorLibrary

logger = logging.getLogger(__name__)

# 所有 11 偵測器
_ALL_DETECTORS = list(DetectorType)


class RealtimeRadar(IRealtimeRadar):
    """盤中即時監控引擎。

    管理 11 偵測器，定期掃描 watchlist，
    透過 EventBus 發布 DetectorAlert 與 Signal。
    """

    def __init__(
        self,
        data_manager: DataManager,
        indicator_lib: IndicatorLibrary,
        event_bus: EventBus | None = None,
        scan_interval: float = 30.0,
    ) -> None:
        self._dm = data_manager
        self._ind = indicator_lib
        self._event_bus = event_bus
        self._scan_interval = scan_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._enabled_detectors: set[DetectorType] = set(_ALL_DETECTORS)
        self._alerts_today: list[DetectorAlert] = []
        self._signals_today: list[Signal] = []
        self._watchlist: list[str] = []

    async def start(self, market: MarketType) -> None:
        """啟動盤中雷達。"""
        if self._running:
            return
        self._running = True
        self._alerts_today.clear()
        self._signals_today.clear()
        self._task = asyncio.create_task(self._scan_loop(market))
        logger.info("Realtime radar started for %s", market.value)

    async def stop(self) -> None:
        """停止盤中雷達。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Realtime radar stopped. Alerts=%d Signals=%d",
                     len(self._alerts_today), len(self._signals_today))

    async def is_running(self) -> bool:
        return self._running

    async def enable_detector(self, detector_type: DetectorType) -> None:
        self._enabled_detectors.add(detector_type)

    async def disable_detector(self, detector_type: DetectorType) -> None:
        self._enabled_detectors.discard(detector_type)

    async def get_active_detectors(self) -> list[DetectorType]:
        return list(self._enabled_detectors)

    async def get_alerts_today(self, market: MarketType) -> list[DetectorAlert]:
        return list(self._alerts_today)

    async def get_signals_today(self, market: MarketType) -> list[Signal]:
        return list(self._signals_today)

    async def get_intraday_summary(self, market: MarketType) -> dict[str, Any]:
        """產出盤中摘要。"""
        detector_counts: dict[str, int] = {}
        for alert in self._alerts_today:
            dt = alert.detector_type.value
            detector_counts[dt] = detector_counts.get(dt, 0) + 1

        buy_signals = [s for s in self._signals_today if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in self._signals_today if s.signal_type == SignalType.SELL]

        return {
            "market": market.value,
            "date": date.today().isoformat(),
            "total_alerts": len(self._alerts_today),
            "total_signals": len(self._signals_today),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals),
            "detector_breakdown": detector_counts,
            "top_alert_codes": self._get_top_codes(self._alerts_today, 10),
        }

    def set_watchlist(self, codes: list[str]) -> None:
        self._watchlist = codes

    # ── 內部方法 ─────────────────────────────────

    async def _scan_loop(self, market: MarketType) -> None:
        """主掃描迴圈。"""
        while self._running:
            try:
                await self._run_detectors(market)
            except Exception as exc:
                logger.error("Radar scan error: %s", exc)
            await asyncio.sleep(self._scan_interval)

    async def _run_detectors(self, market: MarketType) -> None:
        """執行所有啟用的偵測器。"""
        for code in self._watchlist:
            for detector in self._enabled_detectors:
                try:
                    alert = await self._check_detector(code, market, detector)
                    if alert:
                        self._alerts_today.append(alert)
                        if self._event_bus:
                            await self._event_bus.publish(DetectorTriggered(
                                detector_type=alert.detector_type,
                                code=alert.code,
                                market=market,
                                severity=alert.severity,
                                price=alert.price,
                                detail=alert.detail,
                            ))
                except Exception as exc:
                    logger.debug("Detector %s failed on %s: %s", detector.value, code, exc)

    async def _check_detector(
        self, code: str, market: MarketType, detector: DetectorType
    ) -> DetectorAlert | None:
        """路由到各偵測器實作。"""
        dispatch = {
            DetectorType.VOLUME_BREAKOUT: self._detect_volume_breakout,
            DetectorType.LARGE_ORDER: self._detect_large_order,
            DetectorType.SPIKE: self._detect_spike,
            DetectorType.MA_BREAK: self._detect_ma_break,
            DetectorType.VOLUME_DIVERGE: self._detect_volume_diverge,
        }
        handler = dispatch.get(detector)
        if handler:
            return await handler(code, market)
        return None

    @staticmethod
    def _get_top_codes(alerts: list[DetectorAlert], top_n: int) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for a in alerts:
            counts[a.code] = counts.get(a.code, 0) + 1
        sorted_codes = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"code": c, "count": n} for c, n in sorted_codes[:top_n]]

    # ══════════════════════════════════════════════
    # 5 偵測器實作
    # ══════════════════════════════════════════════

    async def _detect_volume_breakout(
        self, code: str, market: MarketType
    ) -> DetectorAlert | None:
        """爆量啟動：當日成交量 > 5日均量 × 2。"""
        try:
            df = await self._fetch_history(code, period="1mo")
            if df is None or len(df) < 6:
                return None
            avg_vol_5 = df["volume"].iloc[-6:-1].mean()
            today_vol = df["volume"].iloc[-1]
            if avg_vol_5 <= 0:
                return None
            ratio = today_vol / avg_vol_5
            if ratio < 2.0:
                return None
            close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            direction = "漲" if close >= prev_close else "跌"
            severity = 3 if ratio >= 4.0 else 2 if ratio >= 3.0 else 1
            return DetectorAlert(
                detector_type=DetectorType.VOLUME_BREAKOUT,
                code=code,
                market=market,
                severity=severity,
                price=close,
                volume=int(today_vol),
                detail=f"爆量{direction} {ratio:.1f}x (今量{today_vol/1000:.0f}張 vs 5日均{avg_vol_5/1000:.0f}張)",
            )
        except Exception as exc:
            logger.debug("volume_breakout %s: %s", code, exc)
            return None

    async def _detect_large_order(
        self, code: str, market: MarketType
    ) -> DetectorAlert | None:
        """大單異常：當日成交量 > 20日均量 × 3（模擬大單集中）。"""
        try:
            df = await self._fetch_history(code, period="2mo")
            if df is None or len(df) < 21:
                return None
            avg_vol_20 = df["volume"].iloc[-21:-1].mean()
            today_vol = df["volume"].iloc[-1]
            if avg_vol_20 <= 0:
                return None
            ratio = today_vol / avg_vol_20
            if ratio < 3.0:
                return None
            close = float(df["close"].iloc[-1])
            severity = 3 if ratio >= 5.0 else 2
            return DetectorAlert(
                detector_type=DetectorType.LARGE_ORDER,
                code=code,
                market=market,
                severity=severity,
                price=close,
                volume=int(today_vol),
                detail=f"量能異常 {ratio:.1f}x 20日均量 (疑似大單進出)",
            )
        except Exception as exc:
            logger.debug("large_order %s: %s", code, exc)
            return None

    async def _detect_spike(
        self, code: str, market: MarketType
    ) -> DetectorAlert | None:
        """急拉急殺：當日漲跌幅 > 3%。"""
        try:
            df = await self._fetch_history(code, period="5d")
            if df is None or len(df) < 2:
                return None
            close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            if prev_close <= 0:
                return None
            change_pct = (close - prev_close) / prev_close * 100
            if abs(change_pct) < 3.0:
                return None
            if change_pct > 0:
                label = "急拉"
                severity = 3 if change_pct >= 7.0 else 2 if change_pct >= 5.0 else 1
            else:
                label = "急殺"
                severity = 3 if change_pct <= -7.0 else 2 if change_pct <= -5.0 else 1
            return DetectorAlert(
                detector_type=DetectorType.SPIKE,
                code=code,
                market=market,
                severity=severity,
                price=close,
                volume=int(df["volume"].iloc[-1]),
                detail=f"{label} {change_pct:+.2f}% ({prev_close:.1f}→{close:.1f})",
            )
        except Exception as exc:
            logger.debug("spike %s: %s", code, exc)
            return None

    async def _detect_ma_break(
        self, code: str, market: MarketType
    ) -> DetectorAlert | None:
        """均線跌破/突破：收盤跌破 MA8 (前日在上方) 或突破 MA8 (前日在下方)。"""
        try:
            df = await self._fetch_history(code, period="2mo")
            if df is None or len(df) < 10:
                return None
            ind = self._ind.calculate_all(df)
            if "MA8" not in ind.columns:
                return None
            ma8_today = ind["MA8"].iloc[-1]
            ma8_prev = ind["MA8"].iloc[-2]
            close_today = float(df["close"].iloc[-1])
            close_prev = float(df["close"].iloc[-2])

            if pd.isna(ma8_today) or pd.isna(ma8_prev):
                return None

            # 跌破：前日收盤 > MA8，今日收盤 < MA8
            if close_prev > ma8_prev and close_today < ma8_today:
                return DetectorAlert(
                    detector_type=DetectorType.MA_BREAK,
                    code=code,
                    market=market,
                    severity=2,
                    price=close_today,
                    volume=int(df["volume"].iloc[-1]),
                    detail=f"跌破 MA8 ({ma8_today:.1f})，前日收{close_prev:.1f} 在MA上方",
                )

            # 突破：前日收盤 < MA8，今日收盤 > MA8
            if close_prev < ma8_prev and close_today > ma8_today:
                return DetectorAlert(
                    detector_type=DetectorType.MA_BREAK,
                    code=code,
                    market=market,
                    severity=2,
                    price=close_today,
                    volume=int(df["volume"].iloc[-1]),
                    detail=f"突破 MA8 ({ma8_today:.1f})，前日收{close_prev:.1f} 在MA下方",
                )

            return None
        except Exception as exc:
            logger.debug("ma_break %s: %s", code, exc)
            return None

    async def _detect_volume_diverge(
        self, code: str, market: MarketType
    ) -> DetectorAlert | None:
        """價量背離：價漲量縮 或 價跌量增。"""
        try:
            df = await self._fetch_history(code, period="1mo")
            if df is None or len(df) < 6:
                return None
            close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            today_vol = float(df["volume"].iloc[-1])
            avg_vol_5 = float(df["volume"].iloc[-6:-1].mean())

            if prev_close <= 0 or avg_vol_5 <= 0:
                return None

            change_pct = (close - prev_close) / prev_close * 100
            vol_ratio = today_vol / avg_vol_5

            # 價漲量縮：漲 > 1% 但量 < 5日均量 60%
            if change_pct > 1.0 and vol_ratio < 0.6:
                return DetectorAlert(
                    detector_type=DetectorType.VOLUME_DIVERGE,
                    code=code,
                    market=market,
                    severity=2,
                    price=close,
                    volume=int(today_vol),
                    detail=f"價漲量縮 漲{change_pct:+.1f}% 但量僅 {vol_ratio:.0%} 均量（上漲動能不足）",
                )

            # 價跌量增：跌 > 1% 且量 > 5日均量 150%
            if change_pct < -1.0 and vol_ratio > 1.5:
                return DetectorAlert(
                    detector_type=DetectorType.VOLUME_DIVERGE,
                    code=code,
                    market=market,
                    severity=2 if change_pct > -3.0 else 3,
                    price=close,
                    volume=int(today_vol),
                    detail=f"價跌量增 跌{change_pct:+.1f}% 量達 {vol_ratio:.0%} 均量（恐慌賣壓）",
                )

            return None
        except Exception as exc:
            logger.debug("volume_diverge %s: %s", code, exc)
            return None

    # ── 共用資料取得 ──────────────────────────────

    async def _fetch_history(self, code: str, period: str = "1mo") -> pd.DataFrame | None:
        """取得歷史 K 線資料（優先用 DataManager，fallback 到 yfinance）。"""
        if self._dm:
            try:
                bars = await self._dm.fetch_daily_bars(code, MarketType.TW, days=60)
                if bars:
                    rows = [{"open": b.open, "high": b.high, "low": b.low,
                             "close": b.close, "volume": b.volume} for b in bars]
                    return pd.DataFrame(rows)
            except Exception:
                pass

        # fallback: yfinance（同步）
        try:
            import yfinance as yf

            from atlas.constants import is_otc  # noqa: I001
            suffix = ".TWO" if is_otc(code) else ".TW"
            ticker = yf.Ticker(f"{code}{suffix}")
            df = ticker.history(period=period)
            if df is not None and not df.empty:
                df = df.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume",
                })
                return df
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════
# 同步掃描函數（供 Streamlit UI 直接呼叫）
# ══════════════════════════════════════════════

def scan_watchlist_sync(
    codes: list[str],
    indicator_lib: Any = None,
) -> list[dict[str, Any]]:
    """同步掃描一組股票，回傳偵測結果列表。

    不依賴 async loop，直接用 yfinance 取資料，供 Streamlit 頁面使用。
    每支股票跑 5 個偵測器，有觸發才加入結果。
    """
    import yfinance as yf

    from atlas.constants import is_otc

    if indicator_lib is None:
        from atlas.strategy.indicator_lib import IndicatorLibrary
        indicator_lib = IndicatorLibrary()

    results: list[dict[str, Any]] = []
    from atlas.constants import TW_TZ
    now_str = datetime.now(TW_TZ).strftime("%H:%M")

    # 建立代碼→名稱對照表（從 TWSE/TPEx 全市場快取取得）
    code_name_map: dict[str, str] = {}
    try:
        from atlas.infrastructure.twse_bulk import fetch_tpex_daily_all, fetch_twse_daily_all
        for df_src in [fetch_twse_daily_all(), fetch_tpex_daily_all()]:
            if not df_src.empty and "code" in df_src.columns and "name" in df_src.columns:
                for _, row in df_src[["code", "name"]].iterrows():
                    code_name_map[str(row["code"])] = str(row["name"])
    except Exception:
        pass

    # 批次下載歷史資料（效率遠高於逐一下載）
    tickers = [f"{c}.TWO" if is_otc(c) else f"{c}.TW" for c in codes]
    try:
        bulk_data = yf.download(tickers, period="2mo", progress=False,
                                threads=True, auto_adjust=True, group_by="ticker")
    except Exception as exc:
        logger.warning("yfinance bulk download failed: %s", exc)
        return results

    for code, ticker in zip(codes, tickers, strict=False):
        try:
            if len(codes) == 1:
                df = bulk_data.copy()
            else:
                if ticker not in bulk_data.columns.get_level_values(0):
                    continue
                df = bulk_data[ticker].copy()

            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = df.dropna(subset=["close"])
            if len(df) < 6:
                continue

            close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            today_vol = float(df["volume"].iloc[-1])

            # --- 爆量啟動 ---
            avg_vol_5 = float(df["volume"].iloc[-6:-1].mean())
            if avg_vol_5 > 0:
                vol_ratio_5 = today_vol / avg_vol_5
                if vol_ratio_5 >= 2.0:
                    direction = "漲" if close >= prev_close else "跌"
                    sev = 3 if vol_ratio_5 >= 4.0 else 2 if vol_ratio_5 >= 3.0 else 1
                    results.append({
                        "time": now_str, "detector": "爆量啟動", "code": code, "name": code_name_map.get(code, ""),
                        "direction": "BUY" if close >= prev_close else "ALERT",
                        "price": close, "severity": sev,
                        "detail": f"爆量{direction} {vol_ratio_5:.1f}x "
                                  f"(今{today_vol/1000:.0f}張 vs 5日均{avg_vol_5/1000:.0f}張)",
                    })

            # --- 大單異常 ---
            if len(df) >= 21:
                avg_vol_20 = float(df["volume"].iloc[-21:-1].mean())
                if avg_vol_20 > 0:
                    vol_ratio_20 = today_vol / avg_vol_20
                    if vol_ratio_20 >= 3.0:
                        sev = 3 if vol_ratio_20 >= 5.0 else 2
                        results.append({
                            "time": now_str, "detector": "大單異常", "code": code, "name": code_name_map.get(code, ""),
                            "direction": "ALERT",
                            "price": close, "severity": sev,
                            "detail": f"量能異常 {vol_ratio_20:.1f}x 20日均量 (疑似大單進出)",
                        })

            # --- 急拉急殺 ---
            if prev_close > 0:
                change_pct = (close - prev_close) / prev_close * 100
                if abs(change_pct) >= 3.0:
                    if change_pct > 0:
                        label, sig_dir = "急拉", "BUY"
                        sev = 3 if change_pct >= 7.0 else 2 if change_pct >= 5.0 else 1
                    else:
                        label, sig_dir = "急殺", "SELL"
                        sev = 3 if change_pct <= -7.0 else 2 if change_pct <= -5.0 else 1
                    results.append({
                        "time": now_str, "detector": "急拉急殺", "code": code, "name": code_name_map.get(code, ""),
                        "direction": sig_dir,
                        "price": close, "severity": sev,
                        "detail": f"{label} {change_pct:+.2f}% ({prev_close:.1f}→{close:.1f})",
                    })

            # --- 均線跌破/突破 ---
            if len(df) >= 10:
                ind = indicator_lib.calculate_all(df)
                if "MA8" in ind.columns:
                    ma8_today = ind["MA8"].iloc[-1]
                    ma8_prev = ind["MA8"].iloc[-2]
                    close_prev = float(df["close"].iloc[-2])
                    if not (pd.isna(ma8_today) or pd.isna(ma8_prev)):
                        if close_prev > ma8_prev and close < ma8_today:
                            results.append({
                                "time": now_str, "detector": "均線跌破", "code": code, "name": code_name_map.get(code, ""),
                                "direction": "SELL",
                                "price": close, "severity": 2,
                                "detail": f"跌破 MA8 ({ma8_today:.1f})，"
                                          f"前日收{close_prev:.1f} 在MA上方",
                            })
                        elif close_prev < ma8_prev and close > ma8_today:
                            results.append({
                                "time": now_str, "detector": "均線突破", "code": code, "name": code_name_map.get(code, ""),
                                "direction": "BUY",
                                "price": close, "severity": 2,
                                "detail": f"突破 MA8 ({ma8_today:.1f})，"
                                          f"前日收{close_prev:.1f} 在MA下方",
                            })

            # --- 價量背離 ---
            if avg_vol_5 > 0 and prev_close > 0:
                change_pct = (close - prev_close) / prev_close * 100
                vr = today_vol / avg_vol_5
                if change_pct > 1.0 and vr < 0.6:
                    results.append({
                        "time": now_str, "detector": "價量背離", "code": code, "name": code_name_map.get(code, ""),
                        "direction": "ALERT",
                        "price": close, "severity": 2,
                        "detail": f"價漲量縮 漲{change_pct:+.1f}% "
                                  f"但量僅 {vr:.0%} 均量（上漲動能不足）",
                    })
                elif change_pct < -1.0 and vr > 1.5:
                    sev = 2 if change_pct > -3.0 else 3
                    results.append({
                        "time": now_str, "detector": "價量背離", "code": code, "name": code_name_map.get(code, ""),
                        "direction": "SELL",
                        "price": close, "severity": sev,
                        "detail": f"價跌量增 跌{change_pct:+.1f}% "
                                  f"量達 {vr:.0%} 均量（恐慌賣壓）",
                    })

        except Exception as exc:
            logger.debug("scan_watchlist_sync %s: %s", code, exc)
            continue

    # 按嚴重度降序
    results.sort(key=lambda x: x.get("severity", 0), reverse=True)
    return results
