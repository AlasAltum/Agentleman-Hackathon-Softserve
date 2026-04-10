"""
Business Impact analyzer.

Calculates the three impact categories defined in the project spec:
  1. Direct Financial Loss  (RPM loss, CR delta, AOV risk)
  2. Customer Experience Degradation  (users affected, CIS score)
  3. Operational Costs  (MTTR engineer cost)

All monetary figures are estimates derived from mock business constants and
information extracted from the incident text (latency numbers, service names,
downtime clues).
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timezone

from src.utils.logger import logger
from src.workflow.models import Severity, ToolResult
from src.workflow.tools.mock_data.business_metrics import (
    AOV_RISK_SEVERITY_THRESHOLD_USD,
    AVG_ORDER_VALUE_USD,
    CONVERSION_RATE_BASELINE_PCT,
    CR_DROP_FLOOR,
    CR_DROP_PER_100MS,
    DEFAULT_BASELINE_LATENCY_MS,
    DEFAULT_INCIDENT_DURATION_MIN,
    ENGINEER_HOURLY_RATE_USD,
    ENGINEERS_BY_SEVERITY,
    FUNCTION_CRITICALITY,
    HOURLY_TRAFFIC_FACTORS,
    HOURLY_VISITORS,
    ORDERS_PER_MINUTE_BASELINE,
    RPM_BASELINE_USD,
)

# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# Patterns to pull latency values from free text.
# Captures pairs like "from 45ms to 3200ms" or single values like "3200ms".
_RE_LATENCY_RANGE = re.compile(
    r"(?:from\s+)?(\d+(?:\.\d+)?)\s*ms\s+to\s+(\d+(?:\.\d+)?)\s*ms",
    re.IGNORECASE,
)
_RE_LATENCY_SINGLE = re.compile(
    r"(?:latency|p99|response\s*time|timeout)[^\d]*(\d+(?:\.\d+)?)\s*ms",
    re.IGNORECASE,
)
_RE_DOWNTIME = re.compile(
    r"(\d+(?:\.\d+)?)\s*(minute|min|hour|hr|second|sec)s?\b",
    re.IGNORECASE,
)


def _extract_latency_delta(text: str) -> tuple[float, float] | None:
    """Return (baseline_ms, current_ms) or None if not found."""
    m = _RE_LATENCY_RANGE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _RE_LATENCY_SINGLE.search(text)
    if m:
        return DEFAULT_BASELINE_LATENCY_MS, float(m.group(1))
    return None


def _extract_downtime_minutes(text: str) -> float:
    """Return the first explicit duration found in the text, in minutes."""
    for m in _RE_DOWNTIME.finditer(text):
        value = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            return value * 60.0
        if unit.startswith("sec"):
            return value / 60.0
        return value  # minutes
    return DEFAULT_INCIDENT_DURATION_MIN


def _detect_affected_function(text: str) -> tuple[str, float]:
    """Return (function_name, criticality_score) for the most critical match."""
    lower = text.lower()
    best_fn, best_score = "default", FUNCTION_CRITICALITY["default"]
    for fn, score in FUNCTION_CRITICALITY.items():
        if fn == "default":
            continue
        if fn in lower and score > best_score:
            best_fn, best_score = fn, score
    return best_fn, best_score


# ---------------------------------------------------------------------------
# RPM model
# ---------------------------------------------------------------------------

def _compute_rpm_at_current_hour() -> float:
    """Scale RPM_BASELINE by the sine-based traffic factor for the current UTC hour."""
    hour = datetime.now(tz=timezone.utc).hour
    return RPM_BASELINE_USD * HOURLY_TRAFFIC_FACTORS[hour]


# ---------------------------------------------------------------------------
# Category 1: Direct Financial Loss
# ---------------------------------------------------------------------------

def _compute_cr_delta(baseline_ms: float, current_ms: float) -> float:
    """Return the absolute CR drop as a fraction (0.0 – CR_DROP_FLOOR)."""
    delta_ms = max(0.0, current_ms - baseline_ms)
    drop_fraction = (delta_ms / 100.0) * CR_DROP_PER_100MS
    return min(drop_fraction, CR_DROP_FLOOR)


def _compute_financial_loss(
    rpm: float,
    downtime_min: float,
    cr_drop_fraction: float,
    aov: float,
    orders_baseline_per_min: float,
) -> dict[str, float]:
    """Return a dict with all direct financial loss components."""
    rpm_loss = rpm * downtime_min * cr_drop_fraction
    orders_lost = orders_baseline_per_min * downtime_min * cr_drop_fraction
    aov_risk = orders_lost * aov
    return {
        "rpm_current": rpm,
        "rpm_loss_total": rpm_loss,
        "cr_drop_pct": cr_drop_fraction * 100.0,
        "orders_lost": orders_lost,
        "aov_risk_usd": aov_risk,
        "total_direct_loss_usd": rpm_loss + aov_risk,
    }


# ---------------------------------------------------------------------------
# Category 2: Customer Experience Degradation
# ---------------------------------------------------------------------------

def _compute_customer_impact(
    downtime_min: float,
    function_criticality: float,
) -> dict[str, float]:
    """Return users affected and Customer Impact Score (CIS, 0-100)."""
    visitors_per_min = HOURLY_VISITORS / 60.0
    users_affected = int(visitors_per_min * downtime_min)
    # CIS: logarithmic scale on users, scaled by criticality
    cis_raw = math.log10(max(users_affected, 1)) / math.log10(HOURLY_VISITORS) * 100
    cis = round(min(cis_raw * function_criticality * 1.5, 100.0), 1)
    return {
        "users_affected": users_affected,
        "cis_score": cis,
    }


# ---------------------------------------------------------------------------
# Category 3: Operational Cost (MTTR)
# ---------------------------------------------------------------------------

def _compute_mttr_cost(severity_hint: Severity | None, downtime_min: float) -> dict[str, float]:
    """Return engineer cost estimate based on severity and duration."""
    sev_key = severity_hint.value if severity_hint else "medium"
    engineers = ENGINEERS_BY_SEVERITY.get(sev_key, 1)
    duration_hours = downtime_min / 60.0
    cost = engineers * ENGINEER_HOURLY_RATE_USD * duration_hours
    return {
        "engineers": engineers,
        "duration_hours": duration_hours,
        "engineer_cost_usd": cost,
    }


# ---------------------------------------------------------------------------
# Severity determination from business metrics
# ---------------------------------------------------------------------------

def _determine_severity(financial: dict, customer: dict) -> Severity:
    total_loss = financial["total_direct_loss_usd"]
    cr_drop = financial["cr_drop_pct"]
    cis = customer["cis_score"]

    if total_loss > AOV_RISK_SEVERITY_THRESHOLD_USD or cr_drop > 30.0 or cis >= 80:
        return Severity.CRITICAL
    if total_loss > AOV_RISK_SEVERITY_THRESHOLD_USD * 0.4 or cr_drop > 15.0 or cis >= 50:
        return Severity.HIGH
    if cr_drop > 5.0 or cis >= 25:
        return Severity.MEDIUM
    return Severity.LOW


# ---------------------------------------------------------------------------
# Findings formatter
# ---------------------------------------------------------------------------

def _format_findings(
    affected_fn: str,
    downtime_min: float,
    latency_pair: tuple[float, float] | None,
    financial: dict,
    customer: dict,
    mttr: dict,
    severity: Severity,
) -> str:
    cr_baseline = CONVERSION_RATE_BASELINE_PCT
    cr_current = cr_baseline * (1.0 - financial["cr_drop_pct"] / 100.0)

    lines: list[str] = [
        "Business Impact Assessment",
        "=" * 42,
        "",
        "1. Direct Financial Loss",
        f"   Revenue rate (current):  ${financial['rpm_current']:,.0f}/min",
        f"   Revenue loss (estimated): ${financial['rpm_loss_total']:,.0f} over {downtime_min:.0f} min",
    ]

    if latency_pair:
        baseline_ms, current_ms = latency_pair
        lines.append(
            f"   Latency delta:           +{current_ms - baseline_ms:.0f}ms "
            f"({baseline_ms:.0f}ms → {current_ms:.0f}ms)"
        )

    lines += [
        f"   Conversion rate drop:     {financial['cr_drop_pct']:.1f}%"
        f" ({cr_baseline:.1f}% → {cr_current:.1f}%)",
        f"   Orders lost (estimate):   {financial['orders_lost']:.1f} × ${AVG_ORDER_VALUE_USD} AOV"
        f" = ${financial['aov_risk_usd']:,.0f}",
        f"   Total direct loss:        ${financial['total_direct_loss_usd']:,.0f}",
        "",
        "2. Customer Experience Degradation",
        f"   Active users affected:    ~{customer['users_affected']:,}",
        f"   Affected function:        {affected_fn} (criticality: {FUNCTION_CRITICALITY.get(affected_fn, 0.5):.1f}/1.0)",
        f"   Customer Impact Score:    {customer['cis_score']:.0f}/100",
        "",
        "3. Operational Cost (MTTR)",
        f"   Engineers engaged:        {mttr['engineers']}",
        f"   Incident duration:        {downtime_min:.0f} min ({mttr['duration_hours']:.2f}h)",
        f"   Engineer cost:            {mttr['engineers']} × ${ENGINEER_HOURLY_RATE_USD:.0f}/h"
        f" × {mttr['duration_hours']:.2f}h = ${mttr['engineer_cost_usd']:,.0f}",
        "",
        f"Total estimated incident cost: ${financial['total_direct_loss_usd'] + mttr['engineer_cost_usd']:,.0f}",
        f"Overall severity hint: {severity.value.upper()}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core sync analysis
# ---------------------------------------------------------------------------

def _run_analysis(incident_text: str) -> ToolResult:
    logger.info("tool_execution", tool="business_impact", status="running")

    latency_pair = _extract_latency_delta(incident_text)
    downtime_min = _extract_downtime_minutes(incident_text)
    affected_fn, criticality = _detect_affected_function(incident_text)
    rpm = _compute_rpm_at_current_hour()

    cr_drop_fraction = (
        _compute_cr_delta(latency_pair[0], latency_pair[1])
        if latency_pair
        else 0.05  # assume 5% baseline degradation if no latency data
    )

    financial = _compute_financial_loss(
        rpm, downtime_min, cr_drop_fraction, AVG_ORDER_VALUE_USD, ORDERS_PER_MINUTE_BASELINE
    )
    customer = _compute_customer_impact(downtime_min, criticality)
    severity = _determine_severity(financial, customer)
    mttr = _compute_mttr_cost(severity, downtime_min)

    findings = _format_findings(
        affected_fn, downtime_min, latency_pair, financial, customer, mttr, severity
    )

    logger.info(
        "tool_execution",
        tool="business_impact",
        status="complete",
        affected_function=affected_fn,
        total_loss_usd=round(financial["total_direct_loss_usd"], 2),
        cis_score=customer["cis_score"],
        severity_hint=severity.value,
    )

    return ToolResult(
        tool_name="business_impact",
        findings=findings,
        severity_hint=severity,
    )


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

async def check_business_impact(incident_text: str) -> ToolResult:
    """Estimate financial and customer impact from the incident description.

    Calculates:
      1. Direct Financial Loss (RPM loss, CR delta, AOV risk)
      2. Customer Experience Degradation (users affected, CIS)
      3. Operational Costs (engineer hours × rate)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_analysis, incident_text)
