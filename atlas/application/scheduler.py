"""排程服務 — 定時觸發工作流，基於 APScheduler。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from atlas.enums import MarketType
from atlas.interfaces.application import ISchedulerService

if TYPE_CHECKING:
    from atlas.application.workflow_engine import WorkflowEngine
    from atlas.domain.trading_calendar import TradingCalendar

logger = logging.getLogger(__name__)


class _ScheduleEntry:
    __slots__ = ("name", "cron_expr", "workflow_name", "enabled", "last_run", "next_run")

    def __init__(self, name: str, cron_expr: str, workflow_name: str, enabled: bool = True):
        self.name = name
        self.cron_expr = cron_expr
        self.workflow_name = workflow_name
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None


class Scheduler(ISchedulerService):
    """排程服務。

    管理 cron 排程，觸發 WorkflowEngine 的對應工作流。
    依賴 TradingCalendar 判斷交易日。
    """

    def __init__(
        self,
        workflow_engine: WorkflowEngine | None = None,
        trading_calendar: TradingCalendar | None = None,
    ) -> None:
        self._workflow = workflow_engine
        self._calendar = trading_calendar
        self._schedules: dict[str, _ScheduleEntry] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._execution_log: list[dict[str, Any]] = []

    async def start(self) -> None:
        """啟動排程服務。若無排程已註冊，自動載入預設排程。"""
        if self._running:
            return
        if not self._schedules:
            await self._load_default_schedules()
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started with %d schedules", len(self._schedules))

    async def stop(self) -> None:
        """停止排程服務。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Scheduler stopped")

    async def add_schedule(
        self, name: str, cron_expr: str, workflow_name: str, enabled: bool = True
    ) -> None:
        self._schedules[name] = _ScheduleEntry(name, cron_expr, workflow_name, enabled)
        logger.info("Schedule added: %s → %s (%s)", name, workflow_name, cron_expr)

    async def remove_schedule(self, name: str) -> None:
        self._schedules.pop(name, None)

    async def enable_schedule(self, name: str) -> None:
        if name in self._schedules:
            self._schedules[name].enabled = True

    async def disable_schedule(self, name: str) -> None:
        if name in self._schedules:
            self._schedules[name].enabled = False

    async def list_schedules(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "cron_expr": s.cron_expr,
                "workflow_name": s.workflow_name,
                "enabled": s.enabled,
                "last_run": s.last_run.isoformat() if s.last_run else None,
            }
            for s in self._schedules.values()
        ]

    async def trigger_now(self, name: str) -> dict[str, Any]:
        """手動立即觸發指定排程。"""
        entry = self._schedules.get(name)
        if not entry:
            return {"error": f"Schedule '{name}' not found"}

        if not self._workflow:
            return {"error": "No workflow engine configured"}

        try:
            result = await self._workflow.run(entry.workflow_name)
            entry.last_run = datetime.utcnow()
            self._execution_log.append({
                "schedule": name,
                "workflow": entry.workflow_name,
                "triggered_at": entry.last_run.isoformat(),
                "status": "completed",
                "manual": True,
            })
            return {"status": "completed", "result": result}
        except Exception as exc:
            self._execution_log.append({
                "schedule": name,
                "workflow": entry.workflow_name,
                "triggered_at": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(exc),
                "manual": True,
            })
            return {"status": "failed", "error": str(exc)}

    async def is_trading_day(
        self, market: MarketType, check_date: date | None = None
    ) -> bool:
        d = check_date or date.today()
        if self._calendar:
            return self._calendar.is_trading_day(d, market)
        # 預設：週一到週五為交易日
        return d.weekday() < 5

    async def _load_default_schedules(self) -> None:
        """載入預設台股交易日排程（UTC+8 時間）。"""
        defaults = [
            # name, cron (M H * * DOW), workflow
            ("tw_pre_market", "0 8 * * 1-5", "pre_market"),
            ("tw_intraday", "0 9 * * 1-5", "intraday"),
            ("tw_post_market", "45 13 * * 1-5", "post_market"),
            ("tw_monthly_rebuild", "0 20 * * 0", "monthly_rebuild"),
            # 維運排程（非交易日亦執行）
            ("daily_backup", "0 14 * * *", "backup_db"),
            ("weekly_retrain", "0 21 * * 0", "retrain_model"),
        ]
        for name, cron, workflow in defaults:
            await self.add_schedule(name, cron, workflow)
        logger.info("Loaded %d default schedules", len(defaults))

    # ── 內部排程迴圈 ─────────────────────────────

    async def _scheduler_loop(self) -> None:
        """排程迴圈：每分鐘檢查一次 cron 匹配，非交易日跳過。"""
        while self._running:
            now = datetime.utcnow()
            is_trade_day = await self.is_trading_day(MarketType.TW)
            for entry in self._schedules.values():
                if not entry.enabled:
                    continue
                # monthly_rebuild / backup_db / retrain_model 不受交易日限制
                _ops_workflows = {"monthly_rebuild", "backup_db", "retrain_model"}
                if not is_trade_day and entry.workflow_name not in _ops_workflows:
                    continue
                if self._should_run(entry, now):
                    asyncio.create_task(self._execute_schedule(entry))
            await asyncio.sleep(60)

    async def _execute_schedule(self, entry: _ScheduleEntry) -> None:
        """執行單一排程。"""
        if not self._workflow:
            return
        try:
            await self._workflow.run(entry.workflow_name)
            entry.last_run = datetime.utcnow()
            self._execution_log.append({
                "schedule": entry.name,
                "workflow": entry.workflow_name,
                "triggered_at": entry.last_run.isoformat(),
                "status": "completed",
            })
        except Exception as exc:
            logger.error("Schedule %s failed: %s", entry.name, exc)
            self._execution_log.append({
                "schedule": entry.name,
                "workflow": entry.workflow_name,
                "triggered_at": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(exc),
            })

    @staticmethod
    def _should_run(entry: _ScheduleEntry, now: datetime) -> bool:
        """簡化 cron 匹配：解析 'M H * * DOW' 格式。"""
        parts = entry.cron_expr.split()
        if len(parts) < 5:
            return False
        try:
            minute, hour, _, _, dow = parts
            if minute != "*" and now.minute != int(minute):
                return False
            if hour != "*" and now.hour != int(hour):
                return False
            if dow != "*":
                dow_range = dow.replace("1-5", "0,1,2,3,4").replace("0-6", "0,1,2,3,4,5,6")
                valid_days = [int(d) for d in dow_range.split(",")]
                if now.weekday() not in valid_days:
                    return False
            # 避免同一分鐘重複觸發
            return not (entry.last_run and (now - entry.last_run).total_seconds() < 120)
        except (ValueError, IndexError):
            return False
