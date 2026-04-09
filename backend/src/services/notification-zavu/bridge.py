from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.workflow.models import ResolutionPayload, TicketInfo, TriageResult

from .client import ZavuClient, ZavuClientError, ZavuConfig, ZavuConfigurationError
from .observability import log_event, new_request_id, record_counter, traced_operation

_RECIPIENT_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


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


def load_config_from_env() -> ZavuConfig:
    return ZavuConfig.from_env()


def notify_team(
    ticket: TicketInfo,
    triage: TriageResult,
    request_id: str | None = None,
) -> NotificationFanoutResult:
    active_request_id = request_id or new_request_id()
    config = load_config_from_env()
    if not config.team_email_recipients and not config.team_telegram_chat_ids:
        raise ZavuConfigurationError(
            "Configure ZAVU_TEAM_EMAIL_RECIPIENTS and/or ZAVU_TEAM_TELEGRAM_CHAT_IDS"
        )

    client = ZavuClient(config)
    with traced_operation(
        "zavu.notify_team",
        active_request_id,
        ticket_id=ticket.ticket_id,
        severity=triage.severity.value,
        action=ticket.action,
    ):
        log_event(
            "info",
            "zavu.team_notification.started",
            active_request_id,
            ticket_id=ticket.ticket_id,
            team_email_count=len(config.team_email_recipients),
            team_telegram_count=len(config.team_telegram_chat_ids),
        )

        dispatched: list[DispatchResult] = []
        failed: list[DispatchResult] = []
        for recipient in config.team_email_recipients:
            result = _dispatch_email(
                client,
                recipient=recipient,
                subject=_team_email_subject(ticket, triage),
                text=_team_email_body(ticket, triage, config),
                request_id=active_request_id,
            )
            _append_result(dispatched, failed, result)

        for chat_id in config.team_telegram_chat_ids:
            result = _dispatch_telegram(
                client,
                recipient=chat_id,
                text=_team_telegram_body(ticket, triage, config),
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
            "zavu.team_notification.completed",
            active_request_id,
            dispatched=len(dispatched),
            failed=len(failed),
        )
        return summary


def notify_reporter_resolution(
    reporter_email: str,
    payload: ResolutionPayload,
    request_id: str | None = None,
    reporter_telegram_chat_id: str | None = None,
) -> NotificationFanoutResult:
    active_request_id = request_id or new_request_id()
    config = load_config_from_env()
    client = ZavuClient(config)

    with traced_operation(
        "zavu.notify_reporter_resolution",
        active_request_id,
        ticket_id=payload.ticket_id,
        reporter_email=reporter_email,
    ):
        log_event(
            "info",
            "zavu.reporter_notification.started",
            active_request_id,
            ticket_id=payload.ticket_id,
            reporter_email=reporter_email,
        )

        dispatched: list[DispatchResult] = []
        failed: list[DispatchResult] = []
        email_result = _dispatch_email(
            client,
            recipient=reporter_email,
            subject=f"Incident resolved - {payload.ticket_id}",
            text=_reporter_resolution_email_body(payload, config),
            request_id=active_request_id,
        )
        _append_result(dispatched, failed, email_result)

        telegram_chat_id = reporter_telegram_chat_id or config.reporter_telegram_map.get(
            reporter_email.strip().lower()
        )
        if telegram_chat_id:
            telegram_result = _dispatch_telegram(
                client,
                recipient=telegram_chat_id,
                text=_reporter_resolution_telegram_body(payload, config),
                request_id=active_request_id,
            )
            _append_result(dispatched, failed, telegram_result)
        else:
            log_event(
                "warning",
                "zavu.reporter_notification.telegram_skipped",
                active_request_id,
                reporter_email=reporter_email,
                reason="missing_chat_id",
            )

        return NotificationFanoutResult(
            request_id=active_request_id,
            dispatched=dispatched,
            failed=failed,
        )


def _dispatch_email(
    client: ZavuClient,
    *,
    recipient: str,
    subject: str,
    text: str,
    request_id: str,
) -> DispatchResult:
    return _dispatch_message(
        client,
        channel="email",
        recipient=recipient,
        text=text,
        request_id=request_id,
        subject=subject,
        reply_to=client.config.email_reply_to,
    )


def _dispatch_telegram(
    client: ZavuClient,
    *,
    recipient: str,
    text: str,
    request_id: str,
) -> DispatchResult:
    return _dispatch_message(
        client,
        channel="telegram",
        recipient=recipient,
        text=text,
        request_id=request_id,
    )


def _dispatch_message(
    client: ZavuClient,
    *,
    channel: str,
    recipient: str,
    text: str,
    request_id: str,
    subject: str | None = None,
    reply_to: str | None = None,
) -> DispatchResult:
    try:
        response = client.send_message(
            to=recipient,
            channel=channel,
            text=text,
            subject=subject,
            reply_to=reply_to,
            request_id=request_id,
            idempotency_key=_idempotency_key(request_id, channel, recipient),
        )
        message_id = _extract_message_id(response)
        status = _extract_status(response)
        result = DispatchResult(
            channel=channel,
            recipient=recipient,
            status=status,
            message_id=message_id,
        )
        record_counter("zavu_notifications_sent_total", attributes={"channel": channel})
        log_event(
            "info",
            "zavu.message.sent",
            request_id,
            channel=channel,
            recipient=recipient,
            status=status,
            message_id=message_id,
        )
        return result
    except ZavuClientError as exc:
        result = DispatchResult(
            channel=channel,
            recipient=recipient,
            status="failed",
            error=str(exc),
        )
        record_counter("zavu_notifications_failed_total", attributes={"channel": channel})
        log_event(
            "error",
            "zavu.message.failed",
            request_id,
            channel=channel,
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


def _team_email_subject(ticket: TicketInfo, triage: TriageResult) -> str:
    return f"[{triage.severity.value.upper()}] Incident triaged - {ticket.ticket_id}"


def _team_email_body(ticket: TicketInfo, triage: TriageResult, config: ZavuConfig) -> str:
    lines = [
        f"Ticket: {ticket.ticket_id}",
        f"Action: {ticket.action}",
        f"Severity: {triage.severity.value}",
        f"Technical summary: {triage.technical_summary.strip()}",
        f"Business impact: {triage.business_impact_summary.strip()}",
    ]
    if config.include_ticket_url:
        lines.append(f"Ticket URL: {ticket.ticket_url}")
    return "\n".join(lines)


def _team_telegram_body(ticket: TicketInfo, triage: TriageResult, config: ZavuConfig) -> str:
    lines = [
        f"[{triage.severity.value.upper()}] Incident triaged",
        f"Ticket: {ticket.ticket_id}",
        f"Action: {ticket.action}",
        triage.technical_summary.strip(),
    ]
    if config.include_ticket_url:
        lines.append(ticket.ticket_url)
    return "\n".join(lines)


def _reporter_resolution_email_body(payload: ResolutionPayload, config: ZavuConfig) -> str:
    lines = [
        f"Your incident linked to {payload.ticket_id} has been resolved.",
        f"Resolved by: {payload.resolved_by}",
        f"Resolution notes: {payload.resolution_notes.strip()}",
    ]
    if config.include_ticket_url:
        lines.append("A direct ticket link can be added after URL verification is enabled in Zavu.")
    return "\n".join(lines)


def _reporter_resolution_telegram_body(payload: ResolutionPayload, config: ZavuConfig) -> str:
    lines = [
        f"Incident resolved: {payload.ticket_id}",
        f"Resolved by: {payload.resolved_by}",
        payload.resolution_notes.strip(),
    ]
    if config.include_ticket_url:
        lines.append("Open the incident portal for more details.")
    return "\n".join(lines)


def _idempotency_key(request_id: str, channel: str, recipient: str) -> str:
    slug = _RECIPIENT_SLUG_RE.sub("-", recipient).strip("-").lower()
    return f"{request_id}:{channel}:{slug[:64]}"


def _extract_message_id(response: dict[str, object]) -> str | None:
    message = response.get("message")
    if isinstance(message, dict):
        message_id = message.get("id")
        if message_id:
            return str(message_id)
    for key in ("messageId", "id"):
        value = response.get(key)
        if value:
            return str(value)
    return None


def _extract_status(response: dict[str, object]) -> str:
    message = response.get("message")
    if isinstance(message, dict) and message.get("status"):
        return str(message["status"])
    if response.get("status"):
        return str(response["status"])
    return "accepted"