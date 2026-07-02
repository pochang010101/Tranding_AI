"""Telegram Bot API 推播適配器。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from atlas.exceptions import NotificationError
from atlas.interfaces.infrastructure import INotificationAdapter

if TYPE_CHECKING:
    from atlas.models.notification import NotificationPayload

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


class TelegramAdapter(INotificationAdapter):
    """Telegram Bot sendMessage 推播。"""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def _base_url(self) -> str:
        return f"https://api.telegram.org/bot{self._bot_token}"

    async def send(self, payload: NotificationPayload) -> bool:
        if not self._bot_token or not self._chat_id:
            raise NotificationError("Telegram bot_token or chat_id not configured")

        text = f"*{payload.title}*\n\n{payload.body}"
        json_body = {
            "chat_id": self._chat_id,
            "text": text[:4096],
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(f"{self._base_url}/sendMessage", json=json_body)
                resp.raise_for_status()
                data = resp.json()
            if not data.get("ok"):
                raise NotificationError(f"Telegram API error: {data.get('description')}")
            logger.info("Telegram notification sent: %s", payload.title)
            return True
        except httpx.HTTPError as exc:
            raise NotificationError(f"Telegram send failed: {exc}") from exc

    async def validate_config(self) -> bool:
        if not self._bot_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/getMe")
                return resp.status_code == 200 and resp.json().get("ok", False)
        except httpx.HTTPError:
            return False

    def channel_name(self) -> str:
        return "telegram"
