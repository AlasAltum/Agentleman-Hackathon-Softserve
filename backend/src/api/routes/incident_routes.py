from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from typing import Any, List
from src.guardrails import GuardrailsEngine
from src.guardrails.models import ThreatLevel
from src.guardrails.relevance_guardrail import RelevanceGuardrail
from src.guardrails.validators import ContentTypeGuardrail
from src.utils.logger import logger, bind_request_context, generate_request_id
from src.utils.tracing import start_run
from src.workflow.models import IncidentInput, PreprocessedIncident, ResolutionPayload
from src.workflow.phases.preprocessing import preprocess_incident
from src.workflow.phases.resolution import handle_resolution
from src.workflow.sre_workflow import SREIncidentWorkflow
import structlog

router = APIRouter(prefix="/api")

_MAX_FILES = 5


@router.post("/ingest")
async def ingest_incident(
    request: Request,
    text_desc: str = Form(...),
    reporter_email: str = Form(...),
    file_attachments: List[UploadFile] = File(default=[]),
):
    """Phase 1 entry point: submit an incident report for automated triage.

    Pre-workflow phases executed here:
        - MIME type validation
        - Dynamic preprocessing (file routing, content consolidation)
        - Guardrails validation on consolidated text (text + extracted file content)
        - LLM relevance check
    """
    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    bind_request_context(request_id, phase="ingest", component="api")

    logger.info("ingest_started", text_desc_length=len(text_desc), num_attachments=len(file_attachments))

    if len(file_attachments) > _MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files: maximum is {_MAX_FILES}.")

    file_contents: list[bytes] = []
    file_mime_types: list[str] = []
    file_names: list[str] = []

    ct_guardrail = ContentTypeGuardrail()
    for upload in file_attachments:
        content = await upload.read()
        mime_type = upload.content_type or ""
        file_name = upload.filename or ""

        ct_result = ct_guardrail.validate("", mime_type=mime_type)
        if not ct_result.is_safe:
            logger.warning("blocked_mime_type", file_name=file_name, mime_type=mime_type, reason=ct_result.message)
            raise HTTPException(status_code=400, detail=ct_result.message)

        file_contents.append(content)
        file_mime_types.append(mime_type)
        file_names.append(file_name)

    incident = IncidentInput(
        text_desc=text_desc,
        reporter_email=reporter_email,
        file_contents=file_contents,
        file_mime_types=file_mime_types,
        file_names=file_names,
    )

    try:
        preprocessed = await preprocess_incident(incident, request_id=request_id)
    except ValueError as exc:
        logger.warning("blocked_file_type", request_id=request_id, reason=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("preprocessing_complete", request_id=request_id, text_length=len(preprocessed.consolidated_text))

    # Pattern-based guardrails on the full consolidated text
    engine_result = GuardrailsEngine().validate(preprocessed.consolidated_text)
    if engine_result.threat_level == ThreatLevel.MALICIOUS:
        logger.warning("guardrails_blocked_input", threat_level="MALICIOUS", reason=engine_result.message)
        raise HTTPException(status_code=400, detail=engine_result.message)
    elif engine_result.threat_level == ThreatLevel.SUSPICIOUS:
        preprocessed.security_flag = "suspicious_input"
        logger.warning("guardrails_flagged_input", threat_level="SUSPICIOUS")

    # LLM relevance check — rejects off-topic or adversarial inputs
    relevance_result = await RelevanceGuardrail().validate(preprocessed.consolidated_text)
    if not relevance_result.is_safe:
        logger.warning("relevance_check_blocked", reason=relevance_result.message)
        raise HTTPException(status_code=422, detail=relevance_result.message)

    workflow = SREIncidentWorkflow(timeout=300)

    try:
        # MLflow 3.x: LlamaIndex autolog creates the Trace automatically when
        # workflow.run() executes.  start_run only activates the structlog
        # capture buffer; after the block it tags the completed Trace with
        # request_id and the captured log lines.
        structlog.contextvars.bind_contextvars(mlflow_request_id=request_id)
        with start_run(request_id=request_id):
            ticket = await workflow.run(preprocessed=preprocessed)

        logger.info("workflow_completed", ticket_id=ticket.ticket_id, action=ticket.action)
        
        return {
            "status": "triaged",
            "ticket_id": ticket.ticket_id,
            "ticket_url": ticket.ticket_url,
            "action": ticket.action,
            "request_id": request_id,
        }
    except Exception as exc:
        logger.error("triage_error", error_type=type(exc).__name__, exc_info=True)
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
        # Ignore non-resolution and non-human Jira updates so only manual task resolution fans out downstream work.
        return {
            "status": "ignored",
            "reason": ignore_reason,
            "ticket_id": issue_key,
        }

    resolution_payload = _build_resolution_payload(payload)
    # The webhook arrives after Jira already resolved the issue, so we only trigger the local post-resolution flow here.
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