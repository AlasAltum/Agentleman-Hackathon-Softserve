from llama_index.core.workflow import Event

from src.workflow.models import (
    ClassificationResult,
    PreprocessedIncident,
    ToolResult,
    TriageResult,
)


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