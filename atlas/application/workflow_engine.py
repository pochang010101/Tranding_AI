"""工作流引擎 — 編排盤前/盤中/盤後 SOP 自動化流程。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType
from atlas.interfaces.application import IWorkflowEngine

if TYPE_CHECKING:
    from atlas.application.conclusion_engine import ConclusionEngine
    from atlas.application.realtime_radar import RealtimeRadar
    from atlas.application.screener_engine import ScreenerEngine
    from atlas.domain.international import InternationalMarket
    from atlas.domain.market_regime import MarketRegimeService
    from atlas.domain.sentiment import SentimentService
    from atlas.domain.universe import UniverseManager
    from atlas.infrastructure.data_manager import DataManager
    from atlas.infrastructure.notification_hub import NotificationHub
    from atlas.strategy.gap_predictor import GapPredictor

logger = logging.getLogger(__name__)


class WorkflowEngine(IWorkflowEngine):
    """工作流引擎。

    管理六大工作流：
    - pre_market: 盤前 SOP（國際行情→缺口預測→環境感知→情緒→推播）
    - intraday: 盤中監控（啟動雷達→定期掃描→推播告警）
    - post_market: 盤後 SOP（選股掃描→結論→回測更新→推播報告）
    - ipo_scan: IPO 掃描
    - weekly_report: 週報產出
    - monthly_rebuild: 月度重建股票池
    """

    def __init__(
        self,
        market: MarketType = MarketType.TW,
        screener: ScreenerEngine | None = None,
        conclusion: ConclusionEngine | None = None,
        regime: MarketRegimeService | None = None,
        sentiment: SentimentService | None = None,
        international: InternationalMarket | None = None,
        gap_predictor: GapPredictor | None = None,
        radar: RealtimeRadar | None = None,
        universe: UniverseManager | None = None,
        notification: NotificationHub | None = None,
        data_manager: DataManager | None = None,
    ) -> None:
        self._market = market
        self._screener = screener
        self._conclusion = conclusion
        self._regime = regime
        self._sentiment = sentiment
        self._intl = international
        self._gap = gap_predictor
        self._radar = radar
        self._universe = universe
        self._notification = notification
        self._data_manager = data_manager
        self._history: list[dict[str, Any]] = []
        self._status: dict[str, dict[str, Any]] = {}

    async def run(self, workflow_name: str) -> dict[str, Any]:
        """執行指定工作流。"""
        start_time = datetime.utcnow()
        self._status[workflow_name] = {"status": "running", "started_at": start_time.isoformat()}

        try:
            handler = {
                "pre_market": self._run_pre_market,
                "intraday": self._run_intraday,
                "post_market": self._run_post_market,
                "ipo_scan": self._run_ipo_scan,
                "weekly_report": self._run_weekly_report,
                "monthly_rebuild": self._run_monthly_rebuild,
            }.get(workflow_name)

            if not handler:
                raise ValueError(f"Unknown workflow: {workflow_name}")

            result = await handler()
            elapsed = (datetime.utcnow() - start_time).total_seconds()

            record = {
                "workflow": workflow_name,
                "date": date.today().isoformat(),
                "status": "completed",
                "elapsed_sec": round(elapsed, 1),
                "result": result,
            }
            self._history.append(record)
            self._status[workflow_name] = {
                "status": "completed",
                "last_run": start_time.isoformat(),
                "elapsed_sec": round(elapsed, 1),
            }
            logger.info("Workflow '%s' completed in %.1fs", workflow_name, elapsed)
            return result

        except Exception as exc:
            self._status[workflow_name] = {"status": "failed", "error": str(exc)}
            self._history.append({
                "workflow": workflow_name,
                "date": date.today().isoformat(),
                "status": "failed",
                "error": str(exc),
            })
            logger.error("Workflow '%s' failed: %s", workflow_name, exc)
            raise

    async def get_status(self, workflow_name: str) -> dict[str, Any]:
        return self._status.get(workflow_name, {"status": "never_run"})

    async def get_execution_history(
        self,
        workflow_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        results = self._history
        if workflow_name:
            results = [h for h in results if h["workflow"] == workflow_name]
        if start_date:
            results = [h for h in results if h["date"] >= start_date.isoformat()]
        if end_date:
            results = [h for h in results if h["date"] <= end_date.isoformat()]
        return results

    # ── 工作流實作 ────────────────────────────────

    async def _run_pre_market(self) -> dict[str, Any]:
        """盤前 SOP：國際行情 → 缺口預測 → 環境感知 → 情緒。"""
        result: dict[str, Any] = {"steps": []}

        # Step 1: 國際行情
        if self._intl:
            us_data = await self._intl.fetch_us_close()
            futures = await self._intl.fetch_futures(self._market)
            result["us_close"] = us_data
            result["futures"] = futures
            result["steps"].append("fetch_international")

            # Step 2: 缺口預測
            if self._gap:
                gap = await self._gap.predict(us_data, futures)
                result["gap_prediction"] = gap
                result["steps"].append("gap_prediction")

        # Step 3: 大盤環境
        if self._regime:
            regime = await self._regime.update(self._market)
            result["regime"] = {"state": regime.state.value, "strength": regime.trend_strength}
            result["steps"].append("regime_update")

        # Step 4: 市場情緒
        if self._sentiment:
            sentiment = await self._sentiment.calculate(self._market)
            result["sentiment"] = {"level": sentiment.level.value, "index": sentiment.index_value}
            result["steps"].append("sentiment_update")

        return result

    async def _run_intraday(self) -> dict[str, Any]:
        """盤中監控：啟動雷達。"""
        if self._radar:
            await self._radar.start(self._market)
            return {"status": "radar_started", "market": self._market.value}
        return {"status": "no_radar_configured"}

    async def _run_post_market(self) -> dict[str, Any]:
        """盤後 SOP：停止雷達 → 資料更新 → 選股 → 結論。"""
        result: dict[str, Any] = {"steps": []}

        if self._radar:
            summary = await self._radar.get_intraday_summary(self._market)
            await self._radar.stop()
            result["intraday_summary"] = summary
            result["steps"].append("radar_stopped")

        # 資料自動更新：日K + 法人買賣超 + 融資融券
        if self._data_manager:
            data_result = await self._update_daily_data()
            result["data_update"] = data_result
            result["steps"].append("data_update")

        if self._screener:
            scan = await self._screener.scan(self._market, top_n=50)
            result["scan_count"] = len(scan)
            result["top_5"] = [
                {"code": s.code, "score": s.axis_score.total_score, "level": s.conclusion.name}
                for s in scan[:5]
            ]
            result["steps"].append("screener_scan")

        return result

    async def _update_daily_data(self) -> dict[str, Any]:
        """盤後自動拉取並儲存當日資料。"""
        today = date.today()
        update_result: dict[str, Any] = {}

        try:
            # 全市場日K
            bars = await self._data_manager.fetch_daily_all(self._market, today)
            update_result["daily_bars"] = len(bars)
        except Exception as exc:
            logger.warning("Daily bars update failed: %s", exc)
            update_result["daily_bars_error"] = str(exc)

        try:
            # 法人買賣超
            flow_df = await self._data_manager.fetch_institutional_flow(today, today)
            update_result["institutional_flow_rows"] = len(flow_df) if flow_df is not None else 0
        except Exception as exc:
            logger.warning("Institutional flow update failed: %s", exc)
            update_result["institutional_flow_error"] = str(exc)

        try:
            # 融資融券
            margin_df = await self._data_manager.fetch_margin_trading(today, today)
            update_result["margin_trading_rows"] = len(margin_df) if margin_df is not None else 0
        except Exception as exc:
            logger.warning("Margin trading update failed: %s", exc)
            update_result["margin_trading_error"] = str(exc)

        logger.info("Daily data update: %s", update_result)
        return update_result

    async def _run_ipo_scan(self) -> dict[str, Any]:
        return {"status": "placeholder", "message": "IPO scan via IPOModule"}

    async def _run_weekly_report(self) -> dict[str, Any]:
        return {"status": "placeholder", "message": "Weekly report generation"}

    async def _run_monthly_rebuild(self) -> dict[str, Any]:
        if self._universe:
            codes = await self._universe.build_universe(self._market, force_rebuild=True)
            return {"status": "rebuilt", "universe_size": len(codes)}
        return {"status": "no_universe_manager"}
