"""Discord Webhook 推播適配器。"""

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
_MAX_CONTENT_LEN = 2000


class DiscordAdapter(INotificationAdapter):
    """Discord Webhook 推播（不依賴 discord.py SDK）。"""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(self, payload: NotificationPayload) -> bool:
        if not self._webhook_url:
            raise NotificationError("Discord webhook URL not configured")

        body = payload.body
        if len(body) > _MAX_CONTENT_LEN:
            body = body[: _MAX_CONTENT_LEN - 3] + "..."

        json_body = {
            "embeds": [
                {
                    "title": payload.title,
                    "description": body,
                    "color": self._priority_color(payload.priority),
                    "footer": {"text": f"Atlas | {payload.category}"},
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(self._webhook_url, json=json_body)
                resp.raise_for_status()
            logger.info("Discord notification sent: %s", payload.title)
            return True
        except httpx.HTTPError as exc:
            raise NotificationError(f"Discord send failed: {exc}") from exc

    async def validate_config(self) -> bool:
        if not self._webhook_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(self._webhook_url)
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def channel_name(self) -> str:
        return "discord"

    @staticmethod
    def _priority_color(priority: int) -> int:
        colors = {1: 0x808080, 2: 0x3498DB, 3: 0xF39C12, 4: 0xE74C3C}
        return colors.get(priority, 0x3498DB)
