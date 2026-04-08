from dataclasses import dataclass
from typing import Any

from src.integrations.base import MockIntegrationProvider
from src.integrations.models import IntegrationConfig, IntegrationResult, IntegrationType


@dataclass
class EmailMessage:
    to: str
    subject: str
    body: str
    cc: list[str] | None = None
    bcc: list[str] | None = None
    attachments: list[bytes] | None = None


class EmailProvider(MockIntegrationProvider):
    type = IntegrationType.EMAIL

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        **kwargs: Any,
    ) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["to"] = to
            result.data["subject"] = subject
            result.data["sent_at"] = "2025-01-01T00:00:00Z"
        return result


@dataclass
class ChatMessage:
    channel: str
    text: str
    attachments: list[dict[str, Any]] | None = None


class CommunicatorProvider(MockIntegrationProvider):
    type = IntegrationType.COMMUNICATOR

    async def send_message(
        self,
        channel: str,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["channel"] = channel
            result.data["message_id"] = f"msg-{hash(text) % 10000:04d}"
        return result

    async def send_alert(
        self,
        channel: str,
        title: str,
        severity: str,
        details: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["channel"] = channel
            result.data["alert_sent"] = True
        return result