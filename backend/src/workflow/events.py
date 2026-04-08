from llama_index.core.workflow import Event

from src.workflow.models import (
    ClassificationResult,
    HistoricalCandidate,
    PreprocessedIncident,
    ToolResult,
    TriageResult,
)


# ── Candidate retrieval pipeline ──────────────────────────────────────────────

class CandidatesRetrievedEvent(Event):
    """Emitted after Top-K vector retrieval from Qdrant."""

    preprocessed: PreprocessedIncident
    candidates: list[HistoricalCandidate]


class RankedCandidatesEvent(Event):
    """Emitted after cross-encoder / score-based reranking to Top-N."""

    preprocessed: PreprocessedIncident
    candidates: list[HistoricalCandidate]


# ── Downstream pipeline ───────────────────────────────────────────────────────

class ContextEnrichedEvent(Event):
    preprocessed: PreprocessedIncident
    classification: ClassificationResult


class ToolCallEvent(Event):
    preprocessed: PreprocessedIncident
    classification: ClassificationResult
    tools_to_dispatch: list[str]
    previous_results: list[ToolResult] = []
    iteration: int = 0


class ToolResultEvent(Event):
    preprocessed: PreprocessedIncident
    classification: ClassificationResult
    tool_results: list[ToolResult]
    iteration: int = 0


class TriageCompleteEvent(Event):
    preprocessed: PreprocessedIncident
    triage: TriageResult