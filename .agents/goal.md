# Hackathon Assignment: Build an SRE Incident Intake & Triage Agent

## Context:
We are participating in the SoftServe Agent Hackathon

Create an SRE Agent that ingests incident/failure reports for our company e-commerce application, performs initial automated triage (by analyzing code and documentation), and routes the issue to the technical team via our ticketing workflow, with end-to-end notifications for both engineers and the original reporter.

---

## Core E2E Flow

1. Submit the report via UI.
2. Agent triages on submit: extracts key details + produces an initial technical summary (using code/docs as available).
3. The agent creates a ticket in a ticketing system (Jira/Linear/Other).
4. Agent notifies the technical team (email and/or communicator).
5. When the ticket becomes resolved, the agent notifies the original reporter.

---

## Minimum Requirements

- **Multimodal input:** Accept at least text + one other modality (e.g., image/log file/video) and use a multimodal LLM.
- **Guardrails:** Basic protection against prompt injection / malicious artifacts (safe tool use + input handling).
- **Observability:** Logs/traces/metrics covering the main stages (ingest → triage → ticket → notify → resolved).
- **Integrations:** Ticketing + email + communicator (real or mocked, but must be demoable).
- **E-commerce codebase:** Use a medium/complex open-source repository for your e-commerce application.

---


# Technical Requirements for Submission

To ensure consistent evaluation across all teams, each submission must meet the following technical requirements.

---

## Required Repository Structure

Each repository must include the following files:

- **README.md** — architecture overview, setup instructions, and project summary
- **AGENTS_USE.md** — agent documentation, including use cases, implementation details, observability evidence, and safety measures
- **SCALING.md** — explanation of how the application scales, including the team's assumptions and technical decisions
- **QUICKGUIDE.md** — simple step-by-step instructions to run and test the application, ideally in the format: clone → copy `.env.example` → fill keys → `docker compose up --build`. OpenRouter support should be included if applicable
- **docker-compose.yml** — mandatory; the entire application must run through Docker Compose and expose only the required ports
- **.env.example** — all required environment variables, with placeholder values and comments
- **Dockerfile(s)** — referenced by `docker-compose.yml`
- **LICENSE** — the repository must be public and licensed under MIT

---

## Docker Requirement

Docker Compose is mandatory for all submissions.

Although we do not need to run every application during evaluation, Docker is required because it:

- ensures consistent and reproducible execution regardless of the technology stack
- provides a safer, sandboxed environment for code review and validation
- allows resource limits and network restrictions to be applied during evaluation if needed
- gives the review team a standard structure across all projects

The project must build and run from a clean environment using:

```
docker compose up --build
```

No host-level dependencies should be required beyond Docker Compose.

---

## Acceptable Implementation Scope

Participants may use mocked integrations where needed. This includes systems such as:

- ticketing platforms
- email systems
- communication tools

Mocked components are acceptable if the end-to-end flow is clearly demoable.

---

## Demo Video Requirements

Each submission must include a demo video that meets the following requirements:

- **Language:** English
- **Maximum length:** 3 minutes
- **Platform:** YouTube
- **Required tag:** #AgentXHackathon

The video should clearly demonstrate the value of the solution and show the main flow of the application.

---

## Important Notes for Participants

Before submitting, make sure your project satisfies the following:

- the repository is public
- the repository includes an MIT License
- the required files are present and complete
- the application can be built and run using `docker compose up --build`
- only necessary ports are exposed
- all required environment variables are documented in `.env.example`
- the demo video is published on YouTube and includes #AgentXHackathon

---

## Why These Requirements Exist

These requirements are designed to make submissions:

- easier to review
- more consistent across teams
- safer to evaluate
- easier to understand without requiring full execution

For security and consistency reasons, we do not rely on running every application during review. However, we still require a standardized, runnable structure to ensure fairness and technical completeness.

# Deliverables

Each team must submit the following by the deadline (see FAQ #1 in #faq for timezone details).

---

## 1. Solution Introduction

A brief text (2–3 paragraphs) introducing your solution, the problem it addresses, and your approach.

---

## 2. Demo Video

A publicly published YouTube video (maximum 3 minutes) demonstrating the full end-to-end flow of your agent:

submit → triage → ticket created → team notified → resolved → reporter notified

Tag it with **#AgentXHackathon** in the title or description.

---

## 3. Public Git Repository

A public Git repository licensed under MIT. The repo must include:

- **README.md** — architecture overview, setup instructions, and project summary
- **AGENTS_USE.md** — agent documentation: use cases, implementation details, observability evidence, and safety measures (reference: https://docs.anthropic.com/en/docs/agents-use-md)
- **SCALING.md** — explanation of how the application scales, including assumptions and technical decisions
- **QUICKGUIDE.md** — step-by-step instructions to run and test the application
- **docker-compose.yml** — the application must run via Docker Compose
- **.env.example** — all required environment variables with placeholders and comments
- **LICENSE** — MIT

For full technical details on each file, see the **Technical Requirements** post in this channel.

---

## Optional Extras

These are not required but are welcome and will be considered during evaluation:

- Smarter routing or severity scoring
- Deduplication of incidents
- Runbook suggestions
- Observability dashboards
- Team-wide agent configuration (skills, cursor rules, AGENTS.md, sub-agents, etc.)

---

## Submission Checklist

Before submitting, confirm:

- 🟡   Solution introduction is written
- 🟡  Demo video is published on YouTube, in English, max 3 minutes, tagged #AgentXHackathon
- 🟡  Repository is public with MIT License
- 🟡  All required files are present (README, AGENTS_USE.md, SCALING.md, QUICKGUIDE.md, docker-compose.yml, .env.example)
- 🟡  Application builds and runs with `docker compose up --build`

Incomplete submissions will not be evaluated.

```json
// Example of an MLflow logged event during the triage phase
{
  "event_type": "ContextEnrichedEvent",
  "incident_classification": "Historical Regression",
  "qdrant_similarity_score": 0.89,
  "time_delta_hours": 72,
  "tools_dispatched": ["check_business_impact", "analyze_codebase"],
  "latency_ms": 2104,
  "stage": "triage"
}
```

## Detailed End-to-End Workflow

The following outlines the step-by-step life of an incident report as it travels through our agentic system:

Phase 1: Ingestion and Security

    User Submission: A user submits an incident via the Next.js frontend form, providing a text description and optionally attaching files.

    API Reception: The payload ({ text_desc, file_attachment }) is sent via a POST request (/api/ingest) to our FastAPI orchestrator webhook.

    Guardrails Evaluation: The input passes through the Input Guardrails (NeMo). If a threat is detected, it blocks the request (HTTP 400) and alerts SecOps. If safe, it proceeds.

Phase 2: Dynamic Preprocessing

The safe payload enters the Dynamic Preprocessor (File Router). Depending on the MIME type, it applies the specific extraction logic mentioned in Section 3 (Regex for logs, OCR for images, etc.). Finally, it consolidates the input into a clean string and file metadata. This triggers the LlamaIndex Event-Driven Workflow, and MLflow begins tracing.
Phase 3: Retrieval and Incident Classification

    Candidate Retrieval: The agent queries the Qdrant Vector DB to extract the Top-K historical incidents matching the current report.

    Reranking: The Cross-Encoder Node Reranker filters and orders the results down to the Top-3 candidates.

    Cluster & Time Judge: An LLM evaluates the similarity of the candidates alongside timestamp metadata to classify the incident:

        Active Alert Storm (High Sim, < 24hrs): The system flags this to prevent duplicate tickets and increases the urgency of the existing open ticket.

        Historical Regression (High Sim, > 24hrs): The agent retrieves the historical Root Cause Analysis (RCA) to use as a suggestion (acting as a Known Error Database).

        New Incident (No Sim): The agent flags this for deep triage.

Phase 4: Enriched Routing and Tool Dispatch

The classified event is passed to the LLM Router/Orchestrator. The Tool Dispatcher selects expert tools based on the context:

    Analyzes .tf files if infrastructure issues are suspected.

    Analyzes the codebase if syntax errors are detected.

    Analyzes telemetry if metrics spikes are reported.

    Always executes check_business_impact() to calculate potential financial loss via SQL.
    A Result Processor consolidates these technical findings and sends them back to the Router.

Phase 5: Ticketing and Notification

    Ticket Generation: The Router compiles a comprehensive technical summary (including the drafted RCA and financial impact) and interacts with the Jira API:

        For Alert Storms: It updates the existing Jira ticket with a new comment.

        For Regressions or New Incidents: It creates a brand-new Jira ticket.

    Tech Alert: The agent immediately notifies the technical team via Slack and Email, providing the triage summary and a direct link to the ticket.

Phase 6: Resolution and Continuous Learning

    Resolution: The technical team works on the issue. Once resolved, they transition the ticket state to 'Done' in Jira.

    User Notification: Jira triggers a webhook back to the FastAPI backend, which automatically sends an email notifying the original reporter that their issue has been resolved.

    Auto-Improvement Loop: The system extracts the final resolution metadata from the completed ticket and saves it back into the Qdrant Vector DB, acting as a feedback loop to improve future retrievals and triage accuracy.