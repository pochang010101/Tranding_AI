"""Email SMTP 推播適配器。"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from atlas.exceptions import NotificationError
from atlas.interfaces.infrastructure import INotificationAdapter

if TYPE_CHECKING:
    from atlas.models.notification import NotificationPayload

logger = logging.getLogger(__name__)


class EmailAdapter(INotificationAdapter):
    """Email SMTP 推播（smtplib + asyncio.to_thread）。"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        user: str,
        password: str,
        from_addr: str | None = None,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._user = user
        self._password = password
        self._from_addr = from_addr or user

    async def send(self, payload: NotificationPayload) -> bool:
        if not self._smtp_host or not self._user:
            raise NotificationError("Email SMTP not configured")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Atlas] {payload.title}"
        msg["From"] = self._from_addr
        msg["To"] = self._user  # 預設寄給自己

        msg.attach(MIMEText(payload.body, "plain", "utf-8"))
        html = f"<h3>{payload.title}</h3><pre>{payload.body}</pre>"
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            await asyncio.to_thread(self._send_sync, msg)
            logger.info("Email notification sent: %s", payload.title)
            return True
        except Exception as exc:
            raise NotificationError(f"Email send failed: {exc}") from exc

    def _send_sync(self, msg: MIMEMultipart) -> None:
        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as server:
            server.ehlo()
            if self._smtp_port != 25:
                server.starttls()
                server.ehlo()
            if self._user and self._password:
                server.login(self._user, self._password)
            server.send_message(msg)

    async def validate_config(self) -> bool:
        if not self._smtp_host:
            return False
        try:
            await asyncio.to_thread(self._validate_sync)
            return True
        except Exception:
            return False

    def _validate_sync(self) -> None:
        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=5) as server:
            server.ehlo()

    def channel_name(self) -> str:
        return "email"
