import asyncio

from src.utils.logger import logger
from src.workflow.models import (
    ClassificationResult,
    IncidentType,
    PreprocessedIncident,
    Severity,
    ToolResult,
    TriageResult,
)
from src.workflow.tools.business_impact import check_business_impact
from src.workflow.tools.codebase_analyzer import analyze_codebase
from src.workflow.tools.infra_analyzer import analyze_infrastructure
from src.workflow.tools.telemetry_analyzer import analyze_telemetry

_INFRA_KEYWORDS = ["terraform", "infrastructure", ".tf", "deployment", "kubernetes", "k8s", "pod", "helm"]
_CODEBASE_KEYWORDS = ["error", "exception", "syntax", "traceback", "stacktrace", "null pointer", "500", "bug"]
_TELEMETRY_KEYWORDS = ["spike", "latency", "cpu", "memory", "disk", "timeout", "p99", "metric", "alert"]

_TOOL_DISPATCH: dict[str, any] = {
    "business_impact": check_business_impact,
    "codebase_analyzer": analyze_codebase,
    "infra_analyzer": analyze_infrastructure,
    "telemetry_analyzer": analyze_telemetry,
}


def _select_tools(
    preprocessed: PreprocessedIncident,
    classification: ClassificationResult,
    previous_results: list[ToolResult] | None = None,
) -> list[str]:
    """Select relevant analysis tools based on incident content keywords.
    
    Skips tools that were already dispatched in previous iterations.
    """
    previous_results = previous_results or []
    already_called = {result.tool_name for result in previous_results}
    
    text = preprocessed.consolidated_text.lower()
    selected: list[str] = []
    
    if "business_impact" not in already_called:
        selected.append("business_impact")
    
    if any(kw in text for kw in _INFRA_KEYWORDS) and "infra_analyzer" not in already_called:
        selected.append("infra_analyzer")
    if any(kw in text for kw in _CODEBASE_KEYWORDS) and "codebase_analyzer" not in already_called:
        selected.append("codebase_analyzer")
    if any(kw in text for kw in _TELEMETRY_KEYWORDS) and "telemetry_analyzer" not in already_called:
        selected.append("telemetry_analyzer")

    logger.info("tools_selected", tools=selected)
    return selected


async def _dispatch_tools(
    tools: list[str],
    preprocessed: PreprocessedIncident,
) -> list[ToolResult]:
    """Dispatch selected tools concurrently and collect results."""
    coroutines = [
        _TOOL_DISPATCH[tool](preprocessed.consolidated_text)
        for tool in tools
        if tool in _TOOL_DISPATCH
    ]
    results = await asyncio.gather(*coroutines)
    logger.info("tools_completed", count=len(results))
    return list(results)


def _consolidate_triage(
    preprocessed: PreprocessedIncident,
    classification: ClassificationResult,
    tool_results: list[ToolResult],
) -> TriageResult:
    """Merge classification and tool findings into a unified triage report."""
    severity = _determine_severity(classification, tool_results)
    business_impact = _extract_business_impact(tool_results)
    technical_summary = _build_technical_summary(preprocessed, classification, tool_results)

    return TriageResult(
        classification=classification,
        tool_results=tool_results,
        technical_summary=technical_summary,
        severity=severity,
        business_impact_summary=business_impact,
    )


def _determine_severity(
    classification: ClassificationResult,
    tool_results: list[ToolResult],
) -> Severity:
    if classification.incident_type == IncidentType.ALERT_STORM:
        return Severity.CRITICAL

    severity_hints = [r.severity_hint for r in tool_results if r.severity_hint]
    if Severity.CRITICAL in severity_hints:
        return Severity.CRITICAL
    if Severity.HIGH in severity_hints:
        return Severity.HIGH
    if classification.incident_type == IncidentType.HISTORICAL_REGRESSION:
        return Severity.HIGH
    return Severity.MEDIUM


def _extract_business_impact(tool_results: list[ToolResult]) -> str:
    for result in tool_results:
        if result.tool_name == "business_impact":
            return result.findings
    return "Business impact not assessed."


def _build_technical_summary(
    preprocessed: PreprocessedIncident,
    classification: ClassificationResult,
    tool_results: list[ToolResult],
) -> str:
    lines = [
        f"Incident type: {classification.incident_type}",
        f"Description: {preprocessed.consolidated_text[:500]}",
    ]
    if classification.historical_rca:
        lines.append(f"Historical RCA: {classification.historical_rca}")
    for result in tool_results:
        lines.append(f"[{result.tool_name}] {result.findings}")
    return "\n".join(lines)
