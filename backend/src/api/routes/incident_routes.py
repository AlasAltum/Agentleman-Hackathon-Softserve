from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.guardrails import GuardrailsEngine
from src.guardrails.models import ThreatLevel
from src.guardrails.relevance_guardrail import RelevanceGuardrail
from src.guardrails.validators import ContentTypeGuardrail
from src.utils.logger import logger
from src.workflow.models import IncidentInput, ResolutionPayload
from src.workflow.phases.preprocessing import preprocess_incident
from src.workflow.phases.resolution import handle_resolution
from src.workflow.sre_workflow import SREIncidentWorkflow

router = APIRouter(prefix="/api")


@router.post("/ingest")
async def ingest_incident(
    text_desc: str = Form(...),
    reporter_email: str = Form(...),
    file_attachment: UploadFile | None = File(default=None),
):
    """Phase 1 entry point: submit an incident report for automated triage.

    Pre-workflow phases executed here:
        - MIME type validation
        - Dynamic preprocessing (file routing, content consolidation)
        - Guardrails validation on consolidated text (text + extracted file content)
        - LLM relevance check
    """
    file_content: bytes | None = None
    file_mime_type: str | None = None

    file_name: str | None = None

    if file_attachment:
        file_content = await file_attachment.read()
        file_mime_type = file_attachment.content_type
        file_name = file_attachment.filename

        ct_result = ContentTypeGuardrail().validate("", mime_type=file_mime_type)
        if not ct_result.is_safe:
            logger.warning("[ingest] Blocked MIME type: %s — %s", file_mime_type, ct_result.message)
            raise HTTPException(status_code=400, detail=ct_result.message)

    incident = IncidentInput(
        text_desc=text_desc,
        reporter_email=reporter_email,
        file_content=file_content,
        file_mime_type=file_mime_type,
        file_name=file_name,
    )

    # Preprocess first so guardrails evaluate the full consolidated text (desc + file content)
    preprocessed = await preprocess_incident(incident)
    logger.info("[ingest] Preprocessing complete — text length=%d", len(preprocessed.consolidated_text))

    # Pattern-based guardrails on the full consolidated text
    engine_result = GuardrailsEngine().validate(preprocessed.consolidated_text)
    if engine_result.threat_level == ThreatLevel.MALICIOUS:
        logger.warning("[ingest] Guardrails hard-blocked input: %s", engine_result.message)
        raise HTTPException(status_code=400, detail=engine_result.message)
    elif engine_result.threat_level == ThreatLevel.SUSPICIOUS:
        preprocessed.security_flag = "suspicious_input"
        logger.warning("[ingest] Guardrails soft-flagged input — proceeding with caution")

    # LLM relevance check — rejects off-topic or adversarial inputs
    relevance_result = await RelevanceGuardrail().validate(preprocessed.consolidated_text)
    if not relevance_result.is_safe:
        logger.warning("[ingest] Relevance check blocked input: %s", relevance_result.message)
        raise HTTPException(status_code=422, detail=relevance_result.message)

    workflow = SREIncidentWorkflow(timeout=120)
    try:
        ticket = await workflow.run(preprocessed=preprocessed)
        return {
            "status": "triaged",
            "ticket_id": ticket.ticket_id,
            "ticket_url": ticket.ticket_url,
            "action": ticket.action,
        }
    except Exception as exc:
        logger.error("[ingest] Unexpected triage error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal triage error.")


@router.post("/webhook/jira/resolved")
@router.post("/webhook/resolved")
async def on_ticket_resolved(payload: dict[str, Any]):
    """Phase 6 entry point for Jira issue update webhooks that resolve a task.

    Jira Cloud sends issue update events for many field changes. This handler
    narrows processing to human-triggered status transitions that move an issue
    into a resolved/done state.
    """
    issue_key = _extract_issue_key(payload)
    ignore_reason = _jira_resolution_ignore_reason(payload)
    if ignore_reason is not None:
        return {
            "status": "ignored",
            "reason": ignore_reason,
            "ticket_id": issue_key,
        }

    resolution_payload = _build_resolution_payload(payload)
    handle_resolution(resolution_payload)
    return {"status": "resolution_processed", "ticket_id": resolution_payload.ticket_id}


def _jira_resolution_ignore_reason(payload: dict[str, Any]) -> str | None:
    """Return a reason when the webhook should not trigger the resolution flow."""
    if not _extract_issue_key(payload):
        return "missing_issue_key"

    if payload.get("webhookEvent") not in {None, "jira:issue_updated"}:
        return "unsupported_webhook_event"

    status_change = _extract_status_change(payload)
    if status_change is None:
        return "missing_status_transition"

    if not _is_human_actor(payload):
        return "non_human_actor"

    if not _is_resolution_transition(payload, status_change):
        return "status_not_resolved"

    return None


def _build_resolution_payload(payload: dict[str, Any]) -> ResolutionPayload:
    """Project the Jira webhook into the internal resolution payload."""
    issue_key = _extract_issue_key(payload)
    if issue_key is None:
        raise HTTPException(status_code=400, detail="Invalid Jira webhook payload: missing issue.key")

    status_change = _extract_status_change(payload) or {}
    from_status = _clean_string(status_change.get("fromString")) or "unknown"
    to_status = _clean_string(status_change.get("toString")) or _extract_status_name(payload) or "done"
    issue_summary = _extract_issue_summary(payload)
    notes = f"Jira webhook status transition: {from_status} -> {to_status}."
    if issue_summary:
        notes = f"{notes} Issue summary: {issue_summary}"

    return ResolutionPayload(
        ticket_id=issue_key,
        resolved_by=_extract_actor_name(payload),
        resolution_notes=notes,
    )


def _extract_issue_key(payload: dict[str, Any]) -> str | None:
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None
    return _clean_string(issue.get("key"))


def _extract_status_change(payload: dict[str, Any]) -> dict[str, Any] | None:
    changelog = payload.get("changelog")
    if not isinstance(changelog, dict):
        return None

    items = changelog.get("items")
    if not isinstance(items, list):
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        if _clean_string(item.get("field"), lowercase=True) == "status":
            return item
    return None


def _extract_status_name(payload: dict[str, Any]) -> str | None:
    status = _extract_status(payload)
    if status is None:
        return None
    return _clean_string(status.get("name"))


def _extract_status_category_key(payload: dict[str, Any]) -> str | None:
    status = _extract_status(payload)
    if status is None:
        return None

    category = status.get("statusCategory")
    if not isinstance(category, dict):
        return None
    return _clean_string(category.get("key"), lowercase=True)


def _extract_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None

    fields = issue.get("fields")
    if not isinstance(fields, dict):
        return None

    status = fields.get("status")
    if not isinstance(status, dict):
        return None
    return status


def _extract_issue_summary(payload: dict[str, Any]) -> str | None:
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        return None

    fields = issue.get("fields")
    if not isinstance(fields, dict):
        return None
    return _clean_string(fields.get("summary"))


def _extract_actor_name(payload: dict[str, Any]) -> str:
    user = payload.get("user")
    if not isinstance(user, dict):
        return "jira-webhook-user"

    return (
        _clean_string(user.get("displayName"))
        or _clean_string(user.get("emailAddress"))
        or _clean_string(user.get("accountId"))
        or "jira-webhook-user"
    )


def _is_human_actor(payload: dict[str, Any]) -> bool:
    user = payload.get("user")
    if not isinstance(user, dict):
        return False

    account_type = _clean_string(user.get("accountType"), lowercase=True)
    return account_type == "atlassian"


def _is_resolution_transition(payload: dict[str, Any], status_change: dict[str, Any]) -> bool:
    resolved_names = {"done", "resolved", "closed"}
    current_category = _extract_status_category_key(payload)
    if current_category == "done":
        return True

    to_status = _clean_string(status_change.get("toString"), lowercase=True)
    current_status = _extract_status_name(payload)
    current_status_lower = current_status.lower() if current_status else None
    return to_status in resolved_names or current_status_lower in resolved_names


def _clean_string(value: Any, lowercase: bool = False) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned.lower() if lowercase else cleaned