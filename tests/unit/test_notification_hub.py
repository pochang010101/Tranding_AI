"""Tests for NotificationHub, adapters, and payload serialization."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.exceptions import NotificationError
from atlas.infrastructure.notification_hub import NotificationHub
from atlas.models.notification import NotificationPayload


# ── Fake / Failing adapters ─────────────────────────


class FakeAdapter:
    """Always-succeeding adapter for testing."""

    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self.sent: list[NotificationPayload] = []

    async def send(self, payload: NotificationPayload) -> bool:
        self.sent.append(payload)
        return True

    async def validate_config(self) -> bool:
        return True

    def channel_name(self) -> str:
        return self._name


class FailingAdapter:
    """Adapter that always raises NotificationError."""

    def __init__(self, name: str = "failing") -> None:
        self._name = name

    async def send(self, payload: NotificationPayload) -> bool:
        raise NotificationError(f"{self._name} boom")

    async def validate_config(self) -> bool:
        return False

    def channel_name(self) -> str:
        return self._name


class UnexpectedErrorAdapter:
    """Adapter that raises a non-NotificationError."""

    async def send(self, payload: NotificationPayload) -> bool:
        raise RuntimeError("unexpected")

    async def validate_config(self) -> bool:
        return False

    def channel_name(self) -> str:
        return "unexpected"


# ── Fixtures ─────────────────────────────────────────


@pytest.fixture
def payload() -> NotificationPayload:
    return NotificationPayload(
        title="Test Title",
        body="Test body content",
        channel="all",
        priority=2,
        category="system",
    )


# ── NotificationHub.send() ──────────────────────────


class TestNotificationHubSend:
    @pytest.mark.asyncio
    async def test_send_no_adapters_returns_false(self, payload: NotificationPayload) -> None:
        hub = NotificationHub()
        result = await hub.send(payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_success_with_one_adapter(self, payload: NotificationPayload) -> None:
        adapter = FakeAdapter()
        hub = NotificationHub(adapters=[adapter])
        result = await hub.send(payload)
        assert result is True
        assert len(adapter.sent) == 1
        assert adapter.sent[0].title == "Test Title"

    @pytest.mark.asyncio
    async def test_send_fallback_on_first_failure(self, payload: NotificationPayload) -> None:
        """First adapter fails, second succeeds — fallback chain works."""
        failing = FailingAdapter("ch1")
        backup = FakeAdapter("ch2")
        hub = NotificationHub(adapters=[failing, backup])
        result = await hub.send(payload)
        assert result is True
        assert len(backup.sent) == 1

    @pytest.mark.asyncio
    async def test_send_all_fail_returns_false(self, payload: NotificationPayload) -> None:
        hub = NotificationHub(adapters=[FailingAdapter("a"), FailingAdapter("b")])
        result = await hub.send(payload)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_handles_unexpected_error(self, payload: NotificationPayload) -> None:
        backup = FakeAdapter("backup")
        hub = NotificationHub(adapters=[UnexpectedErrorAdapter(), backup])
        result = await hub.send(payload)
        assert result is True
        assert len(backup.sent) == 1


# ── NotificationHub.broadcast() ─────────────────────


class TestNotificationHubBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_all_success(self, payload: NotificationPayload) -> None:
        a1, a2 = FakeAdapter("ch1"), FakeAdapter("ch2")
        hub = NotificationHub(adapters=[a1, a2])
        results = await hub.broadcast(payload)
        assert results == {"ch1": True, "ch2": True}
        assert len(a1.sent) == 1
        assert len(a2.sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_partial_failure(self, payload: NotificationPayload) -> None:
        ok = FakeAdapter("ok")
        fail = FailingAdapter("fail")
        hub = NotificationHub(adapters=[ok, fail])
        results = await hub.broadcast(payload)
        assert results["ok"] is True
        assert results["fail"] is False


# ── NotificationHub.validate_all() ──────────────────


class TestNotificationHubValidate:
    @pytest.mark.asyncio
    async def test_validate_all(self) -> None:
        ok = FakeAdapter("ok")
        fail = FailingAdapter("fail")
        hub = NotificationHub(adapters=[ok, fail])
        results = await hub.validate_all()
        assert results["ok"] is True
        assert results["fail"] is False


# ── Rate Limiting ────────────────────────────────────


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_max(self, payload: NotificationPayload) -> None:
        adapter = FakeAdapter()
        hub = NotificationHub(adapters=[adapter], rate_limit_max=3, rate_limit_window=60)
        for _ in range(3):
            assert await hub.send(payload) is True
        # 4th should be rate-limited
        assert await hub.send(payload) is False
        assert len(adapter.sent) == 3


# ── add_adapter ──────────────────────────────────────


class TestAddAdapter:
    def test_add_adapter(self) -> None:
        hub = NotificationHub()
        assert len(hub._adapters) == 0
        hub.add_adapter(FakeAdapter())
        assert len(hub._adapters) == 1


# ── Adapter Construction (no network) ───────────────


class TestAdapterConstruction:
    def test_discord_adapter_init(self) -> None:
        from atlas.infrastructure.notifications.discord import DiscordAdapter

        adapter = DiscordAdapter("https://discord.com/api/webhooks/test/token")
        assert adapter.channel_name() == "discord"
        assert adapter._webhook_url.startswith("https://")

    def test_telegram_adapter_init(self) -> None:
        from atlas.infrastructure.notifications.telegram import TelegramAdapter

        adapter = TelegramAdapter("123:ABC", "99999")
        assert adapter.channel_name() == "telegram"
        assert "123:ABC" in adapter._base_url

    def test_line_adapter_init(self) -> None:
        from atlas.infrastructure.notifications.line import LineAdapter

        adapter = LineAdapter(channel_token="tok", channel_secret="sec", user_id="uid")
        assert adapter.channel_name() == "line"
        assert adapter._token == "tok"
        assert adapter._user_id == "uid"


# ── NotificationPayload ─────────────────────────────


class TestNotificationPayload:
    def test_payload_defaults(self) -> None:
        p = NotificationPayload(title="T", body="B")
        assert p.channel == "discord"
        assert p.priority == 2
        assert p.category == "signal"
        assert isinstance(p.created_at, datetime)
        assert p.mute_check is True
        assert p.attachments == []
        assert p.metadata == {}

    def test_payload_custom(self) -> None:
        p = NotificationPayload(
            title="Alert",
            body="Something happened",
            channel="all",
            priority=4,
            category="system",
            mute_check=False,
        )
        assert p.priority == 4
        assert p.channel == "all"
        assert p.mute_check is False

    def test_payload_metadata_isolation(self) -> None:
        """Each instance should have independent metadata/attachments."""
        p1 = NotificationPayload(title="A", body="B")
        p2 = NotificationPayload(title="C", body="D")
        p1.metadata["key"] = "val"
        p1.attachments.append("file.png")
        assert "key" not in p2.metadata
        assert len(p2.attachments) == 0
