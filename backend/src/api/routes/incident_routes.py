from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.guardrails import GuardrailsEngine
from src.guardrails.models import ThreatLevel
from src.guardrails.relevance_guardrail import RelevanceGuardrail
from src.guardrails.validators import ContentTypeGuardrail
from src.utils.logger import logger
from src.workflow.models import IncidentInput, PreprocessedIncident, ResolutionPayload
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


@router.post("/webhook/resolved")
async def on_ticket_resolved(payload: ResolutionPayload):
    """Phase 6 entry point: Jira webhook triggered when a ticket transitions to 'Done'."""
    await handle_resolution(payload)
    return {"status": "resolution_processed", "ticket_id": payload.ticket_id}