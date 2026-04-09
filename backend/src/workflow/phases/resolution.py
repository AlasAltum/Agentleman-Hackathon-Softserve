from src.utils.logger import logger
from src.workflow.models import ResolutionPayload


def handle_resolution(payload: ResolutionPayload) -> None:
    """Phase 6: Handle Jira webhook when a ticket transitions to 'Done'.

    Notifies the original reporter and feeds the resolution back into the
    knowledge base for future retrieval and triage improvement.
    """
    logger.info(
        "[resolution] Ticket resolved: %s by %s",
        payload.ticket_id,
        payload.resolved_by,
    )
    _trigger_resolution_notifications(payload)
    _save_to_knowledge_base(payload)


def _trigger_resolution_notifications(payload: ResolutionPayload) -> None:
    """Trigger resolution notifications for the reporter and support team.

    Stub: logs intent until the notification integration is wired.
    """
    # TODO(notification-service): call the notification service here when the Jira resolution webhook should fan out notifications.  # NOSONAR
    logger.info(
        "[resolution/notify] Would trigger notifications for resolved ticket %s — notes: %s",
        payload.ticket_id,
        payload.resolution_notes,
    )


def _save_to_knowledge_base(payload: ResolutionPayload) -> None:
    """Persist resolution metadata to Qdrant for the auto-improvement loop.

    Stub: logs intent until Qdrant integration is wired.
    """
    logger.info(
        "[resolution/kb] Would upsert resolution into vector DB: ticket=%s",
        payload.ticket_id,
    )
