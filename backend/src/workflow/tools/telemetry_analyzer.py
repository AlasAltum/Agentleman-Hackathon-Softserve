import asyncio

from src.utils.logger import logger
from src.workflow.models import Severity, ToolResult
from src.workflow.tools.mock_data.telemetry_logs import (
    KEYWORD_DATASET_INDEX,
    TELEMETRY_DATASETS,
    LogEntry,
    MetricSample,
)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_CRITICAL: dict[str, float] = {
    "cpu_percent":             90.0,
    "memory_percent":          90.0,
    "p99_latency_ms":        2000.0,
    "error_rate_percent":      10.0,
    "timeout_rate_percent":    10.0,
    "http_5xx_rate_percent":   10.0,
    "db_connections_active":   19.0,
    "auth_error_rate_percent":  5.0,
    "http_401_rate_percent":    5.0,
    "ntp_drift_ms":           500.0,
}

_HIGH: dict[str, float] = {
    "cpu_percent":             75.0,
    "memory_percent":          80.0,
    "p99_latency_ms":        1000.0,
    "error_rate_percent":       5.0,
    "timeout_rate_percent":     5.0,
    "http_5xx_rate_percent":    5.0,
    "db_connections_active":   16.0,
    "auth_error_rate_percent":  2.0,
    "http_401_rate_percent":    2.0,
    "ntp_drift_ms":            50.0,
}

_METRIC_UNITS: dict[str, str] = {
    "cpu_percent":             "%",
    "memory_percent":          "%",
    "p99_latency_ms":          "ms",
    "error_rate_percent":      "%",
    "timeout_rate_percent":    "%",
    "http_5xx_rate_percent":   "%",
    "db_connections_active":   " active connections",
    "db_query_time_p99_ms":    "ms",
    "auth_error_rate_percent": "%",
    "http_401_rate_percent":   "%",
    "ntp_drift_ms":            "ms",
    "requests_per_sec":        " req/s",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _select_dataset_index(incident_text: str) -> int:
    """Return the index of the most relevant mock dataset based on keyword matching."""
    text = incident_text.lower()
    scores: dict[int, int] = {}
    for keyword, idx in KEYWORD_DATASET_INDEX.items():
        if keyword in text:
            scores[idx] = scores.get(idx, 0) + 1
    if not scores:
        return 0
    return max(scores, key=lambda k: scores[k])


def _latest_samples(metrics: list[MetricSample]) -> dict[tuple[str, str], MetricSample]:
    """Keep only the most recent sample per (service, metric_name) pair."""
    latest: dict[tuple[str, str], MetricSample] = {}
    for sample in metrics:
        key = (sample.service, sample.metric_name)
        if key not in latest or sample.timestamp > latest[key].timestamp:
            latest[key] = sample
    return latest


def _classify_sample(sample: MetricSample) -> str | None:
    """Return 'CRITICAL', 'HIGH', or None based on threshold comparison."""
    if sample.metric_name in _CRITICAL and sample.value >= _CRITICAL[sample.metric_name]:
        return "CRITICAL"
    if sample.metric_name in _HIGH and sample.value >= _HIGH[sample.metric_name]:
        return "HIGH"
    return None


def _severity_from_levels(levels: list[str]) -> Severity | None:
    if "CRITICAL" in levels:
        return Severity.CRITICAL
    if "HIGH" in levels:
        return Severity.HIGH
    return None


def _format_anomaly_line(sample: MetricSample, level: str) -> str:
    unit = _METRIC_UNITS.get(sample.metric_name, "")
    label = f"{sample.metric_name.replace('_', ' ')}{unit}"
    threshold = _CRITICAL.get(sample.metric_name) if level == "CRITICAL" else _HIGH.get(sample.metric_name)
    threshold_str = f" (threshold: {threshold})" if threshold is not None else ""
    return f"  [{level}] {label}: {sample.value}{threshold_str}  @ {sample.timestamp}"


def _build_findings(
    anomalies_by_service: dict[str, list[tuple[MetricSample, str]]],
    logs: list[LogEntry],
    primary_service: str,
    severity_hint: Severity | None,
) -> str:
    lines: list[str] = []

    if not anomalies_by_service:
        lines.append("No metric anomalies detected in telemetry data.")
    else:
        lines.append(f"Anomalies detected across {len(anomalies_by_service)} service(s):\n")
        for service, items in sorted(anomalies_by_service.items()):
            lines.append(f"{service}:")
            for sample, level in sorted(items, key=lambda x: x[1]):
                lines.append(_format_anomaly_line(sample, level))
            lines.append("")

    error_logs = [e for e in logs if e.level in ("ERROR", "WARN") and e.service == primary_service]
    if error_logs:
        lines.append(f"Recent log events ({primary_service}):")
        for entry in error_logs[-5:]:
            lines.append(f"  [{entry.timestamp}] {entry.level}: {entry.message}")

    if severity_hint:
        lines.append(f"\nOverall severity hint: {severity_hint.value.upper()}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def _run_analysis(incident_text: str) -> ToolResult:
    """Synchronous core — extracted to keep analyze_telemetry awaitable without dead async."""
    logger.info("tool_execution", tool="telemetry_analyzer", status="running")

    dataset_idx = _select_dataset_index(incident_text)
    metrics, logs, primary_service = TELEMETRY_DATASETS[dataset_idx]

    latest = _latest_samples(metrics)

    anomalies_by_service: dict[str, list[tuple[MetricSample, str]]] = {}
    for sample in latest.values():
        level = _classify_sample(sample)
        if level:
            anomalies_by_service.setdefault(sample.service, []).append((sample, level))

    all_levels = [lvl for items in anomalies_by_service.values() for _, lvl in items]
    severity_hint = _severity_from_levels(all_levels)

    findings = _build_findings(anomalies_by_service, logs, primary_service, severity_hint)

    logger.info(
        "tool_execution",
        tool="telemetry_analyzer",
        status="complete",
        dataset=primary_service,
        anomaly_count=sum(len(v) for v in anomalies_by_service.values()),
        severity_hint=severity_hint.value if severity_hint else None,
    )

    return ToolResult(
        tool_name="telemetry_analyzer",
        findings=findings,
        severity_hint=severity_hint,
    )


async def analyze_telemetry(incident_text: str) -> ToolResult:
    """Analyze mock observability data for metrics spikes and anomalies.

    Correlates the incident description against pre-loaded mock telemetry
    datasets (metrics + structured logs) to surface anomalies and suggest
    a severity hint.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_analysis, incident_text)
