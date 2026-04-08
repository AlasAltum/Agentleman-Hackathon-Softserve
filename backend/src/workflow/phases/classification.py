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
_TOP_K_CANDIDATES = 10   # retrieved from Qdrant
_RERANKER_TOP_N = 3      # kept after reranking


# ── Step 1: Candidate Retriever ───────────────────────────────────────────────

async def retrieve_candidates(preprocessed: PreprocessedIncident) -> list[HistoricalCandidate]:
    """Query Qdrant for the Top-K historical incidents most similar to this report.

    Degrades gracefully to an empty list when Qdrant is unreachable, causing
    the downstream classifier to fall back to NEW_INCIDENT.
    """
    from src.integrations.qdrant_store import get_qdrant_index

    index = get_qdrant_index()
    if index is None:
        logger.warning("[classification] Qdrant unavailable — skipping vector retrieval")
        return []

    try:
        retriever = index.as_retriever(similarity_top_k=_TOP_K_CANDIDATES)
        nodes = await retriever.aretrieve(preprocessed.consolidated_text)

        candidates: list[HistoricalCandidate] = []
        for node_with_score in nodes:
            meta = node_with_score.node.metadata or {}
            candidates.append(
                HistoricalCandidate(
                    incident_id=meta.get("incident_id", node_with_score.node.node_id),
                    similarity_score=node_with_score.score or 0.0,
                    timestamp=_parse_timestamp(meta.get("timestamp")),
                    summary=meta.get(
                        "summary",
                        node_with_score.node.get_content()[:200],
                    ),
                    resolution=meta.get("resolution") or None,
                )
            )

        logger.info(
            "[classification] Qdrant returned %d candidates (top_k=%d)",
            len(candidates),
            _TOP_K_CANDIDATES,
        )
        return candidates

    except Exception as exc:
        logger.warning("[classification] Vector retrieval failed: %s — defaulting to NEW_INCIDENT", exc)
        return []


# ── Step 2: Node Reranker ─────────────────────────────────────────────────────

def rerank_candidates(candidates: list[HistoricalCandidate]) -> list[HistoricalCandidate]:
    """Filter and sort candidates down to Top-N using similarity score.

    Production upgrade path: swap the slice for a cross-encoder reranker
    (e.g. llama_index.postprocessor.SentenceTransformerRerank) without
    changing the step interface.
    """
    ranked = sorted(candidates, key=lambda c: c.similarity_score, reverse=True)
    top_n = ranked[:_RERANKER_TOP_N]
    logger.info(
        "[classification] Reranked %d → %d candidates (threshold kept all above 0)",
        len(candidates),
        len(top_n),
    )
    return top_n


# ── Step 3: Cluster & Time Judge ──────────────────────────────────────────────

def classify_incident(candidates: list[HistoricalCandidate]) -> ClassificationResult:
    """Classify the incident by analysing similarity score + timestamp metadata.

    Decision logic (mirrors Mermaid diagram):
        similarity < threshold  → NEW_INCIDENT
        similarity ≥ threshold AND age ≤ 24 h  → ALERT_STORM  (active duplicate)
        similarity ≥ threshold AND age > 24 h   → HISTORICAL_REGRESSION (KEDB hit)
    """
    if not candidates:
        return ClassificationResult(incident_type=IncidentType.NEW_INCIDENT)

    top = candidates[0]

    if top.similarity_score < _HIGH_SIMILARITY_THRESHOLD:
        logger.info(
            "[classification] Best score %.3f < threshold %.3f — NEW_INCIDENT",
            top.similarity_score,
            _HIGH_SIMILARITY_THRESHOLD,
        )
        return ClassificationResult(
            incident_type=IncidentType.NEW_INCIDENT,
            top_candidates=candidates,
        )

    age_hours = _hours_since(top.timestamp)

    if age_hours <= _ALERT_STORM_HOURS:
        logger.info(
            "[classification] ALERT_STORM — score=%.3f age=%.1fh",
            top.similarity_score,
            age_hours,
        )
        return ClassificationResult(
            incident_type=IncidentType.ALERT_STORM,
            top_candidates=candidates,
        )

    logger.info(
        "[classification] HISTORICAL_REGRESSION — score=%.3f age=%.1fh",
        top.similarity_score,
        age_hours,
    )
    return ClassificationResult(
        incident_type=IncidentType.HISTORICAL_REGRESSION,
        top_candidates=candidates,
        historical_rca=top.resolution,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hours_since(timestamp: datetime) -> float:
    now = datetime.now(tz=timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (now - timestamp).total_seconds() / 3600


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)
