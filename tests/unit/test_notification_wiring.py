"""Test notification wiring in WorkflowEngine."""

from __future__ import annotations

import pytest

from atlas.application.workflow_engine import WorkflowEngine
from atlas.infrastructure.notification_hub import NotificationHub
from atlas.models.notification import NotificationPayload


class FakeAdapter:
    """Fake notification adapter for testing."""

    def __init__(self) -> None:
        self.sent: list[NotificationPayload] = []

    async def send(self, payload: NotificationPayload) -> bool:
        self.sent.append(payload)
        return True

    async def validate_config(self) -> bool:
        return True

    def channel_name(self) -> str:
        return "fake"


@pytest.fixture
def fake_adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture
def engine_with_notification(fake_adapter: FakeAdapter) -> WorkflowEngine:
    hub = NotificationHub(adapters=[fake_adapter])
    return WorkflowEngine(notification=hub)


class TestNotificationWiring:
    @pytest.mark.asyncio
    async def test_pre_market_sends_notification(
        self, engine_with_notification: WorkflowEngine, fake_adapter: FakeAdapter
    ) -> None:
        await engine_with_notification.run("pre_market")
        assert len(fake_adapter.sent) == 1
        assert "盤前" in fake_adapter.sent[0].title

    @pytest.mark.asyncio
    async def test_post_market_sends_notification(
        self, engine_with_notification: WorkflowEngine, fake_adapter: FakeAdapter
    ) -> None:
        await engine_with_notification.run("post_market")
        assert len(fake_adapter.sent) == 1
        assert "盤後" in fake_adapter.sent[0].title

    @pytest.mark.asyncio
    async def test_no_notification_without_hub(self) -> None:
        engine = WorkflowEngine()
        # Should not raise even without notification hub
        result = await engine.run("pre_market")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_notification_body_has_elapsed(
        self, engine_with_notification: WorkflowEngine, fake_adapter: FakeAdapter
    ) -> None:
        await engine_with_notification.run("pre_market")
        assert "耗時" in fake_adapter.sent[0].body

    @pytest.mark.asyncio
    async def test_format_post_market_body(self) -> None:
        body = WorkflowEngine._format_workflow_body(
            "post_market",
            {"scan_count": 42, "top_5": [{"code": "2330", "level": "Lv5", "score": 85.0}]},
            1.5,
        )
        assert "42" in body
        assert "2330" in body
        assert "1.5s" in body
