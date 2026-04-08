import uuid
from typing import Optional

from src.utils.logger import logger
from src.workflow.models import IncidentType, PreprocessedIncident, TicketInfo, TriageResult


def _create_or_update_ticket(
    triage: TriageResult,
    reporter_email: str,
    preprocessed: Optional[PreprocessedIncident] = None,
) -> TicketInfo:
    """Create a new ticket or update an existing one for alert storms."""
    if triage.classification.incident_type == IncidentType.ALERT_STORM:
        return _update_existing_ticket(triage, reporter_email, preprocessed)
    return _create_new_ticket(triage, reporter_email, preprocessed)


def _create_new_ticket(
    triage: TriageResult,
    reporter_email: str,
    preprocessed: Optional[PreprocessedIncident] = None,
) -> TicketInfo:
    """Create a new Jira ticket with the triage summary.

    Stub: logs intent and returns mock ticket until Jira integration is wired.
    """
    ticket_id = f"SRE-{str(uuid.uuid4())[:8].upper()}"
    ticket_url = f"https://jira.example.com/browse/{ticket_id}"
    logger.info("[ticketing] Creating new ticket: %s severity=%s", ticket_id, triage.severity)

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "[ticketing] ⚠ Ticket %s created from flagged input (security_flag=%s) — review recommended",
            ticket_id,
            preprocessed.security_flag,
        )
    # TODO: call Jira API — create issue with technical_summary, severity, and security_flag label
    return TicketInfo(
        ticket_id=ticket_id,
        ticket_url=ticket_url,
        action="created",
        reporter_email=reporter_email,
    )


def _update_existing_ticket(
    triage: TriageResult,
    reporter_email: str,
    preprocessed: Optional[PreprocessedIncident] = None,
) -> TicketInfo:
    """Add a comment to the existing ticket for an ongoing alert storm.

    Stub: logs intent and returns mock update until Jira integration is wired.
    """
    existing_id = (
        triage.classification.top_candidates[0].incident_id
        if triage.classification.top_candidates
        else "SRE-UNKNOWN"
    )
    logger.info("[ticketing] Updating ticket %s (alert storm deduplication)", existing_id)

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "[ticketing] ⚠ Ticket %s updated from flagged input (security_flag=%s) — review recommended",
            existing_id,
            preprocessed.security_flag,
        )
    # TODO: call Jira API — add comment and increase urgency
    return TicketInfo(
        ticket_id=existing_id,
        ticket_url=f"https://jira.example.com/browse/{existing_id}",
        action="updated",
        reporter_email=reporter_email,
    )


def _notify_team(ticket: TicketInfo, triage: TriageResult) -> None:
    """Notify technical team via Slack and Email."""
    logger.info(
        "[ticketing] Notifying team — ticket=%s severity=%s",
        ticket.ticket_id,
        triage.severity,
    )
    _send_slack_notification(ticket, triage)
    _send_team_email(ticket, triage)


def _send_slack_notification(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send Slack message to SRE channel until Slack integration is wired."""
    logger.info(
        "[notify/slack] Would post to #sre-alerts: %s [%s] — %s",
        ticket.ticket_id,
        triage.severity,
        ticket.ticket_url,
    )


def _send_team_email(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send email to SRE team distribution list until email integration is wired."""
    logger.info(
        "[notify/email] Would email sre-team@company.com about ticket %s [%s]",
        ticket.ticket_id,
        triage.severity,
    )
