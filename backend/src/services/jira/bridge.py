from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.workflow.models import PreprocessedIncident, ResolutionPayload, TicketInfo, TriageResult

from .client import JiraClient, JiraClientError, JiraConfig
from .observability import log_event, record_counter, traced_operation


@dataclass(frozen=True)
class JiraResolutionResult:
    """Describe the outcome of moving a Jira issue into its resolved state."""

    ticket_id: str
    ticket_url: str
    transition_id: str
    transition_name: str
    resolved_by: str


def load_config_from_env() -> JiraConfig:
    """Load Jira settings from the root environment configuration.

    This keeps the service aligned with the repository-wide `.env.example`
    instead of introducing service-local environment templates.
    """
    return JiraConfig.from_env()


def create_ticket(
    preprocessed: PreprocessedIncident,
    triage: TriageResult,
    request_id: str,
) -> TicketInfo:
    """Create a Jira issue for a newly reported incident.

    The user-facing ticket content comes from the incident report itself.
    Agent triage is only used to enrich Jira labels so the workflow remains
    easy to inspect without hard-coding the agent's narrative into the summary
    or description fields.
    """
    active_request_id = _require_request_id(request_id)
    config = load_config_from_env()
    client = JiraClient(config)
    reporter_email = preprocessed.original.reporter_email

    with traced_operation(
        "jira.create_ticket",
        active_request_id,
        reporter_email=reporter_email,
        severity=triage.severity.value,
        incident_type=triage.classification.incident_type.value,
    ):
        log_event(
            "info",
            "jira.ticket.created.started",
            active_request_id,
            reporter_email=reporter_email,
            severity=triage.severity.value,
            incident_type=triage.classification.incident_type.value,
        )

        issue = client.create_issue(
            summary=_build_issue_summary(preprocessed),
            description=_build_issue_document(preprocessed),
            labels=_build_labels(config, triage, preprocessed),
            request_id=active_request_id,
        )
        record_counter(
            "jira_tickets_created_total",
            attributes={"incident_type": triage.classification.incident_type.value},
        )
        log_event(
            "info",
            "jira.ticket.created.completed",
            active_request_id,
            issue_key=issue.issue_key,
            reporter_email=reporter_email,
        )
        return TicketInfo(
            ticket_id=issue.issue_key,
            ticket_url=issue.issue_url,
            action="created",
            reporter_email=reporter_email,
            request_id=active_request_id,
        )


def resolve_ticket(payload: ResolutionPayload, request_id: str) -> JiraResolutionResult:
    """Move an existing Jira issue to its resolved workflow state.

    This flow performs only the workflow transition. It intentionally does not
    add Jira comments or mutate extra fields, which keeps the resolution path
    narrow and predictable.
    """
    active_request_id = _require_request_id(request_id)
    config = load_config_from_env()
    client = JiraClient(config)

    with traced_operation(
        "jira.resolve_ticket",
        active_request_id,
        ticket_id=payload.ticket_id,
        resolved_by=payload.resolved_by,
    ):
        log_event(
            "info",
            "jira.ticket.resolution.started",
            active_request_id,
            ticket_id=payload.ticket_id,
            resolved_by=payload.resolved_by,
            notes_present=bool(payload.resolution_notes.strip()),
        )

        transitions = client.get_transitions(
            issue_key=payload.ticket_id,
            request_id=active_request_id,
        )
        resolution_transition = _select_resolution_transition(
            transitions,
            preferred_transition_name=config.resolved_transition_name,
        )
        client.transition_issue(
            issue_key=payload.ticket_id,
            transition_id=resolution_transition["id"],
            request_id=active_request_id,
        )
        record_counter("jira_tickets_resolved_total")
        log_event(
            "info",
            "jira.ticket.resolution.completed",
            active_request_id,
            ticket_id=payload.ticket_id,
            transition_id=resolution_transition["id"],
            transition_name=resolution_transition["name"],
            resolved_by=payload.resolved_by,
        )
        return JiraResolutionResult(
            ticket_id=payload.ticket_id,
            ticket_url=client.issue_browse_url(payload.ticket_id),
            transition_id=resolution_transition["id"],
            transition_name=resolution_transition["name"],
            resolved_by=payload.resolved_by,
        )


async def poll_ticket_until_resolved(
    ticket: TicketInfo,
    request_id: str,
    poll_interval_seconds: int = 30,
) -> None:
    """Poll Jira in local development because we could not expose a webhook endpoint.

    Once the ticket reaches a resolved state, this reuses the same webhook route
    that Jira would normally call in a deployed environment.
    """
    active_request_id = _require_request_id(ticket.request_id or request_id)
    config = load_config_from_env()
    client = JiraClient(config)
    previous_status_name: str | None = None

    log_event(
        "info",
        "jira.ticket.poller.started",
        active_request_id,
        ticket_id=ticket.ticket_id,
        interval_seconds=poll_interval_seconds,
    )

    while True:
        await asyncio.sleep(poll_interval_seconds)
        poll_request_id = f"{active_request_id}-poll"

        try:
            issue_payload = await asyncio.to_thread(
                client.get_issue,
                issue_key=ticket.ticket_id,
                fields=["summary", "status", "description"],
                request_id=poll_request_id,
            )
        except JiraClientError as exc:
            log_event(
                "warning",
                "jira.ticket.poller.failed",
                active_request_id,
                ticket_id=ticket.ticket_id,
                error=str(exc),
            )
            continue

        current_status_name = _issue_status_name(issue_payload)
        if not _issue_is_resolved(issue_payload):
            previous_status_name = current_status_name or previous_status_name
            continue

        from src.api.routes.incident_routes import on_ticket_resolved

        await on_ticket_resolved(
            _build_resolution_webhook_payload(
                issue_payload,
                previous_status_name=previous_status_name,
            )
        )
        log_event(
            "info",
            "jira.ticket.poller.completed",
            active_request_id,
            ticket_id=ticket.ticket_id,
            status_name=current_status_name,
        )
        return


def _build_issue_summary(preprocessed: PreprocessedIncident) -> str:
    """Create a short Jira summary from the original incident report.

    Example triage received by the surrounding flow:
    - `incident_type = new_incident`
    - `severity = high`

    Those triage values are intentionally kept out of the summary and only used
    in labels. If the original report says `Checkout API returns 500 after
    payment confirmation`, this method produces a summary like:

    `Incident report - Checkout API returns 500 after payment confirmation`
    """
    source_text = preprocessed.original.text_desc.strip() or preprocessed.consolidated_text.strip()
    headline = source_text.splitlines()[0] if source_text else "Incident details unavailable"
    compact_headline = " ".join(headline.split())
    summary = f"Incident report - {compact_headline}"
    return summary[:255]


def _build_labels(
    config: JiraConfig,
    triage: TriageResult,
    preprocessed: PreprocessedIncident,
) -> list[str]:
    """Convert agent triage into Jira labels without affecting ticket prose."""
    labels = list(config.default_labels)
    labels.append(f"severity-{triage.severity.value}")
    labels.append(f"incident-{triage.classification.incident_type.value}")

    if preprocessed.security_flag:
        labels.append("security-review")

    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label[:255])
    return deduped


def _build_issue_document(preprocessed: PreprocessedIncident) -> dict[str, Any]:
    """Build the Jira description from the reported incident context.

    The description captures who reported the incident, what they reported, and
    any extracted context from preprocessing so responders can inspect the raw
    signal without depending on the agent summary.
    """
    original_text = preprocessed.original.text_desc.strip() or "No original report provided."
    consolidated_text = preprocessed.consolidated_text.strip()
    paragraphs = [
        f"Reporter email: {preprocessed.original.reporter_email}",
        f"Request ID: {preprocessed.request_id or 'unknown'}",
        "Original report:",
        original_text,
    ]

    if consolidated_text and consolidated_text != original_text:
        paragraphs.append("Preprocessed incident context:")
        paragraphs.append(consolidated_text[:2000])

    if preprocessed.file_metadata.mime_types:
        paragraphs.append(
            "Attached content types: " + ", ".join(preprocessed.file_metadata.mime_types)
        )

    if preprocessed.security_flag:
        paragraphs.append(f"Security flag: {preprocessed.security_flag}")

    return _build_adf_document(paragraphs)


def _build_adf_document(paragraphs: list[str]) -> dict[str, Any]:
    """Convert plain text paragraphs into Atlassian Document Format."""
    content = []
    for paragraph in paragraphs:
        clean_text = paragraph.strip()
        if not clean_text:
            continue
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": clean_text}],
            }
        )
    return {"version": 1, "type": "doc", "content": content}


def _build_resolution_webhook_payload(
    issue_payload: dict[str, Any],
    *,
    previous_status_name: str | None,
) -> dict[str, Any]:
    fields = issue_payload.get("fields") or {}
    status = fields.get("status") if isinstance(fields, dict) else {}
    status_name = _issue_status_name(issue_payload) or "Done"
    return {
        "webhookEvent": "jira:issue_updated",
        "user": {
            "displayName": "jira-poller",
            "accountType": "atlassian",
        },
        "issue": {
            "key": issue_payload.get("key"),
            "fields": {
                "summary": fields.get("summary") if isinstance(fields, dict) else None,
                "status": status if isinstance(status, dict) else {"name": status_name},
                "description": fields.get("description") if isinstance(fields, dict) else None,
            },
        },
        "changelog": {
            "items": [
                {
                    "field": "status",
                    "fromString": previous_status_name or "In Progress",
                    "toString": status_name,
                }
            ]
        },
    }


def _issue_is_resolved(issue_payload: dict[str, Any]) -> bool:
    status = issue_payload.get("fields", {}).get("status", {})
    if not isinstance(status, dict):
        return False

    category = status.get("statusCategory")
    if isinstance(category, dict) and str(category.get("key", "")).strip().lower() == "done":
        return True

    status_name = str(status.get("name", "")).strip().lower()
    return status_name in {"done", "resolved", "closed"}


def _issue_status_name(issue_payload: dict[str, Any]) -> str | None:
    status = issue_payload.get("fields", {}).get("status", {})
    if not isinstance(status, dict):
        return None
    value = str(status.get("name", "")).strip()
    return value or None


def _select_resolution_transition(
    transitions: list[dict[str, Any]],
    preferred_transition_name: str | None,
) -> dict[str, str]:
    """Pick the Jira workflow transition that represents resolution.

    If the workflow uses a non-standard name, configure it explicitly with
    `JIRA_RESOLVED_TRANSITION_NAME` in the root environment file.
    """
    available = [_coerce_transition(transition) for transition in transitions]
    if preferred_transition_name:
        preferred_name = preferred_transition_name.strip().casefold()
        for transition in available:
            if transition["name"].casefold() == preferred_name:
                return transition
        raise JiraClientError(
            "Configured JIRA_RESOLVED_TRANSITION_NAME was not found. "
            f"Available transitions: {_available_transition_names(available)}"
        )

    standard_names = {
        "done",
        "resolved",
        "resolve issue",
        "close issue",
        "closed",
    }
    for transition in available:
        if transition["name"].casefold() in standard_names:
            return transition

    raise JiraClientError(
        "Could not determine a resolution transition automatically. "
        f"Available transitions: {_available_transition_names(available)}. "
        "Set JIRA_RESOLVED_TRANSITION_NAME in the root .env.example if your workflow uses a custom name."
    )


def _coerce_transition(transition: dict[str, Any]) -> dict[str, str]:
    """Normalize Jira transition payloads into the minimal structure this flow needs."""
    transition_id = str(transition.get("id", "")).strip()
    transition_name = str(transition.get("name", "")).strip()
    if not transition_id or not transition_name:
        raise JiraClientError(f"Invalid Jira transition payload: {transition}")
    return {"id": transition_id, "name": transition_name}


def _available_transition_names(transitions: list[dict[str, str]]) -> str:
    """Render transition names for actionable error messages."""
    return ", ".join(transition["name"] for transition in transitions) or "none"


def _require_request_id(request_id: str) -> str:
    """Reject calls that do not provide the request ID from the upstream flow."""
    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        raise ValueError("request_id is required")
    return normalized_request_id