"""
Mock business constants for the e-commerce platform.

These simulate data that would normally come from a business analytics DB.
Used by business_impact.py to calculate the three impact categories:
  1. Direct Financial Loss
  2. Customer Experience Degradation
  3. Operational Costs (MTTR)
"""

# ---------------------------------------------------------------------------
# Global e-commerce constants
# ---------------------------------------------------------------------------

# Revenue per minute at peak hour (used as baseline; actual value is modulated
# by a sine wave over the day in _compute_rpm_at_current_hour)
RPM_BASELINE_USD: float = 1_800.0

# Average hourly unique visitors across all traffic
HOURLY_VISITORS: int = 12_000

# Average order value (AOV) in USD
AVG_ORDER_VALUE_USD: float = 127.50

# Baseline orders per minute at peak hour
ORDERS_PER_MINUTE_BASELINE: float = 14.2

# Baseline conversion rate (visitors → completed purchase) at peak hour
CONVERSION_RATE_BASELINE_PCT: float = 3.2

# ---------------------------------------------------------------------------
# Latency → Conversion Rate impact model
# Based on industry research: each 100ms of added latency reduces CR by ~1%,
# with a floor at -50% total drop. Reference: Amazon/Akamai latency studies.
# ---------------------------------------------------------------------------

# CR drop per 100ms of additional latency (as a fraction of baseline CR)
CR_DROP_PER_100MS: float = 0.01   # 1% relative drop per 100ms
CR_DROP_FLOOR: float = 0.50       # Maximum CR drop: 50%

# Default assumed baseline latency when only current latency is reported
DEFAULT_BASELINE_LATENCY_MS: float = 100.0

# ---------------------------------------------------------------------------
# Operational cost constants
# ---------------------------------------------------------------------------

# Fully-loaded hourly rate for a senior SRE engineer (USD)
ENGINEER_HOURLY_RATE_USD: float = 150.0

# Number of engineers typically engaged per severity level
ENGINEERS_BY_SEVERITY: dict[str, int] = {
    "critical": 3,
    "high": 2,
    "medium": 1,
    "low": 1,
}

# Default incident duration assumption when not derivable from text (minutes)
DEFAULT_INCIDENT_DURATION_MIN: float = 15.0

# ---------------------------------------------------------------------------
# Function criticality scores (0.0 – 1.0)
# Used to weight the Customer Impact Score (CIS).
# 1.0 = complete inability to purchase; 0.1 = minor inconvenience.
# ---------------------------------------------------------------------------

FUNCTION_CRITICALITY: dict[str, float] = {
    "payment":     1.0,
    "checkout":    1.0,
    "order":       0.9,
    "cart":        0.6,
    "auth":        0.7,
    "login":       0.7,
    "api-gateway": 0.8,
    "search":      0.3,
    "catalog":     0.3,
    "image":       0.2,
    "database":    0.9,
    "db":          0.9,
    "default":     0.5,
}

# ---------------------------------------------------------------------------
# Traffic shape: fraction of peak traffic by hour-of-day (UTC)
# Modelled as a sine curve; peaks around 14:00 UTC (business hours).
# Index = UTC hour (0-23).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Severity thresholds for business impact
# ---------------------------------------------------------------------------

# Total direct loss (USD) above which the incident is considered CRITICAL
AOV_RISK_SEVERITY_THRESHOLD_USD: float = 10_000.0

# ---------------------------------------------------------------------------
# Traffic shape
# ---------------------------------------------------------------------------

import math as _math

HOURLY_TRAFFIC_FACTORS: list[float] = [
    round(max(0.15, 0.6 + 0.4 * _math.sin(_math.pi * (h - 6) / 14)), 3)
    for h in range(24)
]
