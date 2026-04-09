import mlflow
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
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


@router.post("/ingest")
async def ingest_incident(
    request: Request,
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
    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    bind_request_context(request_id, phase="ingest", component="api")
    
    logger.info("ingest_started", text_desc_length=len(text_desc), has_attachment=file_attachment is not None)

    file_content: bytes | None = None
    file_mime_type: str | None = None
    file_name: str | None = None

    if file_attachment:
        file_content = await file_attachment.read()
        file_mime_type = file_attachment.content_type
        file_name = file_attachment.filename

        ct_result = ContentTypeGuardrail().validate("", mime_type=file_mime_type)
        if not ct_result.is_safe:
            logger.warning("blocked_mime_type", mime_type=file_mime_type, reason=ct_result.message)
            raise HTTPException(status_code=400, detail=ct_result.message)

    incident = IncidentInput(
        text_desc=text_desc,
        reporter_email=reporter_email,
        file_content=file_content,
        file_mime_type=file_mime_type,
        file_name=file_name,
    )

    preprocessed = await preprocess_incident(incident)
    preprocessed.request_id = request_id
    logger.info("preprocessing_complete", text_length=len(preprocessed.consolidated_text))

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
        with start_run(request_id=request_id, run_name=f"incident-{request_id[:8]}"):
            structlog.contextvars.bind_contextvars(run_id=request_id)
            with mlflow.start_span(name="sre_incident_workflow", span_type=mlflow.entities.SpanType.CHAIN) as span:
                span.set_inputs({"request_id": request_id, "text_length": len(preprocessed.consolidated_text)})
                ticket = await workflow.run(preprocessed=preprocessed)
                span.set_outputs({"ticket_id": ticket.ticket_id, "action": ticket.action})

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