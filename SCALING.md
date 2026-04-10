# Scaling

This document explains how the platform scales, which assumptions that design depends on, and which technical decisions make that scaling model practical.

The main idea is simple:

- incident intake stays fast and defensive
- heavier triage work runs after the report has been accepted
- stateful and specialized responsibilities are pushed out of the backend process
- the system is observable enough to find bottlenecks before they become outages

That is what makes the architecture scalable. The goal is to keep the intake path responsive, keep the workflow modular, and let infrastructure-heavy dependencies scale on their own terms.

## Core Scaling Model

The platform scales through five decisions that work together:

1. The backend ingest endpoint validates and filters reports before expensive workflow execution begins.
2. The full SRE workflow runs asynchronously after the API returns `202 Accepted`.
3. Services are separated by deployment boundary, so the backend, databases, observability stack, and optional UIs are not forced to scale together.
4. Stateful and high-cost dependencies such as PostgreSQL, Qdrant, Jira, Nylas, and AI providers live outside the backend runtime.
5. Observability is built in, so throughput limits and slow components can be identified early.

Everything else in this document is a consequence of those choices.

## 1. Ingest Is The Real Front Door

The primary entry point to the agent platform is `POST /api/ingest` in `backend/src/api/routes/incident_routes.py`.

That route does the work that should happen before the system commits resources to a report:

- validates required text input and reporter email
- limits attachment count and file size
- validates MIME type and magic bytes for uploads
- preprocesses text and attachments into a consolidated incident payload
- runs guardrails to block malicious or suspicious input
- runs an LLM-based relevance check to reject off-topic submissions

Only after those checks pass does the route start the SRE workflow in the background with `asyncio.create_task(...)`.

This is the most important scaling decision in the project.

The API does not wait for the full triage loop, ticketing, notifications, or codebase analysis to finish. It returns `202 Accepted` with a request ID and keeps processing asynchronously.

Why that matters:

- the user gets immediate confirmation that the report was received
- the HTTP edge stays responsive under higher report volume
- expensive workflow capacity is reserved for validated, relevant incidents only
- backend replicas can focus on intake and orchestration instead of long-lived request handling

In practice, this means the user experience remains good even when deeper analysis takes longer.

## 2. There Are Multiple Ways To Ingest Reports

The platform does not depend on a single frontend to receive incidents.

Reports can reach the ingest endpoint through multiple paths:

- direct requests to the backend API
- the e-commerce platform, which can submit reports to the ingest API
- the dedicated SRE platform, whose API forwards authenticated reports to the backend ingest route

This is useful for scale and for availability.

If the e-commerce application is degraded, SREs can still use the separate SRE platform. If the SRE platform is unavailable, reports can still be sent directly to the backend API. The backend ingest contract remains the common denominator.

That gives the system a more resilient intake model than a single UI-dependent architecture.

## 3. The Workflow Scales Because It Is Asynchronous Internally Too

The backend does not only scale by returning early from the ingest route. It also uses async execution inside the workflow.

The codebase already uses patterns such as:

- `asyncio.create_task(...)` for background dispatch
- `asyncio.gather(...)` for parallel tool fan-out
- `asyncio.to_thread(...)` for blocking SDK and LLM calls

That matters because the workflow is I/O-heavy. It talks to LLMs, retrieval systems, ticketing, notification providers, and sometimes the e-commerce codebase. Async orchestration allows one backend instance to make progress on multiple incidents without serializing every external call.

This does not eliminate the need for more replicas under higher load, but it does make each replica more efficient.

## 4. Container Boundaries Make Independent Scaling Possible

The repository is already split into separate deployable components:

- backend application
- PostgreSQL
- Qdrant
- observability stack
- optional SRE platform
- optional e-commerce platform

Docker Compose is the local deployment contract, not the scaling mechanism itself. The important point is that the services are already separated. That means they do not need to scale as a single unit.

This is valuable because each component has different resource behavior:

- the backend is compute and network heavy
- PostgreSQL is storage and connection sensitive
- Qdrant is memory and I/O sensitive
- observability services have their own ingestion and retention profile
- UI services and API edges have different traffic patterns from background workflow execution

Because of these boundaries, the architecture can move beyond local compose into independently managed deployments without redesigning the application first.

## 5. Modular Code Keeps Future Decomposition Low Friction

The code is organized into separate domains such as:

- guardrails
- preprocessing
- workflow phases
- Jira integration
- notifications
- Qdrant integration
- observability utilities

That modularity matters because it keeps the current backend simple while preserving room for extraction later.

If traffic or operational complexity increases, pieces such as ticket creation, notification fan-out, codebase analysis, or other workflow phases could be moved into separate workers or managed services with limited impact on the rest of the system.

In other words, the codebase is not written as one large inseparable service. It already has the internal seams needed for further decomposition.

## 6. The Backend Can Scale Horizontally Because State Is Externalized

The backend mostly behaves as an orchestrator. It does not try to keep all important state inside its own process.

Specialized responsibilities are delegated to external systems:

- PostgreSQL for relational persistence
- Qdrant for vector search and similarity retrieval
- Jira for ticket lifecycle
- Nylas for outbound notifications
- external AI providers for LLM and embedding workloads

This is one of the clearest scaling advantages in the design.

Because databases, retrieval, and AI inference can be managed by cloud providers, backend instances do not have to carry that state locally. Once those dependencies are externalized or managed separately, the backend can scale horizontally much more cleanly.

Why that matters:

- adding backend instances does not require rethinking local state ownership
- PostgreSQL and Qdrant can scale with the storage systems best suited for them
- AI throughput can increase independently from backend container count
- the backend remains a thinner orchestration layer instead of a state-heavy monolith

This is exactly the kind of separation that makes horizontal scaling realistic.

## 7. The Jira Resolution Webhook Has A Natural Serverless Upgrade Path

The Jira resolution flow is handled through a narrow webhook route in `incident_routes.py`.

That handler:

- accepts the Jira payload
- filters out irrelevant or non-human events
- projects the payload into the internal resolution model
- triggers resolution handling and notification dispatch

This is already close to a serverless shape. It is stateless, request-driven, and has a well-bounded responsibility.

Because of that, it would be straightforward to front this path with API Gateway and move the webhook handler into a serverless deployment if webhook burst traffic or isolated scaling became necessary.

That would let webhook traffic scale independently from the main ingest API while preserving the same downstream resolution behavior.

## 8. The E-commerce Platform Is Decoupled From The Agentic Backend

The e-commerce platform is not embedded into the agent runtime. It is a separate application that can send incidents to the backend and can also be analyzed by the workflow when needed.

That separation matters in two ways.

First, the agent platform can work with any application that can reach the ingest API. It is not coupled to one specific commerce deployment.

Second, the codebase analysis step is path-based. The analyzer resolves its target through the `ECOMMERCE_ROOT` environment variable, defaulting to `/ecommerce-platform`.

That means the analyzed application can move without breaking the workflow, as long as the configured path points to the right codebase.

This gives the system useful portability:

- the e-commerce stack can scale independently from the backend
- another platform can be analyzed later without rewriting the overall triage model
- changes in where the codebase lives can be handled through configuration rather than logic changes

This is a good example of scale-through-decoupling: the agent does not depend on one hard-coded application layout.

## 9. Observability Makes Scaling Operable

The observability stack does not add raw capacity by itself, but it is what makes capacity problems diagnosable.

The platform includes:

- structured logs
- request-level correlation IDs
- metrics collection
- workflow traces
- Grafana dashboards
- Loki log aggregation
- Prometheus metrics scraping
- Grafana Alloy collection and shipping
- MLflow tracing for workflow and LLM activity

This is important because scaling problems are rarely abstract. They show up as slow ingest responses, queueing behavior, failed integrations, noisy tickets, slow LLM calls, or overloaded dependencies.

The observability layer makes it possible to detect those bottlenecks and decide where to scale or refactor next.

Without that visibility, a system may still run, but it does not scale well operationally.

## Assumptions

This scaling model depends on a few assumptions:

- the backend ingest route remains the canonical intake contract
- the repository root `.env` remains the main runtime configuration source
- Docker Compose remains the standard local and demo deployment method
- PostgreSQL, Qdrant, and AI services can be moved to managed infrastructure when more scale is needed
- backend instances remain mostly stateless apart from external dependencies
- the analyzed application is referenced through configuration such as `ECOMMERCE_ROOT`
- the e-commerce platform, SRE platform, and direct API clients may be available independently
- observability remains enabled so bottlenecks can be identified in production-like runs

## Technical Decisions That Enable Scale

The main technical decisions are:

1. The ingest endpoint performs validation and guardrails first, then returns `202 Accepted` while the workflow continues asynchronously.
2. The system supports multiple report-ingress paths instead of depending on a single frontend.
3. The deployment is split into separate services so backend, storage, retrieval, UI, and observability concerns can evolve independently.
4. Stateful and high-cost dependencies are externalized so the backend can scale horizontally.
5. The workflow uses async concurrency instead of serial blocking calls.
6. The codebase is modular enough to extract heavy responsibilities into separate managed services later if needed.
7. The Jira webhook is narrow and stateless enough to be moved to serverless infrastructure if burst scaling becomes important.
8. The analyzed e-commerce application is configured by path, which keeps the agent reusable across different target systems.
9. Observability is built in so scaling limits can be measured instead of guessed.

## Bottom Line

The platform scales because it avoids turning every concern into the same runtime problem.

- intake is fast and protected by guardrails
- deeper triage runs asynchronously
- services are separated by deployment boundary
- specialized dependencies can be managed independently
- the analyzed application is decoupled from the agent platform
- observability makes bottlenecks visible

That gives the project a realistic path from hackathon deployment to a higher-throughput system without changing the core architecture.