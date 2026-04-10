# Backend — SRE Incident Intake & Triage Agent

FastAPI + LlamaIndex event-driven backend that ingests incident reports, triages them automatically using an LLM-powered workflow, creates Jira tickets, and notifies the team.

---

## How it works

The backend exposes two main endpoints:

- **`POST /api/ingest`** — receives an incident report (text + optional files), runs guardrails, and dispatches a background triage workflow that classifies the incident, creates a Jira ticket, and alerts the team.
- **`POST /api/webhook/jira/resolved`** — called by Jira when a ticket is resolved; notifies the original reporter and saves the RCA back into the vector store for future retrieval.

The triage workflow runs as a 6-step LlamaIndex event-driven pipeline:

1. **Retrieve candidates** — vector search against local Qdrant (Top-K historical incidents)
2. **Rerank** — Cohere semantic reranker narrows to Top-3; falls back to similarity sort if unavailable
3. **Classify** — LLM cluster + time judge produces one of three types:
   - *Alert Storm* — high similarity + < 24 h → update existing ticket, escalate urgency
   - *Historical Regression* — high similarity + > 24 h → surface past RCA as suggestion
   - *New Incident* — no match → full deep triage
4. **Router** — LLM selects which expert tools to run
5. **Tool dispatch** — parallel execution of `codebase_analyzer`, `telemetry_analyzer`, `business_impact`
6. **Ticket + notify** — creates or updates Jira ticket, sends Slack and email alerts

---

## Project structure

```
backend/
├── src/
│   ├── api/
│   │   ├── entrypoint.py          # FastAPI app, middleware
│   │   └── routes/
│   │       └── incident_routes.py # POST /api/ingest, POST /api/webhook/jira/resolved
│   ├── workflow/
│   │   ├── sre_workflow.py        # LlamaIndex Workflow — 6 steps
│   │   ├── events.py              # Typed workflow events
│   │   ├── models.py              # Pydantic models (IncidentInput, TriageResult…)
│   │   ├── phases/
│   │   │   ├── classification.py  # retrieve_candidates, rerank_candidates, classify_incident
│   │   │   ├── preprocessing.py   # File routing + text extraction
│   │   │   ├── resolution.py      # Webhook resolution handler
│   │   │   ├── routing.py         # LLM router + tool dispatch
│   │   │   └── ticketing.py       # Jira ticket creation/update + notifications
│   │   └── tools/
│   │       ├── codebase_analyzer.py
│   │       ├── telemetry_analyzer.py
│   │       └── business_impact.py
│   ├── guardrails/
│   │   ├── base.py                # BaseGuardrail ABC
│   │   ├── input_guardrails.py    # Pattern-based guardrail engine
│   │   ├── relevance_guardrail.py # LLM relevance check
│   │   └── validators.py          # MIME type + magic bytes validators
│   ├── integrations/
│   │   ├── qdrant_store.py        # Vector store read/write
│   │   ├── ticketing.py           # Jira client wrapper
│   │   └── notifications.py       # Slack + email
│   ├── services/
│   │   ├── jira/                  # Jira bridge + observability
│   │   └── notifications/         # Notification bridge
│   ├── utils/
│   │   ├── logger.py              # structlog structured logging
│   │   ├── tracing.py             # MLflow autolog configuration
│   │   └── setup.py               # LlamaIndex global defaults
│   └── qdrant_setup/
│       └── setup.py               # Collection creation + index setup
├── tests/
├── docker-compose.yml             # PostgreSQL + Qdrant + app
└── pyproject.toml
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/ingest` | Submit an incident report |
| `POST` | `/api/webhook/jira/resolved` | Jira resolution webhook |
| `GET`  | `/health` | Health check |

### POST /api/ingest

Multipart form fields:

| Field | Type | Required |
|-------|------|----------|
| `text_desc` | string (max 10,000 chars) | yes |
| `reporter_email` | string | yes |
| `file_attachments` | files (max 5) | no |

Returns `202 Accepted` immediately. The triage workflow runs in the background.

```json
{
  "status": "accepted",
  "message": "Incident report received. Triage workflow is running in the background.",
  "request_id": "01JXXXXXXXXXXXXXXXXX"
}
```

---

## Observability

- **Structured logs** — `structlog` JSON output; every request tagged with `request_id`
- **MLflow tracing** — LlamaIndex autolog traces every workflow run; view at `http://localhost:5000`
- **Prometheus metrics** — exposed at `/metrics`
- **Request ID** — propagated via `X-Request-ID` header and embedded in the Jira ticket description so the resolution webhook can correlate back to the original request

---

## Guardrails

1. **File validation** — MIME allow-list + magic-byte verification
2. **Pattern guardrails** — regex-based detection of prompt injection and malicious payloads (`MALICIOUS` → HTTP 400, `SUSPICIOUS` → flagged and continues)
3. **LLM relevance check** — rejects off-topic inputs before the workflow starts (HTTP 422)
