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
    logger.info("ticket_created", ticket_id=ticket_id, severity=triage.severity)

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "ticket_from_flagged_input",
            ticket_id=ticket_id,
            security_flag=preprocessed.security_flag,
        )
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
    logger.info("ticket_updated", ticket_id=existing_id, reason="alert_storm_deduplication")

    if preprocessed and preprocessed.security_flag:
        logger.warning(
            "ticket_updated_from_flagged_input",
            ticket_id=existing_id,
            security_flag=preprocessed.security_flag,
        )
    return TicketInfo(
        ticket_id=existing_id,
        ticket_url=f"https://jira.example.com/browse/{existing_id}",
        action="updated",
        reporter_email=reporter_email,
    )


def _notify_team(ticket: TicketInfo, triage: TriageResult) -> None:
    """Notify technical team via Slack and Email."""
    logger.info(
        "team_notification",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )
    _send_slack_notification(ticket, triage)
    _send_team_email(ticket, triage)


def _send_slack_notification(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send Slack message to SRE channel until Slack integration is wired."""
    logger.info(
        "slack_notification",
        channel="#sre-alerts",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )


def _send_team_email(ticket: TicketInfo, triage: TriageResult) -> None:
    """Stub: send email to SRE team distribution list until email integration is wired."""
    logger.info(
        "email_notification",
        recipient="sre-team@company.com",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )