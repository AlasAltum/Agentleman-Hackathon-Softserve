from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from typing import List
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

    workflow = SREIncidentWorkflow(timeout=120)

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


@router.post("/webhook/resolved")
async def on_ticket_resolved(payload: ResolutionPayload):
    """Phase 6 entry point: Jira webhook triggered when a ticket transitions to 'Done'."""
    await handle_resolution(payload)
    return {"status": "resolution_processed", "ticket_id": payload.ticket_id}