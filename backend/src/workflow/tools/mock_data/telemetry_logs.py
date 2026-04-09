"""
Mock telemetry data simulating an observability platform (Prometheus/Datadog/Grafana).

Each dataset covers one of the realistic incident scenarios used in run_workflow_mock.py.
Data is intentionally deterministic so the telemetry_analyzer can return reproducible findings.
"""

from dataclasses import dataclass, field


@dataclass
class MetricSample:
    timestamp: str       # ISO 8601
    service: str
    metric_name: str
    value: float
    labels: dict = field(default_factory=dict)


@dataclass
class LogEntry:
    timestamp: str
    service: str
    level: str           # ERROR | WARN | INFO
    message: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scenario: telemetry — CPU spike + p99 latency (api-gateway)
# ---------------------------------------------------------------------------

CPU_SPIKE_METRICS: list[MetricSample] = [
    # Baseline (before incident)
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "cpu_percent",          40.2, {"env": "prod"}),
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "memory_percent",       62.1, {"env": "prod"}),
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "p99_latency_ms",       45.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "timeout_rate_percent",  0.1, {"env": "prod"}),
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "error_rate_percent",    0.2, {"env": "prod"}),
    MetricSample("2026-04-08T14:05:00Z", "api-gateway", "requests_per_sec",    420.0, {"env": "prod"}),

    # Incident onset (14:10 UTC)
    MetricSample("2026-04-08T14:10:00Z", "api-gateway", "cpu_percent",          72.5, {"env": "prod"}),
    MetricSample("2026-04-08T14:10:00Z", "api-gateway", "memory_percent",       80.3, {"env": "prod"}),
    MetricSample("2026-04-08T14:10:00Z", "api-gateway", "p99_latency_ms",      820.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:10:00Z", "api-gateway", "timeout_rate_percent",  2.4, {"env": "prod"}),
    MetricSample("2026-04-08T14:10:00Z", "api-gateway", "error_rate_percent",    3.1, {"env": "prod"}),

    # Peak (14:15 UTC)
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "cpu_percent",          95.1, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "memory_percent",       91.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "p99_latency_ms",     3200.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "timeout_rate_percent", 12.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "error_rate_percent",   11.8, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "api-gateway", "requests_per_sec",    390.0, {"env": "prod"}),

    # Upstream services (healthy)
    MetricSample("2026-04-08T14:15:00Z", "auth-service",    "cpu_percent",       28.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "auth-service",    "p99_latency_ms",    55.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "catalog-service", "cpu_percent",       31.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:15:00Z", "catalog-service", "p99_latency_ms",    70.0, {"env": "prod"}),
]

CPU_SPIKE_LOGS: list[LogEntry] = [
    LogEntry("2026-04-08T14:10:03Z", "api-gateway", "WARN",
             "High CPU detected: 72.5% — approaching threshold",
             {"threshold": "70%", "alert": "SRE-WARN-CPU"}),
    LogEntry("2026-04-08T14:12:15Z", "api-gateway", "ERROR",
             "Request timeout after 5000ms — GET /api/products",
             {"method": "GET", "path": "/api/products", "duration_ms": 5000}),
    LogEntry("2026-04-08T14:13:22Z", "api-gateway", "ERROR",
             "Circuit breaker OPEN — downstream catalog-service unresponsive",
             {"downstream": "catalog-service", "state": "OPEN"}),
    LogEntry("2026-04-08T14:14:01Z", "api-gateway", "ERROR",
             "Request timeout after 5000ms — POST /api/checkout",
             {"method": "POST", "path": "/api/checkout", "duration_ms": 5000}),
    LogEntry("2026-04-08T14:15:00Z", "api-gateway", "ERROR",
             "SRE-ALERT: api-gateway p99 > 2000ms for 5 consecutive minutes",
             {"metric": "p99_latency_ms", "value": 3200, "threshold": 2000}),
    LogEntry("2026-04-08T14:15:30Z", "api-gateway", "ERROR",
             "Memory pressure: GC pause > 500ms, heap at 91%",
             {"gc_pause_ms": 520, "heap_percent": 91}),
]


# ---------------------------------------------------------------------------
# Scenario: alert_storm — DB connection pool exhausted (order-service)
# ---------------------------------------------------------------------------

DB_POOL_METRICS: list[MetricSample] = [
    MetricSample("2026-04-08T13:00:00Z", "order-service", "db_connections_active",  8.0, {"pool_max": "20"}),
    MetricSample("2026-04-08T13:00:00Z", "order-service", "db_query_time_p99_ms",  45.0, {"env": "prod"}),
    MetricSample("2026-04-08T13:00:00Z", "order-service", "error_rate_percent",     0.3, {"env": "prod"}),

    MetricSample("2026-04-08T13:30:00Z", "order-service", "db_connections_active", 18.0, {"pool_max": "20"}),
    MetricSample("2026-04-08T13:30:00Z", "order-service", "db_query_time_p99_ms", 320.0, {"env": "prod"}),
    MetricSample("2026-04-08T13:30:00Z", "order-service", "error_rate_percent",    4.2, {"env": "prod"}),

    MetricSample("2026-04-08T14:00:00Z", "order-service", "db_connections_active", 20.0, {"pool_max": "20"}),
    MetricSample("2026-04-08T14:00:00Z", "order-service", "db_query_time_p99_ms", 890.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "order-service", "error_rate_percent",   18.5, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "order-service", "cpu_percent",           55.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "order-service", "memory_percent",        70.2, {"env": "prod"}),
]

DB_POOL_LOGS: list[LogEntry] = [
    LogEntry("2026-04-08T13:32:10Z", "order-service", "WARN",
             "DB connection pool nearing capacity: 18/20 connections in use",
             {"active": 18, "max": 20}),
    LogEntry("2026-04-08T13:50:05Z", "order-service", "ERROR",
             "psycopg2.OperationalError: connection pool exhausted (max=20)",
             {"pool_max": 20, "wait_timeout_ms": 3000}),
    LogEntry("2026-04-08T13:52:07Z", "order-service", "ERROR",
             "psycopg2.OperationalError: connection pool exhausted (max=20)",
             {"pool_max": 20, "wait_timeout_ms": 3000}),
    LogEntry("2026-04-08T13:54:09Z", "order-service", "ERROR",
             "psycopg2.OperationalError: connection pool exhausted (max=20)",
             {"pool_max": 20, "wait_timeout_ms": 3000}),
    LogEntry("2026-04-08T14:00:00Z", "order-service", "ERROR",
             "Alert storm: same error firing every ~2min for last 60min (count=8)",
             {"alert_count": 8, "interval_sec": 120}),
]


# ---------------------------------------------------------------------------
# Scenario: default — HTTP 500 on /checkout (checkout-service)
# ---------------------------------------------------------------------------

HTTP500_METRICS: list[MetricSample] = [
    MetricSample("2026-04-08T13:50:00Z", "checkout-service", "http_5xx_rate_percent",  0.1, {"env": "prod"}),
    MetricSample("2026-04-08T13:50:00Z", "checkout-service", "p99_latency_ms",         80.0, {"env": "prod"}),
    MetricSample("2026-04-08T13:50:00Z", "checkout-service", "error_rate_percent",      0.2, {"env": "prod"}),

    MetricSample("2026-04-08T14:00:00Z", "checkout-service", "http_5xx_rate_percent", 15.2, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "checkout-service", "p99_latency_ms",        540.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "checkout-service", "error_rate_percent",    14.8, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "checkout-service", "cpu_percent",            45.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "checkout-service", "memory_percent",         58.0, {"env": "prod"}),

    MetricSample("2026-04-08T14:00:00Z", "database",         "p99_latency_ms",         42.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "database",         "cpu_percent",             22.0, {"env": "prod"}),
]

HTTP500_LOGS: list[LogEntry] = [
    LogEntry("2026-04-08T14:00:12Z", "checkout-service", "ERROR",
             "Internal Server Error — unable to serialize cart session",
             {"path": "/checkout", "session_id": "sess_4a1b2c"}),
    LogEntry("2026-04-08T14:01:05Z", "checkout-service", "ERROR",
             "Internal Server Error — unable to serialize cart session",
             {"path": "/checkout", "session_id": "sess_7d3e4f"}),
    LogEntry("2026-04-08T14:02:33Z", "checkout-service", "ERROR",
             "Redis serialization error: field 'promo_code' not JSON-serializable",
             {"field": "promo_code", "type": "PromotionObject"}),
]


# ---------------------------------------------------------------------------
# Scenario: regression — JWT 401 (auth-service)
# ---------------------------------------------------------------------------

JWT_401_METRICS: list[MetricSample] = [
    MetricSample("2026-04-08T10:00:00Z", "auth-service", "auth_error_rate_percent",  0.1, {"env": "prod"}),
    MetricSample("2026-04-08T10:00:00Z", "auth-service", "http_401_rate_percent",    0.1, {"env": "prod"}),
    MetricSample("2026-04-08T10:00:00Z", "auth-service", "ntp_drift_ms",             2.0, {"env": "prod"}),

    MetricSample("2026-04-08T14:00:00Z", "auth-service", "auth_error_rate_percent",  5.2, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "auth-service", "http_401_rate_percent",    5.1, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "auth-service", "ntp_drift_ms",           850.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "auth-service", "cpu_percent",             30.0, {"env": "prod"}),
    MetricSample("2026-04-08T14:00:00Z", "auth-service", "p99_latency_ms",          65.0, {"env": "prod"}),
]

JWT_401_LOGS: list[LogEntry] = [
    LogEntry("2026-04-08T14:00:08Z", "auth-service", "ERROR",
             "JWT validation failed: token not yet valid (nbf claim in future)",
             {"claim": "nbf", "drift_ms": 850, "user_id": "usr_00291"}),
    LogEntry("2026-04-08T14:00:09Z", "auth-service", "ERROR",
             "JWT validation failed: token not yet valid (nbf claim in future)",
             {"claim": "nbf", "drift_ms": 850, "user_id": "usr_00445"}),
    LogEntry("2026-04-08T14:01:00Z", "auth-service", "WARN",
             "NTP sync anomaly detected: clock drift 850ms above acceptable threshold (50ms)",
             {"drift_ms": 850, "threshold_ms": 50}),
]


# ---------------------------------------------------------------------------
# Registry: map service/keyword hints → dataset
# ---------------------------------------------------------------------------

# Each entry: (metrics_list, logs_list, primary_service)
TELEMETRY_DATASETS: list[tuple[list[MetricSample], list[LogEntry], str]] = [
    (CPU_SPIKE_METRICS,  CPU_SPIKE_LOGS,  "api-gateway"),
    (DB_POOL_METRICS,    DB_POOL_LOGS,    "order-service"),
    (HTTP500_METRICS,    HTTP500_LOGS,    "checkout-service"),
    (JWT_401_METRICS,    JWT_401_LOGS,    "auth-service"),
]

# Keyword → dataset index in TELEMETRY_DATASETS
KEYWORD_DATASET_INDEX: dict[str, int] = {
    # cpu spike / latency / timeout → api-gateway dataset
    "cpu":          0,
    "spike":        0,
    "latency":      0,
    "p99":          0,
    "timeout":      0,
    "api-gateway":  0,
    "memory":       0,

    # db pool / connection → order-service dataset
    "pool":         1,
    "connection":   1,
    "psycopg":      1,
    "order":        1,
    "database":     1,
    "alert storm":  1,
    "alert_storm":  1,

    # http 500 / checkout → checkout-service dataset
    "checkout":     2,
    "500":          2,
    "serialize":    2,
    "cart":         2,

    # jwt / auth → auth-service dataset
    "jwt":          3,
    "401":          3,
    "auth":         3,
    "token":        3,
    "ntp":          3,
    "nbf":          3,
}
