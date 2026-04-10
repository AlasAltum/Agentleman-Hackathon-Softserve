# AGENTS_USE.md

## 1. Agent Overview

**Agent Name:** Agentleman  
**Purpose:** Agentleman is an SRE incident intake and triage agent for our e-commerce application. It accepts multimodal incident reports, validates and preprocesses them, retrieves similar incidents from Qdrant, runs structured triage with LLM reasoning and tool calls, creates a Jira ticket, notifies the engineering team, and sends a resolution email back to the original reporter when the ticket is closed.  
**Tech Stack:** Python, FastAPI, LlamaIndex Workflows, Qdrant, MLflow, Grafana, Loki, Prometheus, Jira Cloud, Nylas email, Docker Compose, configurable LLM providers including Google Gemini, OpenRouter, OpenAI, Anthropic, and Ollama.

---

## 2. Agents & Capabilities

This is a single-agent architecture with one orchestrating agent and several internal tools.

### Agent: Agentleman

| Field | Description |
|-------|-------------|
| **Role** | End-to-end incident triage and routing agent |
| **Type** | Semi-autonomous |
| **LLM** | Configurable via environment; supports Gemini, OpenRouter, OpenAI, Anthropic, and Ollama |
| **Inputs** | Text description, reporter email, image attachments, log/text attachments, retrieved incident context, e-commerce codebase context |
| **Outputs** | Classification, severity, technical summary, Jira ticket, team notification, reporter acknowledgement, reporter resolution email |
| **Tools** | Qdrant retrieval, reranking, business impact tool, telemetry analyzer, codebase analyzer, Jira adapter, notification bridge, observability stack |

---

## 3. Architecture & Orchestration

- **Architecture diagram:** `submit -> preprocess -> guardrails -> retrieve -> rerank -> classify -> tools -> ticket -> notify -> resolved webhook -> reporter notify`
- **Orchestration approach:** Event-driven workflow using `LlamaIndex Workflow` in `backend/src/workflow/sre_workflow.py`.
- **State management:** Request-scoped workflow context in memory plus shared external systems: Qdrant for retrieval, Jira for ticket state, and observability services for logs/traces/metrics.
- **Error handling:** Invalid files and malicious inputs are rejected early. Retrieval and reranking degrade gracefully. Notification and ticketing failures are logged with structured events.
- **Handoff logic:** Single-agent system. Internal phases pass structured models such as `PreprocessedIncident`, `ClassificationResult`, `TriageResult`, and `ResolutionPayload` between steps.

---

## 4. Context Engineering

- **Context sources:** User text, extracted file content, historical incidents from Qdrant, tool outputs, and the e-commerce codebase when the incident suggests a code or regression issue.
- **Context strategy:** Preprocess and consolidate attachments first, then use retrieval plus reranking before classification and tool dispatch.
- **Token management:** Inputs are trimmed and summarized before LLM use; tool findings and prompt inputs are capped to keep prompts bounded.
- **Grounding:** The workflow grounds outputs in retrieved incidents, validated attachments, tool results, and the original incident report. Jira ticket content is based on the reported incident data rather than free-form agent narrative.

---

## 5. Use Cases

### Use Case 1: Multimodal incident triage

- **Trigger:** An engineer or customer submits a report with text plus an image or log file.
- **Steps:** `/api/ingest` accepts the form, extracts attachment content, runs MIME and threat validation, performs relevance checking, dispatches the workflow, retrieves similar incidents, classifies the issue, runs tools, creates a Jira ticket, and notifies the engineering team.
- **Expected outcome:** A triaged incident with classification, severity, Jira ticket, and notification fan-out.

### Use Case 2: Resolution loop

- **Trigger:** A Jira issue created by the agent is moved to a resolved state.
- **Steps:** The Jira webhook hits `/api/webhook/jira/resolved`, the backend validates the transition, projects it into a `ResolutionPayload`, records the resolution event, and sends the reporter a resolution email.
- **Expected outcome:** The original reporter is notified that the incident has been resolved.

---

## 6. Observability

- **Logging:** Structured JSON logs via `structlog`. Main events include `ingest_started`, `preprocessing_complete`, `workflow_dispatched`, `ticket_created`, `team_notification_dispatched`, and `resolution_notification_dispatched`.
- **Tracing:** End-to-end workflow tracing through MLflow with request correlation and LlamaIndex autologging.
- **Metrics:** Prometheus-compatible service instrumentation around Jira and notifications, plus workflow-stage visibility through the observability stack.
- **Dashboards:** Grafana dashboards backed by Loki, Prometheus, and MLflow.

### Evidence

- Logs: `docker compose logs hackaton-backend | grep request_id`
- Traces: MLflow at `http://localhost:5001`
- Dashboards: Grafana at `http://localhost:3000`
- Code paths: `backend/src/api/routes/incident_routes.py`, `backend/src/workflow/sre_workflow.py`, `backend/src/services/jira/observability.py`, `backend/src/services/notifications/observability.py`

---

## 7. Security & Guardrails

- **Prompt injection defense:** `GuardrailsEngine` blocks known prompt-injection, XSS, and SQL injection patterns before workflow execution.
- **Input validation:** `ContentTypeGuardrail` validates attachment MIME types; preprocessing blocks unsupported or dangerous file extensions.
- **Tool use safety:** The workflow only calls bounded internal tools and adapters. Ticketing and notifications go through explicit Jira and notification bridge functions rather than arbitrary command execution.
- **Data handling:** Secrets come from `.env`; request correlation and logs avoid exposing credentials; external integrations are isolated behind adapters.

### Evidence

- Guardrail code: `backend/src/guardrails/validators.py`, `backend/src/guardrails/input_guardrails.py`, `backend/src/guardrails/relevance_guardrail.py`
- Endpoint tests: `backend/tests/test_ingest_endpoint.py`
- Notification tests: `backend/src/services/notifications/tests/test_bridge.py`
- Jira tests: `backend/src/services/jira/tests/test_bridge.py`

---

## 8. Scalability

- **Current capacity:** The system supports concurrent multimodal incident intake, asynchronous workflow execution, and externalized ticketing/notification handling through Docker Compose.
- **Scaling approach:** Fast stateless intake at the edge, asynchronous background workflow execution, and shared specialized services for retrieval, ticketing, notifications, and observability.
- **Reference:** See `SCALING.md` for the full scaling analysis, assumptions, and technical decisions.

---

## 9. Lessons Learned & Team Reflections

- **What worked well:** Event-driven workflow orchestration, early guardrails, retrieval-backed triage, and strong observability made the system easy to demo and explain.
- **What you would do differently:** With more time, we would extend the communication layer beyond email-only team fan-out and harden the long-running workflow execution path.
- **Key technical decisions:** We chose one orchestrating agent, async FastAPI ingestion, Qdrant-backed retrieval, Jira-based ticket lifecycle, and MLflow/Grafana/Loki/Prometheus observability to keep the system modular and reviewer-friendly.

---
