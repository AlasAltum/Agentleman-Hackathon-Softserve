from __future__ import annotations

from dataclasses import dataclass, field

from src.workflow.models import ResolutionPayload, TicketInfo, TriageResult

from .client import NylasClient, NylasClientError, NylasConfig, NylasConfigurationError
from .observability import log_event, new_request_id, record_counter, traced_operation


@dataclass(frozen=True)
class DispatchResult:
    channel: str
    recipient: str
    status: str
    message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NotificationFanoutResult:
    request_id: str
    dispatched: list[DispatchResult] = field(default_factory=list)
    failed: list[DispatchResult] = field(default_factory=list)


def load_config_from_env() -> NylasConfig:
    return NylasConfig.from_env()


def notify_team(
    ticket: TicketInfo,
    triage: TriageResult,
    request_id: str | None = None,
) -> NotificationFanoutResult:
    active_request_id = request_id or new_request_id()
    config = load_config_from_env()
    if not config.team_email_recipients:
        raise NylasConfigurationError("Configure NYLAS_TEAM_EMAIL_RECIPIENTS")

    client = NylasClient(config)
    with traced_operation(
        "notifications.notify_team",
        active_request_id,
        provider="nylas",
        ticket_id=ticket.ticket_id,
        severity=triage.severity.value,
        action=ticket.action,
    ):
        log_event(
            "info",
            "notifications.team.started",
            active_request_id,
            provider="nylas",
            ticket_id=ticket.ticket_id,
            team_email_count=len(config.team_email_recipients),
        )

        dispatched: list[DispatchResult] = []
        failed: list[DispatchResult] = []
        for recipient in config.team_email_recipients:
            result = _dispatch_email(
                client,
                recipient=recipient,
                subject=_team_email_subject(ticket, triage, active_request_id),
                body=_team_email_body(ticket, triage, config, active_request_id),
                request_id=active_request_id,
            )
            _append_result(dispatched, failed, result)

        summary = NotificationFanoutResult(
            request_id=active_request_id,
            dispatched=dispatched,
            failed=failed,
        )
        log_event(
            "info",
            "notifications.team.completed",
            active_request_id,
            provider="nylas",
            dispatched=len(dispatched),
            failed=len(failed),
        )
        return summary


def notify_reporter_ticket_created(
    ticket: TicketInfo,
    triage: TriageResult,
    request_id: str | None = None,
) -> NotificationFanoutResult:
    active_request_id = request_id or new_request_id()
    reporter_email = ticket.reporter_email.strip()
    if not reporter_email:
        raise NylasConfigurationError("Missing reporter email on ticket")

    config = load_config_from_env()
    client = NylasClient(config)

    with traced_operation(
        "notifications.notify_reporter_ticket_created",
        active_request_id,
        provider="nylas",
        ticket_id=ticket.ticket_id,
        reporter_email=reporter_email,
        severity=triage.severity.value,
    ):
        log_event(
            "info",
            "notifications.reporter_ticket.started",
            active_request_id,
            provider="nylas",
            ticket_id=ticket.ticket_id,
            reporter_email=reporter_email,
        )

        dispatched: list[DispatchResult] = []
        failed: list[DispatchResult] = []
        email_result = _dispatch_email(
            client,
            recipient=reporter_email,
            subject=_reporter_ticket_created_subject(ticket, triage, active_request_id),
            body=_reporter_ticket_created_email_body(ticket, triage, config, active_request_id),
            request_id=active_request_id,
        )
        _append_result(dispatched, failed, email_result)

        summary = NotificationFanoutResult(
            request_id=active_request_id,
            dispatched=dispatched,
            failed=failed,
        )
        log_event(
            "info",
            "notifications.reporter_ticket.completed",
            active_request_id,
            provider="nylas",
            ticket_id=ticket.ticket_id,
            reporter_email=reporter_email,
            dispatched=len(dispatched),
            failed=len(failed),
        )
        return summary


def notify_reporter_resolution(
    reporter_email: str,
    payload: ResolutionPayload,
    request_id: str | None = None,
) -> NotificationFanoutResult:
    active_request_id = request_id or new_request_id()
    recipient = reporter_email.strip()
    if not recipient:
        raise NylasConfigurationError("Missing reporter email for resolution notification")

    config = load_config_from_env()
    client = NylasClient(config)

    with traced_operation(
        "notifications.notify_reporter_resolution",
        active_request_id,
        provider="nylas",
        ticket_id=payload.ticket_id,
        reporter_email=recipient,
    ):
        log_event(
            "info",
            "notifications.reporter_resolution.started",
            active_request_id,
            provider="nylas",
            ticket_id=payload.ticket_id,
            reporter_email=recipient,
        )

        dispatched: list[DispatchResult] = []
        failed: list[DispatchResult] = []
        email_result = _dispatch_email(
            client,
            recipient=recipient,
            subject=_reporter_resolution_subject(payload, active_request_id),
            body=_reporter_resolution_email_body(payload, config, active_request_id),
            request_id=active_request_id,
        )
        _append_result(dispatched, failed, email_result)

        summary = NotificationFanoutResult(
            request_id=active_request_id,
            dispatched=dispatched,
            failed=failed,
        )
        log_event(
            "info",
            "notifications.reporter_resolution.completed",
            active_request_id,
            provider="nylas",
            ticket_id=payload.ticket_id,
            reporter_email=recipient,
            dispatched=len(dispatched),
            failed=len(failed),
        )
        return summary


def _dispatch_email(
    client: NylasClient,
    *,
    recipient: str,
    subject: str,
    body: str,
    request_id: str,
) -> DispatchResult:
    try:
        response = client.send_email(
            to=recipient,
            subject=subject,
            body=body,
            reply_to=client.config.email_reply_to or client.config.sender_email,
            request_id=request_id,
        )
        message_id = _extract_message_id(response)
        status = _extract_status(response)
        result = DispatchResult(
            channel="email",
            recipient=recipient,
            status=status,
            message_id=message_id,
        )
        record_counter("notifications_sent_total", attributes={"provider": "nylas", "channel": "email"})
        log_event(
            "info",
            "notifications.email.sent",
            request_id,
            provider="nylas",
            recipient=recipient,
            status=status,
            message_id=message_id,
        )
        return result
    except NylasClientError as exc:
        result = DispatchResult(
            channel="email",
            recipient=recipient,
            status="failed",
            error=str(exc),
        )
        record_counter("notifications_failed_total", attributes={"provider": "nylas", "channel": "email"})
        log_event(
            "error",
            "notifications.email.failed",
            request_id,
            provider="nylas",
            recipient=recipient,
            error=str(exc),
        )
        return result


def _append_result(
    dispatched: list[DispatchResult],
    failed: list[DispatchResult],
    result: DispatchResult,
) -> None:
    if result.error:
        failed.append(result)
        return
    dispatched.append(result)


def _team_email_subject(ticket: TicketInfo, triage: TriageResult, request_id: str) -> str:
    reference = _request_reference(ticket.request_id, request_id, ticket.ticket_id)
    return f"[{triage.severity.value.upper()}] Incident report - {reference}"


def _team_email_body(
    ticket: TicketInfo,
    triage: TriageResult,
    config: NylasConfig,
    request_id: str,
) -> str:
    reference = _request_reference(ticket.request_id, request_id, ticket.ticket_id)
    lines = [
        f"Request ID: {reference}",
        f"Jira ticket: {ticket.ticket_id}",
        f"Action: {ticket.action}",
        f"Reporter email: {ticket.reporter_email}",
        f"Severity: {triage.severity.value}",
        "",
        "Full report:",
        _team_report_body(ticket, triage),
    ]
    if config.include_ticket_url:
        lines.append(f"Ticket URL: {ticket.ticket_url}")
    return "\n".join(lines)


def _reporter_ticket_created_subject(ticket: TicketInfo, triage: TriageResult, request_id: str) -> str:
    reference = _request_reference(ticket.request_id, request_id, ticket.ticket_id)
    return f"Ticket assigned - {reference}"


def _reporter_ticket_created_email_body(
    ticket: TicketInfo,
    triage: TriageResult,
    config: NylasConfig,
    request_id: str,
) -> str:
    reference = _request_reference(ticket.request_id, request_id, ticket.ticket_id)
    lines = [
        f"You have been assigned ticket #{reference}.",
        "You will be notified once this issue is resolved.",
        "Thanks for reporting this issue.",
        "Our teams have already been notified.",
    ]
    return "\n".join(lines)


def _reporter_resolution_subject(payload: ResolutionPayload, request_id: str) -> str:
    reference = _request_reference(payload.request_id, request_id, payload.ticket_id)
    return f"Issue resolved - {reference}"


def _reporter_resolution_email_body(
    payload: ResolutionPayload,
    config: NylasConfig,
    request_id: str,
) -> str:
    reference = _request_reference(payload.request_id, request_id, payload.ticket_id)
    lines = [
        f"Your reported issue #{reference} has been resolved.",
        f"Jira ticket: {payload.ticket_id}",
        f"Resolved by: {payload.resolved_by}",
        f"Resolution notes: {payload.resolution_notes.strip()}",
    ]
    if config.include_ticket_url:
        lines.append("Open the incident portal for more details.")
    return "\n".join(lines)


def _team_report_body(ticket: TicketInfo, triage: TriageResult) -> str:
    if ticket.description.strip():
        return ticket.description.strip()

    return "\n".join(
        [
            f"Technical summary: {triage.technical_summary.strip()}",
            f"Business impact: {triage.business_impact_summary.strip()}",
        ]
    )


def _request_reference(stored_request_id: str | None, request_id: str | None, fallback: str) -> str:
    normalized_stored_request_id = (stored_request_id or "").strip()
    if normalized_stored_request_id:
        return normalized_stored_request_id

    normalized_request_id = (request_id or "").strip()
    if normalized_request_id:
        return normalized_request_id

    return fallback.strip()


def _extract_message_id(response: dict[str, object]) -> str | None:
    for key in ("message_id", "id"):
        value = response.get(key)
        if value:
            return str(value)
    return None


def _extract_status(response: dict[str, object]) -> str:
    value = response.get("status")
    if value:
        return str(value)
    return "accepted"