from src.utils.logger import logger
from src.workflow.models import ResolutionPayload


def handle_resolution(payload: ResolutionPayload) -> None:
    """Phase 6: Handle Jira webhook when a ticket transitions to 'Done'.

    Feeds the resolution back into the knowledge base for future retrieval and
    triage improvement. Notification fan-out is handled by the webhook route so
    the same helper can be reused for ticket creation and resolution events.
    """
    logger.info(
        "ticket_resolved",
        request_id=payload.request_id or "unknown",
        ticket_id=payload.ticket_id,
        resolved_by=payload.resolved_by,
    )
    _save_to_knowledge_base(payload)



def _save_to_knowledge_base(payload: ResolutionPayload) -> None:
    """Persist resolution metadata to Qdrant for the auto-improvement loop.

    Stub: logs intent until Qdrant integration is wired.
    """
    logger.info(
        "kb_upsert",
        request_id=payload.request_id or "unknown",
        ticket_id=payload.ticket_id,
        integration="qdrant",
    )

