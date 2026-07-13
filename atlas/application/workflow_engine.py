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
    from atlas.domain.portfolio import PortfolioManager
    from atlas.domain.sentiment import SentimentService
    from atlas.domain.universe import UniverseManager
    from atlas.infrastructure.data_manager import DataManager
    from atlas.infrastructure.notification_hub import NotificationHub
    from atlas.strategy.gap_predictor import GapPredictor
    from atlas.strategy.ipo_module import IPOModule

logger = logging.getLogger(__name__)


class WorkflowEngine(IWorkflowEngine):
    """工作流引擎。

    管理八大工作流：
    - pre_market: 盤前 SOP（國際行情→缺口預測→環境感知→情緒→推播）
    - intraday: 盤中監控（啟動雷達→定期掃描→推播告警）
    - post_market: 盤後 SOP（選股掃描→結論→回測更新→推播報告）
    - ipo_scan: IPO 掃描
    - weekly_report: 週報產出
    - monthly_rebuild: 月度重建股票池
    - backup_db: 資料庫備份（每日 14:00）
    - retrain_model: ML 模型重訓（每週日 21:00）
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
        ipo_module: IPOModule | None = None,
        portfolio: PortfolioManager | None = None,
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
        self._ipo = ipo_module
        self._portfolio = portfolio
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
                "backup_db": self._run_backup_db,
                "retrain_model": self._run_retrain_model,
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

            # 自動推播工作流完成通知
            await self._notify_workflow_done(workflow_name, result, elapsed)

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
        """IPO 掃描：公開申購 + 蜜月期追蹤 + 歷史勝率。"""
        result: dict[str, Any] = {"steps": []}

        if not self._ipo:
            return {"status": "no_ipo_module"}

        upcoming = await self._ipo.scan_upcoming()
        result["upcoming"] = upcoming
        result["upcoming_count"] = len(upcoming)
        result["steps"].append("scan_upcoming")

        win_rate = await self._ipo.get_historical_win_rate()
        result["historical_win_rate"] = win_rate
        result["steps"].append("historical_stats")

        return result

    async def _run_weekly_report(self) -> dict[str, Any]:
        """週報：持倉績效 + 本週訊號摘要 + 環境概況。"""
        from datetime import timedelta

        result: dict[str, Any] = {"steps": [], "date": date.today().isoformat()}
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

        # 持倉績效
        if self._portfolio:
            stats = await self._portfolio.get_performance_stats()
            positions = await self._portfolio.get_open_positions(self._market)
            result["performance"] = stats
            result["open_positions"] = len(positions)
            result["steps"].append("portfolio_stats")

        # 本週選股歷史
        history = await self.get_execution_history(
            workflow_name="post_market",
            start_date=week_start,
            end_date=today,
        )
        result["post_market_runs"] = len(history)
        result["steps"].append("weekly_history")

        # 環境概況
        if self._regime:
            regime = await self._regime.update(self._market)
            result["regime"] = {"state": regime.state.value, "strength": regime.trend_strength}
            result["steps"].append("regime_snapshot")

        if self._sentiment:
            sentiment = await self._sentiment.calculate(self._market)
            result["sentiment"] = {"level": sentiment.level.value, "index": sentiment.index_value}
            result["steps"].append("sentiment_snapshot")

        return result

    async def _run_monthly_rebuild(self) -> dict[str, Any]:
        if self._universe:
            codes = await self._universe.build_universe(self._market, force_rebuild=True)
            return {"status": "rebuilt", "universe_size": len(codes)}
        return {"status": "no_universe_manager"}

    async def _run_backup_db(self) -> dict[str, Any]:
        """資料庫備份：呼叫 scripts/backup_db.sh。"""
        import shutil

        script = shutil.which("bash")
        cmd = [script or "bash", "scripts/backup_db.sh"] if script else ["scripts/backup_db.sh"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            output = stdout.decode(errors="replace") if stdout else ""
            if proc.returncode == 0:
                logger.info("backup_db completed:\n%s", output)
                return {"status": "success", "output": output[-500:]}  # 截取最後 500 字元
            else:
                logger.error("backup_db failed (rc=%d):\n%s", proc.returncode, output)
                return {"status": "failed", "returncode": proc.returncode, "output": output[-500:]}
        except TimeoutError:
            logger.error("backup_db timed out after 300s")
            return {"status": "timeout"}
        except Exception as exc:
            logger.error("backup_db error: %s", exc)
            return {"status": "error", "error": str(exc)}

    async def _run_retrain_model(self) -> dict[str, Any]:
        """ML 模型重訓：呼叫 scripts/retrain_model.sh。"""
        import shutil

        script = shutil.which("bash")
        cmd = [script or "bash", "scripts/retrain_model.sh"] if script else ["scripts/retrain_model.sh"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            # 訓練可能耗時較長，給 30 分鐘
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1800)
            output = stdout.decode(errors="replace") if stdout else ""
            if proc.returncode == 0:
                logger.info("retrain_model completed:\n%s", output)
                return {"status": "success", "output": output[-500:]}
            else:
                logger.error("retrain_model failed (rc=%d):\n%s", proc.returncode, output)
                return {"status": "failed", "returncode": proc.returncode, "output": output[-500:]}
        except TimeoutError:
            logger.error("retrain_model timed out after 1800s")
            return {"status": "timeout"}
        except Exception as exc:
            logger.error("retrain_model error: %s", exc)
            return {"status": "error", "error": str(exc)}

    # ── 通知推播 ────────────────────────────────

    async def _notify_workflow_done(
        self,
        workflow_name: str,
        result: dict[str, Any],
        elapsed: float,
    ) -> None:
        """工作流完成後自動推播通知。"""
        if not self._notification:
            return

        from atlas.models.notification import NotificationPayload

        title_map = {
            "pre_market": "盤前分析完成",
            "intraday": "盤中雷達已啟動",
            "post_market": "盤後選股完成",
            "ipo_scan": "IPO 掃描完成",
            "weekly_report": "週報已產出",
            "monthly_rebuild": "月度重建完成",
            "backup_db": "資料庫備份完成",
            "retrain_model": "ML 模型重訓完成",
        }
        title = f"📊 {title_map.get(workflow_name, workflow_name)}"
        body = self._format_workflow_body(workflow_name, result, elapsed)
        priority = 3 if workflow_name in ("post_market", "weekly_report") else 2

        payload = NotificationPayload(
            title=title,
            body=body,
            channel="discord",
            priority=priority,
            category="daily_report" if "market" in workflow_name or "report" in workflow_name else "system",
            mute_check=True,
        )

        try:
            await self._notification.send(payload)
        except Exception as exc:
            logger.warning("Notification failed for '%s': %s", workflow_name, exc)

    @staticmethod
    def _format_workflow_body(
        workflow_name: str,
        result: dict[str, Any],
        elapsed: float,
    ) -> str:
        """格式化工作流結果為推播訊息。"""
        lines = [f"⏱ 耗時 {elapsed:.1f}s"]

        if workflow_name == "pre_market":
            if "gap_prediction" in result:
                lines.append(f"缺口預測: {result['gap_prediction']}")
            if "regime" in result:
                lines.append(f"環境: {result['regime'].get('state', '?')}")
            if "sentiment" in result:
                lines.append(f"情緒: {result['sentiment'].get('level', '?')}")

        elif workflow_name == "post_market":
            if "scan_count" in result:
                lines.append(f"掃描結果: {result['scan_count']} 檔")
            top5 = result.get("top_5", [])
            if top5:
                lines.append("Top 5:")
                for s in top5:
                    lines.append(f"  • {s['code']} ({s['level']}) {s['score']:.1f}分")
            if "data_update" in result:
                du = result["data_update"]
                lines.append(f"資料更新: {du.get('daily_bars', 0)} 筆日K")

        elif workflow_name == "ipo_scan":
            lines.append(f"即將申購: {result.get('upcoming_count', 0)} 檔")

        elif workflow_name == "weekly_report":
            lines.append(f"持倉: {result.get('open_positions', 0)} 筆")
            lines.append(f"本週執行: {result.get('post_market_runs', 0)} 次盤後")

        elif workflow_name == "monthly_rebuild":
            lines.append(f"股票池: {result.get('universe_size', 0)} 檔")

        elif workflow_name == "backup_db" or workflow_name == "retrain_model":
            lines.append(f"狀態: {result.get('status', '?')}")

        return "\n".join(lines)
