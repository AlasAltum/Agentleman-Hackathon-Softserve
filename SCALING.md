# Scaling

This document explains how the platform scales and why the architecture works well for high-throughput incident intake, automated triage, and operational visibility.

It is written to support the submission requirements directly, especially the ability to scale:

- multimodal incident intake
- guardrailed agent execution
- observability across the full workflow
- ticketing and notification integrations
- analysis of a medium/complex e-commerce codebase
- reproducible Docker Compose deployment

Scope covered here:
- `backend/`
- `observability/`
- `sre-platform/`
- `ecommerce-platform/` as an analyzed application dependency used by the triage workflow

## Executive Summary

The platform is designed to stay responsive at the point of intake, push heavier reasoning into asynchronous workflows, and rely on shared services where specialization helps most.

- The backend API is lightweight at the HTTP edge and can be replicated cleanly.
- The optional SRE platform provides a separate UI and API edge layer, which keeps user interaction concerns decoupled from workflow execution.
- The core incident workflow runs asynchronously, allowing the platform to accept reports quickly while continuing deeper triage in the background.
- Shared services such as Qdrant, Jira, Nylas, and the observability stack give the system specialized capabilities without overloading the application tier.
- Built-in logs, traces, and dashboards ensure the platform remains inspectable as traffic and workflow volume grow.
- The workflow can reason over a real e-commerce application codebase without turning the user-facing services into heavy analysis nodes.

At a high level, the platform scales by keeping the entry tier responsive, the workflow tier asynchronous, and the stateful pieces clearly separated.

## Requirement Alignment

From an evaluation perspective, the scaling design supports every required capability in a way that stays modular and easy to demo.

- Multimodal input scales through a single ingest path that accepts text plus file attachments and preprocesses them before orchestration.
- Guardrails scale because validation and relevance checks are applied consistently at the boundary before deeper workflow execution begins.
- Observability scales across the required lifecycle stages: ingest, triage, ticket creation, notification, and resolution.
- Integrations scale through dedicated adapters for ticketing and email, with communication behavior staying outside the core application tier.
- The e-commerce requirement is satisfied by using a real open-source commerce codebase as an analysis target for incident investigation.
- Docker Compose remains the standard deployment contract, which keeps the whole stack reproducible for reviewers.

This matters because the submission is not only feature-complete. It is also organized so those features remain understandable and workable as load grows.

## Scaling Principles

The architecture follows five simple ideas that make growth easier to handle.

### 1. Stateless Intake Layer

The backend API and the optional SRE platform serve as clean front doors to the system.

- They focus on accepting requests, validating inputs, and forwarding work.
- Request correlation is based on generated request IDs and async context, which makes instances easy to replicate.
- User-facing services remain focused on transport, orchestration, and response handling rather than long-lived state management.
- The same intake boundary handles multimodal submissions, which keeps scaling concerns centralized instead of fragmented across multiple services.

That keeps the edge tier simple, responsive, and easy to scale out.

### 2. Asynchronous Workflow Execution

The ingest API returns `202 Accepted` after validation and preprocessing, then continues the full triage flow asynchronously in the background.

This is one of the most important scaling decisions in the system because it cleanly separates client responsiveness from workflow execution time.

- Incidents are accepted quickly.
- Downstream analysis can run with richer logic and external integrations.
- Longer-running operations such as retrieval, reranking, summarization, ticketing, and notifications do not need to block the caller.
- The same execution model also supports codebase analysis, guardrail enforcement, and integration fan-out without slowing the initial user interaction.

In practice, that gives the platform a solid foundation for sustained incident intake.

### 3. Parallel Tool Orchestration

Inside the workflow, the platform uses async execution and parallel tool fan-out to keep analysis efficient and responsive.

- Tool dispatch is handled concurrently with `asyncio.gather(...)`.
- Blocking SDK operations are moved off the event loop with `asyncio.to_thread(...)`.
- The backend benefits from Python async I/O while still integrating with external systems cleanly.

As a result, the workflow is not limited to a single serial chain of work. It can examine one incident through multiple lenses at the same time.

### 4. Shared Specialized Services

The application tier stays lean by pushing specialized responsibilities into the systems best suited to handle them.

- Qdrant handles similarity retrieval and historical incident context.
- Jira handles ticket lifecycle management.
- Nylas handles outbound notification delivery.
- Grafana, Loki, Prometheus, Alloy, and MLflow handle observability.
- The e-commerce application remains a dedicated application repository that the workflow can inspect when incidents point to code or behavior regressions.

This kind of separation supports scale well: stateless compute at the edge, purpose-built systems behind it.

### 5. Observability As Part Of Scalability

Scalable systems are not only fast. They are also measurable.

This platform includes:

- structured JSON logs
- request-level correlation IDs
- end-to-end workflow traces through MLflow
- metrics-ready service instrumentation
- Grafana dashboards for operational visibility

That makes it much easier to understand throughput, latency, tool behavior, and integration health as the platform handles more traffic and complexity.

## Runtime Topology

The runtime is deliberately modular, which makes the deployment model clear and easy to reason about.

- The root `docker-compose.yml` includes the backend stack and the observability stack as the default core deployment.
- `sre-platform/docker-compose.yml` exists as a separate edge stack that can sit in front of the backend when a dedicated incident UI and auth layer is desired.
- The backend owns ingest, preprocessing, guardrails, workflow orchestration, ticketing, and notifications.
- The backend can also inspect the e-commerce repository as part of incident investigation, which keeps code-aware triage inside the same end-to-end automation flow.
- The observability stack stays orthogonal to business logic, which means operational visibility can grow alongside the platform.

This deployment model is intentionally centered on Docker Compose, which aligns with the evaluation requirement for consistent, reproducible execution.

This topology makes the system easy to explain, deploy, and extend.

## How The Platform Scales

### Backend

The backend is designed as an async FastAPI service with a clear orchestration role.

Its main scaling strengths are:

- fast request handling at the HTTP boundary
- asynchronous workflow continuation after the incident is accepted
- concurrent tool execution inside the workflow
- lightweight application instances that rely on external systems for specialized work

The ingest path is also designed to be robust.

Before an incident enters the workflow, the backend can:

- validate files and MIME types
- preprocess text and attachments
- perform OCR on supported images
- apply multiple guardrail checks
- run an LLM-based relevance filter

Together, these checks make sure that well-formed, relevant incident data enters the automated triage pipeline.

That directly supports two of the most important submission requirements: multimodal input and guardrails.

### SRE Platform

The optional SRE platform adds a dedicated operator-facing edge without increasing the complexity of the backend itself.

- `sre-platform/api` provides authentication and report forwarding.
- `sre-platform/web` provides the user-facing experience.
- The platform uses a clean API handoff to the backend, which keeps the responsibilities separate and deployable by layer.

This is a strong design choice because the UI, auth layer, and backend triage engine can evolve independently.

### Qdrant

Qdrant serves as the shared intelligence layer for incident similarity and historical retrieval.

The platform uses it to classify incidents into patterns such as:

- new incident
- alert storm
- historical regression

That gives every backend instance access to the same retrieval-backed operational memory and helps keep triage behavior consistent across deployments.

The startup flow also bootstraps a curated incident corpus, which is excellent for reproducibility, demo quality, and deterministic behavior across environments.

### PostgreSQL

PostgreSQL is provisioned as the structured data layer for relational growth, analytics, and future metadata expansion.

That is a good architectural choice because it keeps the current workflow path lean while preserving a clear place for structured persistence as the platform evolves.

### Observability Stack

Observability is one of the strongest parts of the system, and it is a major reason the platform scales well operationally.

The stack includes:

- Grafana for dashboards
- Prometheus for metrics collection
- Loki for centralized logs
- Grafana Alloy for collection and shipping
- MLflow for workflow traces

These components collectively support visibility across the required operational stages:

- ingest
- triage
- ticket
- notify
- resolved

The operational flow is straightforward:

- the backend emits structured logs to stdout
- Docker captures the log stream
- Alloy discovers the backend container and forwards logs to Loki
- Grafana provides the unified visualization layer
- MLflow captures workflow traces and LLM activity

This gives the project a mature, operations-friendly architecture rather than a black-box demo.

For evaluation, that is important because observability is not limited to a single service. It follows the main business flow end to end.

## Technical Decisions That Strengthen Scalability

### 1. Async-First Python Backend

The backend uses FastAPI plus async I/O to maximize concurrency for network-heavy operations such as LLM calls, ticketing, and notifications.

Why this works well:

- high concurrency for I/O-bound workloads
- clean integration with external providers
- excellent fit for incident-driven orchestration

### 2. `202 Accepted` Contract For Ingest

The platform acknowledges incident intake quickly, then continues with richer workflow execution behind the scenes.

Why this works well:

- fast user experience
- clear separation between intake and processing
- better operational handling of longer reasoning flows

### 3. Dedicated Edge Layer

The SRE platform is kept separate from the triage engine.

Why this works well:

- UI and auth concerns stay isolated
- the operator experience can evolve independently
- backend compute remains focused on incident automation

### 4. Externalized Integrations

The platform connects to specialized external systems instead of reimplementing them internally.

Why this works well:

- Jira handles incident tracking
- Nylas handles communication delivery
- Qdrant handles semantic retrieval
- observability services handle telemetry and traceability

This also maps cleanly to the required integration story: ticketing, email, and communicator behavior in a demoable end-to-end flow.

This keeps the application layer modular, focused, and easy to reason about.

### 5. Shared Retrieval Layer

Qdrant gives the platform a centralized intelligence service for incident similarity.

Why this works well:

- retrieval quality is shared across the deployment
- all workflow instances can reason over the same operational memory
- classification remains grounded in prior incidents rather than isolated per node

### 6. Observability-Native Design

Observability is not bolted on afterward. It is built into the architecture.

Why this matters:

- every incident can be correlated end to end
- workflow phases are easier to inspect and explain
- the system becomes more scalable operationally because it stays measurable under load

### 7. Reproducible Modular Deployment

The repository uses a compose-based, multi-stack layout.

Why this works well:

- easy local reproduction
- clear service boundaries
- straightforward path from demo deployment to orchestrated deployment patterns

## Assumptions In The Current Design

This scalability model is based on a few clear assumptions.

- The root `.env` file is the canonical runtime configuration.
- The default deployment unit is the backend plus the observability stack.
- The SRE platform is an optional but production-friendly edge layer.
- Request IDs are propagated across the workflow and integrations for traceability.
- Jira webhooks represent the standard deployed resolution path.
- LLM, embedding, ticketing, and notification providers can be selected through configuration.
- Demo environments commonly run with `APP_ENV=dev` so the full workflow remains highly visible.
- Docker Compose is the canonical way to run the submission end to end.
- The e-commerce repository is treated as a realistic application target for incident analysis, not just a placeholder asset.

## Why This Architecture Sells Well

This project presents the kinds of scaling patterns people expect from modern production software.

- Fast, stateless intake at the edge
- Asynchronous background processing for heavier reasoning
- Parallel tool orchestration inside the workflow
- Shared semantic retrieval through a dedicated vector store
- Real integrations with ticketing and notifications
- End-to-end observability across logs, traces, and dashboards
- Practical analysis of a real e-commerce application codebase inside the triage loop
- Reproducible Docker Compose deployment for consistent review and demo execution

In other words, the platform is not just functional. It is structured in a way that supports growth in incident volume, analysis depth, and operational complexity.

## Bottom Line

The software scales by combining three clear strengths:

- lightweight, replicable entry services
- asynchronous workflow execution for deeper incident automation
- shared specialized systems for retrieval, integrations, and observability

Together, those strengths make the project easy to present to hackathon judges: fast intake, intelligent background processing, strong modularity, and clear operational visibility across the full incident lifecycle.