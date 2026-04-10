from datetime import datetime, timezone
from time import perf_counter

from src.integrations.qdrant_store import store_incident
from src.utils.logger import logger, log_phase_start, log_phase_success, log_phase_failure
from src.workflow.models import ResolutionPayload


async def handle_resolution(payload: ResolutionPayload) -> None:
    """Phase 6: Handle Jira webhook when a ticket transitions to 'Done'.

    Feeds the resolution back into the knowledge base for future retrieval and
    triage improvement. Notification fan-out is handled by the webhook route so
    the same helper can be reused for ticket creation and resolution events.
    """
    request_id = payload.request_id or "unknown"
    log_phase_start("resolution", component="resolution", request_id=request_id)
    started_at = perf_counter()

    logger.info(
        "jira_ticket_resolved",
        request_id=request_id,
        ticket_id=payload.ticket_id,
        resolved_by=payload.resolved_by,
        reporter_email=payload.reporter_email or "unknown",
        resolution_notes=payload.resolution_notes[:200] if payload.resolution_notes else "",
        has_reporter_email=bool(payload.reporter_email),
    )

    await _save_to_knowledge_base(payload)

    latency_ms = int((perf_counter() - started_at) * 1000)
    log_phase_success(
        "resolution",
        latency_ms=latency_ms,
        ticket_id=payload.ticket_id,
        resolved_by=payload.resolved_by,
        request_id=request_id,
    )


async def _save_to_knowledge_base(payload: ResolutionPayload) -> None:
    """Upsert resolved ticket into Qdrant for the auto-improvement feedback loop.

    Uses LlamaIndex + QdrantVectorStore to embed and store the resolution so
    future incidents can retrieve it as a historical RCA candidate.
    """
    request_id = payload.request_id or "unknown"
    log_phase_start("kb_upsert", component="resolution", request_id=request_id)
    started_at = perf_counter()

    logger.info(
        "kb_upsert_started",
        request_id=request_id,
        ticket_id=payload.ticket_id,
        integration="qdrant",
        has_resolution_notes=bool(payload.resolution_notes.strip()),
    )

    timestamp = datetime.now(tz=timezone.utc).isoformat()
    text = f"{payload.resolution_notes}\nResolved by: {payload.resolved_by}"
    summary = payload.resolution_notes[:300] if payload.resolution_notes else payload.ticket_id

    try:
        await store_incident(
            incident_id=payload.ticket_id,
            text=text,
            summary=summary,
            resolution=payload.resolution_notes,
            timestamp=timestamp,
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        log_phase_success(
            "kb_upsert",
            latency_ms=latency_ms,
            ticket_id=payload.ticket_id,
            integration="qdrant",
            request_id=request_id,
        )
    except Exception as exc:
        latency_ms = int((perf_counter() - started_at) * 1000)
        log_phase_failure(
            "kb_upsert",
            error_type=type(exc).__name__,
            latency_ms=latency_ms,
            request_id=request_id,
        )
        logger.warning(
            "kb_upsert_failed",
            request_id=request_id,
            ticket_id=payload.ticket_id,
            integration="qdrant",
            error=str(exc),
        )
