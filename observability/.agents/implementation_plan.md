# Observability Implementation Plan

This plan is intentionally narrow.

It focuses on two concrete deliverables only:
- a Docker-based local observability stack for Prometheus, Grafana, Loki, and MLflow
- an `observability/test` folder with simple Python scripts that emit traces, metrics, and logs so the stack can be verified quickly

For this plan, `MLflow` is the primary tracing backend.

## 1. Goal

Build a local observability environment that can be started, reset, and validated without depending on the full product workflow.

The result should let the team confirm that:
- Prometheus receives metrics
- Loki receives logs
- MLflow receives traces
- Grafana can query and visualize metrics and logs
- sample Python scripts can generate test telemetry on demand

## 2. Scope

In scope:
- Docker-based deployment for Grafana, Prometheus, Loki, and MLflow
- persistence for local data
- reset scripts to clear persisted data and restart cleanly
- a test folder with simple Python emitters for logs, metrics, and traces
- validation steps for confirming the stack works end to end

Out of scope for this plan:
- full backend instrumentation across all workflow phases
- production-grade dashboards
- advanced alerting rules
- complete integration with the FastAPI application

## 3. Trace Backend Choice

Primary choice for this iteration:
- use MLflow as the trace store and trace viewer

Reasoning:
- it aligns with the existing observability docs
- it fits the team goal of tracing agentic workflows and execution trees
- it is easier to keep the first implementation focused if we do not introduce a second trace backend now

Important note about Tempo:
- Tempo can work as a trace backend and, depending on the architecture, as part of an OTLP-based trace ingestion path
- Tempo remains a valid future option if the team later wants Grafana-native trace exploration or a more OTLP-centric setup
- Tempo is not part of the first implementation target in this plan

## 4. Deliverable A: Docker-Based Observability Stack

### 4.1 Deployment Approach

Use Docker Compose as the primary deployment mechanism.

Reason:
- the repository already expects Docker Compose
- the stack consists of multiple services and should not be forced into one multi-process container
- official images are the simplest and most maintainable base for the hackathon

Preferred approach:
- use official images for Prometheus, Grafana, Loki, and MLflow
- keep configuration files under `/observability`
- only add custom Dockerfiles if a service needs bundled provisioning files or startup customization

### 4.2 Planned Folder Structure

Recommended structure:

```text
/observability
   /grafana
      /provisioning
         /datasources
         /dashboards
   /prometheus
      prometheus.yml
   /loki
      config.yml
   /mlflow
      Dockerfile
   docker-compose.yml
   reset-data.ps1
   reset-data.sh
   /test
```

### 4.3 Services

The stack must include:
- Prometheus for metrics scraping and querying
- Grafana for visualization and data exploration
- Loki for log storage and querying
- MLflow for trace storage and trace inspection

Nice-to-have later, but not required for this plan:
- Promtail or another log shipper if Docker stdout scraping is needed in the next step
- Tempo if the team later wants a dedicated Grafana-native trace backend in addition to or instead of MLflow

### 4.4 Persistence Requirements

Use persistent Docker volumes so the team can:
- restart services without losing dashboards and stored telemetry immediately
- inspect data after a test run
- demo the stack without reconfiguring it every time

Planned persistent volumes:
- `grafana_data`
- `prometheus_data`
- `loki_data`
- `mlflow_data`

Persistence rules:
- mount named volumes for service data directories
- keep configuration files in the repository, not inside mutable volumes
- reset scripts must remove the named volumes when a clean state is required

### 4.5 Reset Scripts

Provide both:
- `reset-data.ps1` for Windows
- `reset-data.sh` for Unix-like environments

The reset scripts should:
- stop the observability stack
- remove the named data volumes
- optionally remove orphaned containers for the observability project
- start the stack again if requested

The scripts must not delete repository configuration files.

### 4.6 Docker Deliverables

Deliverables for this track:
- `observability/docker-compose.yml`
- service configuration files for Prometheus, Loki, and Grafana provisioning
- MLflow container definition and required startup configuration
- persistent named volumes declared in Compose
- reset scripts for local cleanup

Acceptance criteria:
- one command starts the stack locally
- Grafana opens successfully and can connect to Prometheus and Loki
- MLflow opens successfully and can display traces
- data persists across normal restarts
- reset scripts clear local data predictably

## 5. Deliverable B: `observability/test` Smoke-Test Folder

### 5.1 Purpose

The test folder is not for unit tests.

It is a lightweight validation area where simple Python scripts generate sample telemetry so the observability stack can be checked without wiring the entire backend first.

### 5.2 Folder Goal

The scripts in `observability/test` should prove that:
- logs are visible in Loki
- metrics are visible in Prometheus
- traces are visible in MLflow
- Grafana can query the metrics and logs data sources

### 5.3 Planned Scripts

Required scripts:
- `emit_logs.py`
- `emit_metrics.py`
- `emit_traces.py`

Recommended extra script:
- `simulate_stack_check.py`

### 5.4 Script Responsibilities

`emit_logs.py` should:
- emit structured JSON logs from Python
- include fields like `request_id`, `phase`, `status`, and `service`
- write to standard output so the Docker log pipeline can capture the entries

`emit_metrics.py` should:
- expose or push sample metrics suitable for Prometheus validation
- generate counters and histograms for a few stable test phases
- make it easy to confirm scraping is working

`emit_traces.py` should:
- create a root trace and child spans
- send sample traces to MLflow using the chosen tracing integration
- include stable metadata such as `service`, `phase`, and `status`

`simulate_stack_check.py` should:
- run a small end-to-end sequence that emits logs, metrics, and traces together
- make the validation process easier during setup and demo rehearsal

### 5.5 Test Folder Dependencies

The test folder will likely need a small Python dependency set for:
- structured logging
- Prometheus metrics
- MLflow tracing support
- optionally OpenTelemetry libraries if the team decides to standardize trace generation through OTLP-compatible tooling later

Dependency handling should stay simple.

Preferred options:
- a small `requirements.txt` inside `observability/test`
- or a dedicated Poetry group if the team wants it integrated into the existing Python tooling

### 5.6 Test Deliverables

Deliverables for this track:
- `observability/test/emit_logs.py`
- `observability/test/emit_metrics.py`
- `observability/test/emit_traces.py`
- optional helper script for combined validation
- minimal dependency documentation for running the scripts locally

Acceptance criteria:
- the scripts run locally with minimal setup
- at least one sample log entry appears in Loki
- at least one sample metric appears in Prometheus
- at least one sample trace appears in MLflow
- Grafana can visualize or query the generated metrics and logs

## 6. Implementation Sequence

### Step 1: Create the Docker Stack Skeleton

Deliver:
- `observability/docker-compose.yml`
- config directories for Prometheus, Loki, Grafana, and MLflow

Done when:
- the service topology is defined and all required ports, volumes, and mounts are clear

### Step 2: Add Persistence

Deliver:
- named volumes for Grafana, Prometheus, Loki, and MLflow

Done when:
- stack data survives a normal restart

### Step 3: Add Reset Scripts

Deliver:
- `observability/reset-data.ps1`
- `observability/reset-data.sh`

Done when:
- the team can clear the observability state in a single predictable step

### Step 4: Create the Test Folder

Deliver:
- `observability/test`
- initial Python emitters for logs, metrics, and traces

Done when:
- the folder can be used independently from the main backend application

### Step 5: Validate the Stack End to End

Deliver:
- a short validation workflow documented in the test folder or README

Done when:
- the team can start the stack, run the emitters, and confirm all three telemetry types arrive successfully

## 7. Validation Checklist

The stack is considered working when all of the following are true:
- Docker starts Prometheus, Grafana, Loki, and MLflow successfully
- Grafana connects to the configured data sources
- Prometheus shows the sample metrics
- Loki shows the sample logs
- MLflow shows the sample traces
- reset scripts clear persisted data without removing repo configuration
- the test scripts can be rerun repeatedly after a reset

## 8. Definition of Done

This implementation plan is complete when the team has:
- a reproducible local Docker deployment for Prometheus, Grafana, Loki, and MLflow
- persistence configured for the stack
- reset scripts for wiping local state safely
- an `observability/test` folder with simple Python telemetry emitters
- a quick validation flow that proves the stack works as expected

## 9. Immediate Next Actions

The next build iteration should implement, in this order:

1. create `observability/docker-compose.yml` and the service config folders
2. wire named volumes for persistence
3. add `reset-data.ps1` and `reset-data.sh`
4. create `observability/test`
5. add Python scripts for logs, metrics, and traces
6. verify the emitted telemetry in Grafana, Prometheus, Loki, and MLflow