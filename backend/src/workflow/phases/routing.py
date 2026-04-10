import asyncio
import json

from llama_index.core.llms import ChatMessage

from src.utils.logger import logger
from src.utils.setup import get_settings
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
from src.workflow.tools.telemetry_analyzer import analyze_telemetry

_CODEBASE_KEYWORDS = ["error", "exception", "syntax", "traceback", "stacktrace", "null pointer", "500", "bug"]
_TELEMETRY_KEYWORDS = ["spike", "latency", "cpu", "memory", "disk", "timeout", "p99", "metric", "alert"]

_TOOL_DISPATCH: dict[str, any] = {
    "business_impact": check_business_impact,
    "codebase_analyzer": analyze_codebase,
    "telemetry_analyzer": analyze_telemetry,
}

_ROUTER_PROMPT = """\
You are an SRE triage router deciding which analysis tools to run for an incident.

Available tools:
- telemetry_analyzer: metric anomalies, latency spikes, CPU/memory/disk pressure, \
timeouts, p99 degradation, alert storms, any observable system-level degradation.
- codebase_analyzer: exceptions, stack traces, bad deploys, null pointer errors, \
syntax errors, code-level root causes, HTTP 500s from application logic.
- business_impact: ALWAYS include — estimates revenue loss, users affected, \
conversion rate drop, and financial exposure for any incident regardless of type.

Rules:
1. business_impact must always be in the output unless already called.
2. Include telemetry_analyzer if the incident involves observable system metrics \
(latency, CPU, memory, error rates, timeouts, spikes).
3. Include codebase_analyzer if the incident involves application errors, stack traces, \
deploy regressions, or code-level failures.
4. Both telemetry_analyzer and codebase_analyzer can be selected together when \
the incident has both dimensions (e.g. a bad deploy causing a latency spike).
5. Do NOT include tools listed in "Already analyzed".

Incident classification: {incident_type}
Already analyzed: {already_called}

Incident report:
{incident_text}

Respond with ONLY a valid JSON array of tool names, no explanation.
Example: ["telemetry_analyzer", "business_impact"]
"""


def _select_tools_keywords(
    preprocessed: PreprocessedIncident,
    previous_results: list[ToolResult],
) -> list[str]:
    """Keyword-based fallback tool selector."""
    already_called = {r.tool_name for r in previous_results}
    text = preprocessed.consolidated_text.lower()
    selected: list[str] = []

    if "business_impact" not in already_called:
        selected.append("business_impact")
    if any(kw in text for kw in _CODEBASE_KEYWORDS) and "codebase_analyzer" not in already_called:
        selected.append("codebase_analyzer")
    if any(kw in text for kw in _TELEMETRY_KEYWORDS) and "telemetry_analyzer" not in already_called:
        selected.append("telemetry_analyzer")

    return selected


async def _select_tools(
    preprocessed: PreprocessedIncident,
    classification: ClassificationResult,
    previous_results: list[ToolResult] | None = None,
) -> list[str]:
    """Select relevant analysis tools using the LLM router.

    Falls back to keyword matching if no LLM is configured or the LLM call fails.
    Always ensures business_impact is included unless already called.
    """
    previous_results = previous_results or []
    already_called = {r.tool_name for r in previous_results}
    request_id = preprocessed.request_id or "unknown"

    llm = get_settings().get("llm")
    if llm is not None:
        selected = await _select_tools_llm(
            llm, preprocessed, classification, already_called, request_id
        )
        if selected is not None:
            logger.info("tools_selected", request_id=request_id, tools=selected, router="llm")
            return selected

    # Fallback
    selected = _select_tools_keywords(preprocessed, previous_results)
    logger.info("tools_selected", request_id=request_id, tools=selected, router="keywords")
    return selected


async def _select_tools_llm(
    llm,
    preprocessed: PreprocessedIncident,
    classification: ClassificationResult,
    already_called: set[str],
    request_id: str,
) -> list[str] | None:
    """Call the LLM router. Returns None if the call fails or produces invalid output."""
    prompt = _ROUTER_PROMPT.format(
        incident_type=classification.incident_type.value.replace("_", " ").title(),
        already_called=sorted(already_called) if already_called else "none",
        incident_text=preprocessed.consolidated_text[:800],
    )
    try:
        response = await asyncio.to_thread(llm.chat, [ChatMessage(role="user", content=prompt)])
        raw = (response.message.content or "").strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        tools: list[str] = json.loads(raw)
        valid = set(_TOOL_DISPATCH.keys()) - already_called
        return [t for t in tools if t in valid]
    except Exception as exc:
        logger.warning("llm_router_failed", request_id=request_id, error=str(exc))
        return None


async def _dispatch_tools(
    tools: list[str],
    preprocessed: PreprocessedIncident,
) -> list[ToolResult]:
    """Dispatch selected tools concurrently and collect results."""
    request_id = preprocessed.request_id or "unknown"
    coroutines = [
        _TOOL_DISPATCH[tool](preprocessed.consolidated_text)
        for tool in tools
        if tool in _TOOL_DISPATCH
    ]
    results = await asyncio.gather(*coroutines)
    logger.info("tools_completed", request_id=request_id, count=len(results))
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
        f"Description: {preprocessed.consolidated_text[:500]}",
        f"Incident type: {classification.incident_type.value}",
    ]
    if classification.historical_rca:
        lines.append(f"Historical RCA: {classification.historical_rca}")
    for result in tool_results:
        lines.append(f"[{result.tool_name}] {result.findings}")
    return "\n".join(lines)
