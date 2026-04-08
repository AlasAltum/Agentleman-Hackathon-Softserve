from dataclasses import dataclass
from typing import Any

from src.integrations.base import IntegrationProvider, MockIntegrationProvider
from src.integrations.models import IntegrationConfig, IntegrationResult, IntegrationType


@dataclass
class Ticket:
    ticket_id: str
    ticket_url: str
    status: str
    assignee: str | None = None
    priority: str | None = None
    labels: list[str] | None = None
    custom_fields: dict[str, Any] | None = None


@dataclass
class TicketComment:
    author: str
    body: str
    created_at: str | None = None


class TicketingProvider(MockIntegrationProvider):
    type = IntegrationType.TICKETING

    async def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        labels: list[str] | None = None,
        **kwargs: Any,
    ) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["ticket_id"] = f"{self.name.upper()}-{hash(title) % 10000:04d}"
            result.data["ticket_url"] = (
                f"https://{self.name.lower()}.example.com/tickets/{result.data['ticket_id']}"
            )
        return result

    async def update_ticket(
        self,
        ticket_id: str,
        comment: str,
        status: str | None = None,
        **kwargs: Any,
    ) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["ticket_id"] = ticket_id
            result.data["updated"] = True
        return result

    async def get_ticket(self, ticket_id: str) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["ticket_id"] = ticket_id
        return result

    async def add_comment(self, ticket_id: str, comment: str) -> IntegrationResult:
        result = await self.execute()
        if result.success:
            result.data["ticket_id"] = ticket_id
            result.data["comment_added"] = True
        return result