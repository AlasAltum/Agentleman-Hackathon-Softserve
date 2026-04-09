import uuid
from typing import Optional

from src.utils.logger import logger
from src.workflow.models import PreprocessedIncident, TicketInfo, TriageResult


def _create_or_update_ticket(
    triage: TriageResult,
    reporter_email: str,
    preprocessed: Optional[PreprocessedIncident] = None,
) -> TicketInfo:
    """Always create a new Jira ticket regardless of incident type."""
    return _create_new_ticket(triage, reporter_email, preprocessed)


def _build_ticket_title(triage: TriageResult) -> str:
    """Derive a concise ticket title from the triage result."""
    incident_type = triage.classification.incident_type.value.replace("_", " ").title()
    severity = triage.severity.value.upper()
    # Use the first sentence of technical_summary, capped at 80 chars
    first_sentence = triage.technical_summary.split(".")[0].strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77] + "..."
    return f"[{severity}] {incident_type}: {first_sentence}"


def _build_ticket_description(triage: TriageResult, preprocessed: Optional[PreprocessedIncident] = None) -> str:
    """Build a structured Jira ticket description from the triage result."""
    lines = [
        "h2. Incident Summary",
        triage.technical_summary,
        "",
        f"*Severity:* {triage.severity.value.upper()}",
        f"*Incident Type:* {triage.classification.incident_type.value.replace('_', ' ').title()}",
        "",
        "h2. Business Impact",
        triage.business_impact_summary,
    ]

    if triage.tool_results:
        lines += ["", "h2. Tool Findings"]
        for result in triage.tool_results:
            hint = f" (severity hint: {result.severity_hint.value})" if result.severity_hint else ""
            lines.append(f"*{result.tool_name}*{hint}: {result.findings}")

    if triage.classification.historical_rca:
        lines += ["", "h2. Historical RCA", triage.classification.historical_rca]

    if preprocessed:
        lines += ["", "h2. Original Report", preprocessed.original.text_desc]

    return "\n".join(lines)


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
    title = _build_ticket_title(triage)
    description = _build_ticket_description(triage, preprocessed)
    logger.info("ticket_created", ticket_id=ticket_id, severity=triage.severity, title=title)

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
        title=title,
        description=description,
    )


def _notify_team(ticket: TicketInfo, triage: TriageResult) -> None:
    """Notify technical team via Email and other notification channels."""
    logger.info(
        "team_notification",
        ticket_id=ticket.ticket_id,
        severity=triage.severity,
    )
    # TODO: [Alonso] Aquí voy a agregar la notificación en ZAVU
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
