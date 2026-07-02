"""整合測試 atlas.application.workflow_engine — 工作流引擎。"""

from __future__ import annotations

import pytest

from atlas.enums import MarketType
from atlas.application.workflow_engine import WorkflowEngine


@pytest.fixture()
def wf():
    return WorkflowEngine(market=MarketType.TW)


class TestRunWorkflow:
    @pytest.mark.asyncio
    async def test_pre_market_no_services(self, wf):
        result = await wf.run("pre_market")
        assert "steps" in result
        assert isinstance(result["steps"], list)

    @pytest.mark.asyncio
    async def test_intraday_no_radar(self, wf):
        result = await wf.run("intraday")
        assert result["status"] == "no_radar_configured"

    @pytest.mark.asyncio
    async def test_post_market_no_services(self, wf):
        result = await wf.run("post_market")
        assert "steps" in result

    @pytest.mark.asyncio
    async def test_ipo_scan(self, wf):
        result = await wf.run("ipo_scan")
        assert result["status"] == "placeholder"

    @pytest.mark.asyncio
    async def test_weekly_report(self, wf):
        result = await wf.run("weekly_report")
        assert result["status"] == "placeholder"

    @pytest.mark.asyncio
    async def test_monthly_rebuild_no_universe(self, wf):
        result = await wf.run("monthly_rebuild")
        assert result["status"] == "no_universe_manager"

    @pytest.mark.asyncio
    async def test_unknown_workflow(self, wf):
        with pytest.raises(ValueError, match="Unknown workflow"):
            await wf.run("nonexistent")


class TestStatus:
    @pytest.mark.asyncio
    async def test_never_run(self, wf):
        status = await wf.get_status("pre_market")
        assert status["status"] == "never_run"

    @pytest.mark.asyncio
    async def test_after_run(self, wf):
        await wf.run("pre_market")
        status = await wf.get_status("pre_market")
        assert status["status"] == "completed"


class TestExecutionHistory:
    @pytest.mark.asyncio
    async def test_history(self, wf):
        await wf.run("pre_market")
        await wf.run("intraday")
        history = await wf.get_execution_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_filter_by_name(self, wf):
        await wf.run("pre_market")
        await wf.run("intraday")
        history = await wf.get_execution_history(workflow_name="pre_market")
        assert len(history) == 1
        assert history[0]["workflow"] == "pre_market"
