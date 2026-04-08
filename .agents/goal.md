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