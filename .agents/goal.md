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