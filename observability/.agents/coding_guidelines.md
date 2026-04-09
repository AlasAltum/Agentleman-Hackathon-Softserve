# Observability Coding Guidelines

Use this file when implementing observability for the backend AI workflow and the local observability stack under `/observability`.

## 1. Scope

These guidelines apply to:
- the FastAPI backend in `/backend`
- the internal agent workflow coordinated by the backend
- local observability services run with Docker
- logs, metrics, and traces generated during the incident lifecycle

The default assumption is that observability starts at the first backend request and follows the workflow through:
- ingest
- guardrails
- preprocess
- retrieve
- rerank
- classify
- llm
- tool
- ticket
- notify
- resolve
- feedback

## 2. Primary Goals

Observability must make it easy to answer the following:
- which phase is slow
- which phase consumes the most tokens
- which tool or integration is failing
- whether retries or loops are occurring
- what the current throughput is
- how a single incident moved through the full workflow

## 3. Required Local Stack

The local observability stack must run through Docker.

Required components:
- Grafana for dashboards and exploration
- Prometheus for metrics scraping and querying
- Loki for log storage and querying
- Grafana Alloy for shipping logs into Loki
- MLflow for workflow traces and execution trees

Rules:
- Keep observability configuration under `/observability`.
- Use persistent Docker volumes for local state where appropriate.
- Expose only the ports required for local development and demo usage.
- Prefer one reproducible Docker Compose setup over ad hoc local services.

## 4. Core Rules

### 4.1 Correlation

- Generate one `request_id` at the first backend entry point.
- The `request_id` must be UUIDv7.
- Reuse the same `request_id` across the entire workflow.
- Include `request_id` in logs and traces.
- Do not use `request_id` as a Prometheus label.

### 4.2 Phase-Oriented Telemetry

- Every meaningful workflow step must have a stable phase name.
- Every phase must emit logs, metrics, and a trace span.
- Every phase should report status using a small bounded vocabulary such as `started`, `success`, `error`, `retry`, or `timeout`.

### 4.3 Safety and Privacy

- Never log secrets, API keys, tokens, or credentials.
- Never expose personally identifiable data unless it is explicitly needed and approved.
- Prefer logging summaries, counts, identifiers, and statuses over raw payloads.
- If prompt content is sensitive, log prompt version and token counts rather than the full prompt body.

### 4.4 Low Cardinality Metrics

- Prometheus labels must stay low-cardinality.
- Do not use user emails, raw file names, ticket IDs, stack traces, or `request_id` as metric labels.
- Use bounded labels such as `phase`, `status`, `provider`, `model`, `channel`, or `tool_name` only when the set of values is small and stable.

## 5. Structured Logging With `structlog`

Use `structlog` for JSON logs.

Rules:
- Emit logs to standard output.
- Prefer structured key-value fields over interpolated strings.
- Bind request context once, then reuse it throughout the request lifecycle.
- Use consistent event names such as `phase_started`, `phase_completed`, and `phase_failed`.
- Include `exc_info=True` when logging exceptions.

Recommended common log fields:
- `request_id`
- `phase`
- `status`
- `service`
- `component`
- `tool_name`
- `provider`
- `model`
- `latency_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `retry_count`
- `error_type`

Example `structlog` setup:

```python
import logging
import sys

import structlog


def configure_logging() -> None:
	logging.basicConfig(
		format="%(message)s",
		stream=sys.stdout,
		level=logging.INFO,
	)

	structlog.configure(
		processors=[
			structlog.contextvars.merge_contextvars,
			structlog.processors.add_log_level,
			structlog.processors.TimeStamper(fmt="iso", utc=True),
			structlog.processors.JSONRenderer(),
		],
		logger_factory=structlog.PrintLoggerFactory(),
		cache_logger_on_first_use=True,
	)
```

Example request context binding in FastAPI middleware:

```python
import structlog
from starlette.middleware.base import BaseHTTPMiddleware


def generate_request_id() -> str:
	"""Return a UUIDv7 string using the project's chosen UUIDv7 implementation."""
	raise NotImplementedError


class RequestContextMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request, call_next):
		request_id = request.headers.get("X-Request-ID") or generate_request_id()

		structlog.contextvars.clear_contextvars()
		structlog.contextvars.bind_contextvars(
			request_id=request_id,
			service="backend",
			component="fastapi",
			path=request.url.path,
			method=request.method,
		)

		response = await call_next(request)
		response.headers["X-Request-ID"] = request_id
		return response
```

Example phase logging:

```python
import structlog


logger = structlog.get_logger(__name__)


def log_phase_start(phase: str) -> None:
	logger.info("phase_started", phase=phase, status="started")


def log_phase_success(phase: str, latency_ms: int) -> None:
	logger.info(
		"phase_completed",
		phase=phase,
		status="success",
		latency_ms=latency_ms,
	)


def log_phase_failure(phase: str, error_type: str) -> None:
	logger.error(
		"phase_failed",
		phase=phase,
		status="error",
		error_type=error_type,
		exc_info=True,
	)
```

## 6. How Logs Reach Loki

Preferred local pattern:
1. Python writes structured JSON logs to standard output with `structlog`.
2. Docker captures container output.
3. Grafana Alloy reads Docker logs.
4. Grafana Alloy ships those logs to Loki.
5. Grafana queries Loki for exploration and dashboards.

Rules:
- Do not push logs directly from business code to Loki by default.
- Prefer stdout plus Alloy because it is simpler, local-friendly, and easier to debug.
- Make sure logs include the fields needed for filtering, especially `request_id`, `phase`, and `status`.

Recommended Loki query examples for later documentation:
- filter by request: `{service="backend"} |= "<request_id>"`
- filter by phase: `{service="backend"} |= "\"phase\":\"classify\""`
- filter errors only: `{service="backend"} |= "\"status\":\"error\""`

## 7. Metrics With Prometheus

Prometheus is for metrics, not logs.

Rules:
- Use a Python Prometheus client library in the backend.
- Expose a `/metrics` endpoint for Prometheus to scrape.
- Use counters for totals, histograms for duration, and gauges only when a current value is truly needed.
- Track token usage by phase.
- Keep label sets small and stable.

Preferred metric categories:
- request totals
- phase duration
- LLM request totals
- LLM token totals
- LLM cost totals
- tool call totals
- tool failure totals
- notification totals
- ticket operation totals

Suggested metric names:
- `sre_requests_total`
- `sre_phase_duration_seconds`
- `sre_llm_requests_total`
- `sre_llm_tokens_total`
- `sre_llm_cost_usd_total`
- `sre_tool_calls_total`
- `sre_tool_failures_total`
- `sre_notification_total`
- `sre_ticket_operations_total`

Example metric definitions:

```python
from prometheus_client import Counter, Histogram


REQUESTS_TOTAL = Counter(
	"sre_requests_total",
	"Total backend requests handled by the incident workflow.",
	["phase", "status"],
)

PHASE_DURATION_SECONDS = Histogram(
	"sre_phase_duration_seconds",
	"Duration of workflow phases in seconds.",
	["phase", "status"],
)

LLM_TOKENS_TOTAL = Counter(
	"sre_llm_tokens_total",
	"LLM token usage grouped by phase and token type.",
	["phase", "model", "token_type"],
)
```

Example metrics endpoint in FastAPI:

```python
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


metrics_router = APIRouter()


@metrics_router.get("/metrics")
def metrics() -> Response:
	return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Important clarification:
- `structlog` does not send data to Prometheus.
- Prometheus scrapes metrics from an HTTP endpoint.
- Logs and metrics complement each other, but they are emitted differently.

## 8. Traces With MLflow

Use MLflow traces to represent the execution tree of the agentic workflow.

Rules:
- Create one root trace per request.
- Create a child span for each workflow phase.
- Create separate spans for important LLM calls, tool calls, and external integrations.
- Attach non-sensitive metadata such as `request_id`, `phase`, `model`, `tool_name`, `status`, and latency.
- Record token usage and cost metadata at the LLM call level when available.

Implementation guidance:
- Wrap phase boundaries in reusable tracing helpers.
- Keep span names stable and predictable.
- Do not dump full secrets or unsafe raw payloads into trace metadata.

## 9. FastAPI Integration Expectations

The backend is the main orchestration layer, so observability must start there.

Required backend instrumentation:
- request middleware for `request_id`
- request and response logging
- latency tracking for the full request
- per-phase instrumentation inside the workflow
- token accounting around LLM calls
- success and failure metrics around tools and integrations
- trace spans that mirror the workflow structure

When background tasks or async tasks continue after the initial request scope, they must receive the correlation context explicitly.

## 10. Canonical Fields and Labels

Prefer these canonical values when possible.

Phase names:
- `ingest`
- `guardrails`
- `preprocess`
- `retrieve`
- `rerank`
- `classify`
- `llm`
- `tool`
- `ticket`
- `notify`
- `resolve`
- `feedback`

Status values:
- `started`
- `success`
- `error`
- `retry`
- `timeout`

Bounded metric labels:
- `phase`
- `status`
- `provider`
- `model`
- `tool_name`
- `channel`

Forbidden high-cardinality metric labels:
- `request_id`
- `ticket_id`
- `email`
- `file_name`
- `raw_prompt`
- `stack_trace`

## 11. Local Validation Checklist

When the observability stack is implemented, validate it with these checks:
- Grafana can connect to Prometheus and Loki.
- Prometheus can scrape the backend `/metrics` endpoint.
- Loki receives structured logs from backend containers through Alloy.
- MLflow shows traces for one sample request.
- One test incident produces correlated logs, metrics, and traces.
- Token usage is visible by phase.
- Latency and failure hotspots are visible by phase.

## 12. Testing Expectations

Create a dedicated local test area under `/observability/test` for simple validation scripts.

Planned examples:
- `emit_logs.py`
- `emit_metrics.py`
- `emit_traces.py`
- `simulate_incident_flow.py`

The purpose of these scripts is to verify the observability stack independently from the whole application.
