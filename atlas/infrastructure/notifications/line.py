"""LINE Messaging API 推播適配器。"""

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
_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


class LineAdapter(INotificationAdapter):
    """LINE Messaging API 推播（broadcast）。"""

    def __init__(self, channel_token: str, channel_secret: str) -> None:
        self._token = channel_token
        self._secret = channel_secret

    async def send(self, payload: NotificationPayload) -> bool:
        if not self._token:
            raise NotificationError("LINE channel token not configured")

        text = f"【{payload.title}】\n{payload.body}"
        json_body = {
            "messages": [{"type": "text", "text": text[:5000]}]
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(_BROADCAST_URL, json=json_body, headers=headers)
                resp.raise_for_status()
            logger.info("LINE notification sent: %s", payload.title)
            return True
        except httpx.HTTPError as exc:
            raise NotificationError(f"LINE send failed: {exc}") from exc

    async def validate_config(self) -> bool:
        if not self._token:
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    "https://api.line.me/v2/bot/info",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def channel_name(self) -> str:
        return "line"
