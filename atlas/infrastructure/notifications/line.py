"""LINE Messaging API 推播適配器。"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import httpx

from atlas.exceptions import NotificationError
from atlas.interfaces.infrastructure import INotificationAdapter

if TYPE_CHECKING:
    from atlas.models.notification import NotificationPayload

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0
_PUSH_URL = "https://api.line.me/v2/bot/message/push"
_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


class LineAdapter(INotificationAdapter):
    """LINE Messaging API 推播（push / broadcast）。

    若有設定 LINE_USER_ID，使用 push message（推給特定使用者）。
    否則 fallback 到 broadcast（推給所有好友）。
    """

    def __init__(
        self,
        channel_token: str = "",
        channel_secret: str = "",
        user_id: str = "",
    ) -> None:
        self._token = channel_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        self._secret = channel_secret or os.getenv("LINE_CHANNEL_SECRET", "")
        self._user_id = user_id or os.getenv("LINE_USER_ID", "")

    async def send(self, payload: NotificationPayload) -> bool:
        if not self._token:
            raise NotificationError("LINE channel token not configured")

        text = f"【{payload.title}】\n{payload.body}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        # 優先用 push（指定使用者），無 user_id 時 fallback broadcast
        if self._user_id:
            url = _PUSH_URL
            json_body = {
                "to": self._user_id,
                "messages": [{"type": "text", "text": text[:5000]}],
            }
        else:
            url = _BROADCAST_URL
            json_body = {
                "messages": [{"type": "text", "text": text[:5000]}],
            }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(url, json=json_body, headers=headers)
                resp.raise_for_status()
            mode = "push" if self._user_id else "broadcast"
            logger.info("LINE %s sent: %s", mode, payload.title)
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


def send_line_message_sync(text: str) -> bool:
    """同步版 LINE 推播（供 Streamlit 頁面直接呼叫）。"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.getenv("LINE_USER_ID", "")

    if not token:
        logger.warning("LINE token not configured")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if user_id:
        url = _PUSH_URL
        json_body = {"to": user_id, "messages": [{"type": "text", "text": text[:5000]}]}
    else:
        url = _BROADCAST_URL
        json_body = {"messages": [{"type": "text", "text": text[:5000]}]}

    try:
        resp = httpx.post(url, json=json_body, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        logger.info("LINE sync message sent (%d chars)", len(text))
        return True
    except httpx.HTTPError as exc:
        logger.error("LINE sync send failed: %s", exc)
        return False
