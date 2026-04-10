# Workflow Observability Proposal

This document explains three things:

1. What the workflow already measures today.
2. What is still missing for a strong Grafana demo.
3. The minimum code we should add to make the judges see bottlenecks, token usage, failures, blocked inputs, and agent/tool behavior clearly.

## Recommendation Summary

For the hackathon, the most pragmatic setup is:

- Keep Loki for structured logs.
- Keep MLflow for per-request traces and LLM spans.
- Add a real backend Prometheus metrics endpoint for workflow metrics.
- Instrument the workflow with counters and histograms, not only logs.

This is the fastest way to make Grafana answer the questions judges will ask:

- Where is the bottleneck?
- How many requests are blocked by guardrails?
- How many requests pass?
- Which model is slow or expensive?
- Which tool or integration fails most?
- Are retries or loops happening?

## What We Measure Right Now

### 1. Logs already available

The backend already emits structured JSON logs that Loki can ingest.

Examples already present in the code:

- Request lifecycle:
  - `ingest_started`
  - `request_completed`
  - `request_failed`
  - `workflow_completed`
  - `triage_error`
- Guardrails and safety:
  - `guardrail_blocked`
  - `guardrails_blocked_input`
  - `guardrails_flagged_input`
  - `relevance_check_blocked`
  - `relevance_check_passed`
- Workflow phases:
  - `phase_started`
  - `phase_completed`
  - `phase_failed`
- Routing and tools:
  - `tools_selected`
  - `tools_completed`
  - `router_iteration`
  - `max_iterations_reached`
  - `no_tools_to_dispatch`
- Actions and integrations:
  - `ticket_created`
  - `team_notification_dispatched`
  - `reporter_notification_dispatched`
  - `resolution_notification_dispatched`

### 2. Traces already available

The backend already uses MLflow and LlamaIndex tracing.

Current trace coverage includes:

- request correlation through `request_id`
- workflow step boundaries
- LlamaIndex autolog traces
- service spans for Jira and notifications when OpenTelemetry is available

This is already good for drill-down analysis of one incident.

### 3. Metrics already available in some service layers

Some counters and histograms already exist in Jira and notifications code.

Current examples:

- Jira:
  - `jira_http_requests_total`
  - `jira_http_failures_total`
  - `jira_http_request_duration_ms`
  - `jira_tickets_created_total`
  - `jira_tickets_resolved_total`
- Notifications:
  - `notifications_http_requests_total`
  - `notifications_http_failures_total`
  - `notifications_http_request_duration_ms`
  - `notifications_sent_total`
  - `notifications_failed_total`

### 4. Important limitations in the current state

This is the part that matters most for a Grafana demo.

- Workflow step logs exist, but many workflow phase latencies are currently logged as `0 ms`.
- Prometheus is currently configured to scrape the observability test emitter, not the backend workflow itself.
- Guardrails outcomes are visible in logs, but not yet as first-class counters and time series.
- LLM helper functions exist for tokens and tool calls, but they are not wired into the real workflow path yet.
- There is no judge-ready dashboard yet for accepted versus blocked requests, token consumption over time, or retries/loops over time.

## What Judges Will Expect To See

The judges will care less about raw log volume and more about whether the system is inspectable.

The strongest Grafana story is a dashboard with these sections.

### 1. User input and guardrails

We should show:

- total incident submissions over time
- accepted submissions over time
- blocked submissions over time
- suspicious but accepted submissions over time
- blocked file uploads by MIME type
- prompt injection, XSS, SQLi, and relevance rejections by reason

Why it matters:

- It proves the agent is protected.
- It shows the system is not blindly sending every user input to the model.

### 2. Prompt and context preparation

We should show:

- prompt version in traces or logs
- prompt size in characters or tokens
- consolidated input size
- number of retrieved candidates
- number of selected tools

Why it matters:

- It shows whether the agent is using too much context.
- It helps explain model latency and cost.

### 3. Retrieval and tool behavior

We should show:

- tool calls by tool name
- tool success versus failure rate
- tool latency by tool name
- router iterations per incident
- incidents that reached max iterations
- empty-result or no-tool paths

Why it matters:

- This is where bottlenecks and agent loops usually appear.
- It proves the system is orchestrating tools, not just calling an LLM once.

### 4. LLM performance and cost

We should show:

- LLM requests per model/provider
- prompt tokens over time
- completion tokens over time
- total tokens over time
- LLM latency by model
- estimated cost over time
- LLM failures/timeouts over time

Why it matters:

- This is one of the most judge-visible AI metrics.
- Token and latency trends are easy to explain during a demo.

### 5. Response and output quality

We should show:

- successful triage responses versus internal failures
- invalid or incomplete response formats
- severity distribution of generated triage
- resolution webhook outcomes

Why it matters:

- It proves the workflow ends in usable decisions, not just intermediate reasoning.

### 6. Actions and integrations

We should show:

- Jira ticket creation success/failure
- notification success/failure
- Jira and Nylas HTTP latency
- poller started/completed/failed counts
- webhook ignored reasons

Why it matters:

- Judges want to see that the agent can act reliably, not only reason well.

## What We Should Add Next

## Phase 1: Judge-ready minimum

This is the smallest useful observability upgrade.

Add these metrics directly from the backend workflow:

- `sre_requests_total{route, outcome}`
  - outcomes: `accepted`, `blocked`, `failed`
- `sre_guardrail_decisions_total{guardrail, outcome, threat_level}`
  - outcomes: `passed`, `flagged`, `blocked`
- `sre_workflow_phase_duration_ms{phase}` as a histogram
- `sre_workflow_phase_errors_total{phase, error_type}`
- `sre_tool_calls_total{tool, status}`
- `sre_tool_call_duration_ms{tool}` as a histogram
- `sre_workflow_iterations_total`
- `sre_workflow_max_iterations_total`

This phase gives immediate value for:

- bottlenecks
- blocked versus passed requests
- phase failures
- tool failures
- loops/retries signals

### Code impact

Estimated effort: small.

- around 1 new shared metrics module
- small edits in ingest route, guardrails engine, routing, and workflow
- around 120 to 180 lines of code

## Phase 2: LLM and prompt metrics

This phase adds the AI-specific numbers judges will ask for.

Add these metrics:

- `sre_llm_requests_total{provider, model, status}`
- `sre_llm_latency_ms{provider, model}` as a histogram
- `sre_llm_tokens_total{provider, model, token_type}`
  - token types: `prompt`, `completion`, `total`
- `sre_llm_cost_usd_total{provider, model}`
- `sre_prompt_size_chars{prompt_name}` as a histogram
- `sre_prompt_size_tokens{prompt_name}` as a histogram
- `sre_context_candidates_count`

This phase gives immediate value for:

- total token consumption over time
- model latency by model/provider
- cost visibility
- context growth problems

### Code impact

Estimated effort: medium.

- wire the existing LLM helper functions into real calls
- extract token usage from LlamaIndex or provider responses
- add lightweight cost mapping per model
- around 120 to 220 additional lines of code

## Phase 3: Stronger response-quality signals

This phase is optional for the hackathon, but useful if time allows.

Add these metrics:

- `sre_triage_outputs_total{status, severity}`
- `sre_resolution_events_total{status}`
- `sre_webhook_ignored_total{reason}`
- `sre_notifications_total{audience, status}`
- `sre_ticket_actions_total{operation, status}`

Possible quality checks:

- missing severity
- empty technical summary
- malformed ticket body
- missing reporter email on resolution path

### Code impact

Estimated effort: small to medium.

- around 80 to 150 additional lines of code

## Recommended Implementation Approach

For this repository, the simplest path is:

1. Keep logs in Loki.
2. Keep traces in MLflow.
3. Add a FastAPI `/metrics` endpoint using `prometheus-client`.
4. Standardize workflow metrics in one shared module.

This is better for the hackathon than building a more complex exporter path first.

Why:

- Prometheus already exists in the stack.
- `prometheus-client` is already a dependency.
- The backend does not currently expose a metrics endpoint.
- The current Prometheus scrape config points to the test emitter, not the real workflow backend.

## Important Design Rule

Do not use `request_id` as a Prometheus metric label.

Use:

- metrics for counts, rates, latency distributions, and totals over time
- logs and MLflow traces for per-request drill-down

High-cardinality labels will make the metrics much harder to query and explain.

## Concise Examples

### Example metric names

```text
sre_requests_total{route="/api/ingest", outcome="accepted"}
sre_guardrail_decisions_total{guardrail="PromptInjectionGuardrail", outcome="blocked", threat_level="malicious"}
sre_workflow_phase_duration_ms{phase="dispatch_tools"}
sre_tool_calls_total{tool="telemetry_analyzer", status="success"}
sre_llm_tokens_total{provider="openai", model="gpt-4o", token_type="total"}
sre_llm_cost_usd_total{provider="openai", model="gpt-4o"}
```

### Example instrumentation shape

```python
REQUESTS.labels(route="/api/ingest", outcome="accepted").inc()
GUARDRAIL_DECISIONS.labels(
    guardrail="PromptInjectionGuardrail",
    outcome="blocked",
    threat_level="malicious",
).inc()

with WORKFLOW_PHASE_LATENCY.labels(phase="retrieve").time():
    candidates = await retrieve_candidates(preprocessed)
```

### Example PromQL panels

Blocked versus accepted requests:

```promql
sum by (outcome) (rate(sre_requests_total[5m]))
```

P95 phase latency:

```promql
histogram_quantile(
  0.95,
  sum by (le, phase) (rate(sre_workflow_phase_duration_ms_bucket[5m]))
)
```

Tool failures over time:

```promql
sum by (tool, status) (rate(sre_tool_calls_total[10m]))
```

Total token consumption over time:

```promql
sum by (model) (rate(sre_llm_tokens_total{token_type="total"}[5m]))
```

Estimated cost over time:

```promql
sum(rate(sre_llm_cost_usd_total[15m]))
```

## What Is Already Strong Enough For The Demo

These parts are already useful:

- structured logs with request correlation
- MLflow trace correlation with `request_id`
- service observability for Jira and notifications
- request-level HTTP latency logs
- guardrail block/flag events in logs

## What Is Not Strong Enough Yet

These parts should be improved before presenting Grafana as the main observability surface:

- real workflow phase latency metrics
- backend Prometheus scraping
- guardrail counters over time
- LLM token totals over time
- tool call counts and failures over time
- explicit retry/loop metrics

## Suggested Delivery Order

If time is limited, implement in this order:

1. backend `/metrics` endpoint
2. request, guardrail, workflow phase, and tool metrics
3. real phase latency instead of `0 ms`
4. LLM tokens, latency, and estimated cost
5. webhook, poller, ticket, and notification outcome panels

That order gives the best judge-facing result for the least code.