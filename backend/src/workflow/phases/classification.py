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

    request_id = preprocessed.request_id or "unknown"
    index = get_qdrant_index()
    if index is None:
        logger.info("vector_db_retrieval", request_id=request_id, status="stub", integration="qdrant")
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
                    timestamp=_parse_timestamp(meta.get("timestamp")),
                    description=meta.get(
                        "description",
                        node_with_score.node.get_content()[:200],
                    ),
                    resolution=meta.get("resolution") or None,
                    similarity_score=node_with_score.score or 0.0,
                )
            )

        logger.info(
            "vector_db_retrieval_done",
            request_id=request_id,
            candidates_count=len(candidates),
            top_k=_TOP_K_CANDIDATES,
        )
        return candidates

    except Exception as exc:
        logger.warning("vector_db_retrieval_failed", request_id=request_id, error=str(exc))
        return []


# ── Step 2: Node Reranker ─────────────────────────────────────────────────────

def rerank_candidates(candidates: list[HistoricalCandidate]) -> list[HistoricalCandidate]:
    """Rerank candidates using Cohere's intelligent ranking model.

    Uses llama_index's CohereRerank postprocessor for semantic reranking.
    Falls back to similarity-based sorting if Cohere is unavailable.
    """
    if not candidates:
        return []

    # Try Cohere reranking (requires COHERE_API_KEY)
    try:
        from llama_index.postprocessor.cohere_rerank import CohereRerank
        from llama_index.core.schema import NodeWithScore, TextNode

        # Convert HistoricalCandidate back to Nodes for reranking
        nodes_with_scores = [
            NodeWithScore(
                node=TextNode(
                    text=c.description,
                    id_=c.incident_id,
                    metadata={
                        "incident_id": c.incident_id,
                        "resolution": c.resolution,
                        "timestamp": c.timestamp.isoformat(),
                    },
                ),
                score=c.similarity_score,
            )
            for c in candidates
        ]

        # Initialize Cohere reranker
        reranker = CohereRerank(
            top_n=_RERANKER_TOP_N,
            model="rerank-english-v3.0",
        )

        # Rerank using Cohere
        reranked_nodes = reranker.postprocess_nodes(
            nodes=nodes_with_scores,
            query_str=candidates[0].description if candidates else "",  # Use first desc as query context
        )

        # Convert back to HistoricalCandidate
        reranked_candidates = [
            HistoricalCandidate(
                incident_id=node.node.metadata.get("incident_id", node.node.id_),
                description=node.node.get_content(),
                resolution=node.node.metadata.get("resolution"),
                timestamp=datetime.fromisoformat(
                    node.node.metadata.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
                ),
                similarity_score=node.score or 0.0,
            )
            for node in reranked_nodes
        ]

        logger.info(
            "rerank_done",
            reranker="cohere",
            input_count=len(candidates),
            output_count=len(reranked_candidates),
        )
        return reranked_candidates

    except ImportError:
        logger.warning("rerank_fallback", reason="CohereRerank not installed")
    except Exception as exc:
        logger.warning("rerank_fallback", reason="cohere_error", error=str(exc))

    # Fallback: Sort by similarity score
    ranked = sorted(candidates, key=lambda c: c.similarity_score, reverse=True)
    top_n = ranked[:_RERANKER_TOP_N]
    logger.info(
        "rerank_done",
        reranker="similarity_fallback",
        input_count=len(candidates),
        output_count=len(top_n),
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
            "classification_result",
            incident_type=IncidentType.NEW_INCIDENT.value,
            best_score=round(top.similarity_score, 3),
            threshold=_HIGH_SIMILARITY_THRESHOLD,
        )
        return ClassificationResult(
            incident_type=IncidentType.NEW_INCIDENT,
            top_candidates=candidates,
        )

    age_hours = _hours_since(top.timestamp)

    if age_hours <= _ALERT_STORM_HOURS:
        logger.info(
            "classification_result",
            incident_type=IncidentType.ALERT_STORM.value,
            top_candidate_age_hours=round(age_hours, 1),
            score=round(top.similarity_score, 3),
        )
        return ClassificationResult(
            incident_type=IncidentType.ALERT_STORM,
            top_candidates=candidates,
        )

    logger.info(
        "classification_result",
        incident_type=IncidentType.HISTORICAL_REGRESSION.value,
        top_candidate_age_hours=round(age_hours, 1),
        score=round(top.similarity_score, 3),
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
