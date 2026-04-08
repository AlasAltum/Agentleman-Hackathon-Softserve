from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.guardrails import GuardrailsEngine
from src.utils.logger import logger
from src.workflow.models import IncidentInput, PreprocessedIncident, ResolutionPayload
from src.workflow.phases.preprocessing import preprocess_incident
from src.workflow.phases.resolution import handle_resolution
from src.workflow.sre_workflow import SREIncidentWorkflow

router = APIRouter(prefix="/api")


class IngestRequest(BaseModel):
    text_desc: str
    reporter_email: str
    file_mime_type: str | None = None


@router.post("/ingest")
async def ingest_incident(request: IngestRequest):
    """Phase 1 entry point: submit an incident report for automated triage.

    Pre-workflow phases executed here:
        - Guardrails validation
        - Dynamic preprocessing (file routing, content consolidation)
    """
    incident = IncidentInput(
        text_desc=request.text_desc,
        reporter_email=request.reporter_email,
        file_mime_type=request.file_mime_type,
    )

    try:
        engine = GuardrailsEngine()
        result = engine.validate(incident.text_desc)
        if not result.is_safe:
            logger.warning("[ingest] Guardrails blocked input: %s", result.message)
            raise HTTPException(status_code=400, detail=result.message)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[ingest] Guardrails validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))

    preprocessed = preprocess_incident(incident)
    logger.info("[ingest] Preprocessing complete — text length=%d", len(preprocessed.consolidated_text))

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