from datetime import datetime, timezone

from src.utils.logger import logger
from src.workflow.models import (
    ClassificationResult,
    HistoricalCandidate,
    IncidentType,
    PreprocessedIncident,
)

_HIGH_SIMILARITY_THRESHOLD = 0.75
_ALERT_STORM_HOURS = 24
_TOP_K_CANDIDATES = 5
_RERANKER_TOP_N = 3


def _retrieve_candidates(preprocessed: PreprocessedIncident) -> list[HistoricalCandidate]:
    """Query vector DB for top-K historical incidents similar to the current report.

    Stub: returns empty list until Qdrant integration is wired.
    """
    logger.info("vector_db_retrieval", status="stub", integration="qdrant")
    return []


def _rerank_candidates(
    candidates: list[HistoricalCandidate],
) -> list[HistoricalCandidate]:
    """Cross-encoder reranking to filter down to top-N most relevant candidates.

    Stub: passes candidates through until reranker integration is wired.
    """
    return candidates[:_RERANKER_TOP_N]


def _classify_incident(candidates: list[HistoricalCandidate]) -> ClassificationResult:
    """Classify incident as Alert Storm, Historical Regression, or New Incident."""
    if not candidates:
        return ClassificationResult(incident_type=IncidentType.NEW_INCIDENT)

    top = candidates[0]
    if top.similarity_score < _HIGH_SIMILARITY_THRESHOLD:
        return ClassificationResult(
            incident_type=IncidentType.NEW_INCIDENT,
            top_candidates=candidates,
        )

    age_hours = _hours_since(top.timestamp)
    if age_hours <= _ALERT_STORM_HOURS:
        logger.info("alert_storm_detected", top_candidate_age_hours=age_hours)
        return ClassificationResult(
            incident_type=IncidentType.ALERT_STORM,
            top_candidates=candidates,
        )

    logger.info("historical_regression_detected", top_candidate_age_hours=age_hours)
    return ClassificationResult(
        incident_type=IncidentType.HISTORICAL_REGRESSION,
        top_candidates=candidates,
        historical_rca=top.resolution,
    )


def _hours_since(timestamp: datetime) -> float:
    now = datetime.now(tz=timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (now - timestamp).total_seconds() / 3600
