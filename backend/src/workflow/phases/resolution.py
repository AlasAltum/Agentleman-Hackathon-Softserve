from src.utils.logger import logger
from src.workflow.models import ResolutionPayload


async def handle_resolution(payload: ResolutionPayload) -> None:
    """Phase 6: Handle Jira webhook when a ticket transitions to 'Done'.

    Notifies the original reporter and feeds the resolution back into the
    knowledge base for future retrieval and triage improvement.
    """
    logger.info(
        "ticket_resolved",
        ticket_id=payload.ticket_id,
        resolved_by=payload.resolved_by,
    )
    _notify_reporter(payload)
    await _save_to_knowledge_base(payload)


def _notify_reporter(payload: ResolutionPayload) -> None:
    """Send resolution email to the original incident reporter.

    Stub: logs intent until email integration is wired.
    """
    logger.info(
        "resolution_email",
        ticket_id=payload.ticket_id,
        notes=payload.resolution_notes,
    )


async def _save_to_knowledge_base(payload: ResolutionPayload) -> None:
    """Persist resolution metadata to Qdrant for the auto-improvement loop.

    Stub: logs intent until Qdrant integration is wired.
    """
    logger.info(
        "kb_upsert",
        ticket_id=payload.ticket_id,
        integration="qdrant",
    )
