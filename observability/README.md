# Observability

This folder defines how we observe the AI workflow behind the SRE incident intake and triage agent.

The goal is simple: every important step in the workflow should be easy to inspect, measure, and explain. We want to know where time is spent, where tokens are consumed, where failures happen, and how one incident moved through the system from intake to resolution.

## What Observability Must Answer

For the hackathon, observability should help us answer these questions quickly:
- Which workflow phase is slow?
- Which phase consumes the most tokens or cost?
- Which tool or integration is failing?
- Where are retries, loops, or unstable behaviors happening?
- What is the current throughput of the system?
- Can we trace one incident across the full workflow?

## Workflow We Observe

The observability model follows the incident lifecycle.

### 1. User Input and Guardrails

What we observe:
- input patterns
- suspicious or malicious submissions
- blocked versus accepted requests

Main risk:
- a bad input can confuse or manipulate the system before triage begins

### 2. Prompt and Context Assembly

What we observe:
- prompt versions
- token size
- templates and parameters
- context preparation quality

Main risk:
- weak or imprecise context leads to incorrect or expensive model behavior

### 3. Retrieval and Tools

What we observe:
- retrieval relevance
- tool success rate
- coverage and recall
- tool latency

Main risk:
- incomplete context or failing tools can produce weak triage decisions

### 4. LLM Execution

What we observe:
- latency
- token usage
- cost
- model variability

Main risk:
- hallucinations, avoidable latency, and unnecessary cost

This is a high-priority phase for the project.

### 5. Response and Decision Output

What we observe:
- response quality
- safety
- format
- decision clarity

Main risk:
- unsafe, incomplete, or misleading outputs can damage routing and incident handling

### 6. Actions and Integrations

What we observe:
- task success
- retries
- execution errors
- ticketing and notification outcomes

Main risk:
- the agent may reason correctly but still fail during external actions and integrations

### 7. Feedback and Resolution

What we observe:
- human feedback
- usage signals
- resolution callbacks
- learning signals for future incidents

Main risk:
- the system may fail to close the loop or improve over time

## Signals That Matter Most

We care about three complementary signal types:
- Logs tell us what happened and why.
- Metrics tell us how often, how long, and how much.
- Traces show how one incident moved across the workflow.

The most important measurements for this project are:
- token usage by phase
- latency by phase
- throughput
- failure rate
- retry rate
- end-to-end traceability for each incident

## Local Stack Overview

The observability stack will run locally through Docker so the team can test and demo everything in a reproducible way.

We will use:
- Grafana for dashboards and exploration
- Prometheus for metrics
- Loki for logs
- Grafana Alloy for log collection and shipping
- MLflow for workflow traces

This setup gives the team a local control room for understanding the behavior of the AI workflow without depending on external observability infrastructure.

The repository root `docker-compose.yml` now includes both the backend stack and the observability stack, so running `docker compose` from the repository root uses a single combined project.

## How Backend Logs Reach Loki

For backend workflow logs, nothing in the business logic needs to push directly to Loki.

The intended path is:
- the backend writes logs to standard output or standard error
- Docker captures the container log stream
- Grafana Alloy discovers the backend container through the Docker socket
- Alloy forwards those logs to Loki
- Grafana queries Loki

That means the important requirement is not another Python-side Loki client. The important requirement is a collector that can see Docker logs. This stack now uses Alloy for that purpose.

One repo-specific caveat still applies: the backend logger currently emits most workflow phase logs at `INFO`, and those logs are only enabled when the backend runs with `APP_ENV=dev`. If `APP_ENV=prod`, Loki will still receive warnings and errors, but most of the normal workflow progress logs will be absent because the backend never emits them.

The local stack also keeps a file-based path for the smoke tests under `observability/test/logs/`, because `docker compose exec` output is not part of the long-running container log stream.

## Local Operations

### Reset Observability Data

Use `observability/reset-data.sh` when you want to clear the local Grafana, Prometheus, Loki, and MLflow state.

From the repository root:

```bash
bash observability/reset-data.sh
```

This will:
- stop only the observability services from the root compose project
- remove the named Docker volumes used by the local stack
- keep the versioned configuration files in the repository unchanged

If you want the stack to start again immediately after the reset:

```bash
bash observability/reset-data.sh --restart
```

If you only want to see the available options:

```bash
bash observability/reset-data.sh --help
```

On Windows, run the script from a bash-compatible shell such as WSL or Git Bash. In this workspace, Docker validation has been running through WSL, so the safest option is to open the repository root in WSL and run the same commands there.

For file-based log collection details, see `observability/FILE_LOGS.md`.

## Two Complementary Views

### Operational AI Observability

Operational observability focuses on reliability and performance.

It helps us replay incidents, inspect latency, monitor throughput, and identify where costs or failures are coming from.

### Semantic AI Observability

Semantic observability focuses on quality and correctness.

It helps us understand whether the agent used the right context, produced useful outputs, and stayed aligned with the intended task.

## Why This Matters for the Hackathon

The strength of this project is not only that it automates triage. It is also that the workflow stays inspectable under pressure.

With good observability, we can:
- show the full incident journey during the demo
- identify bottlenecks quickly
- explain token and latency hotspots
- separate model issues from integration failures
- make the system easier to improve after the hackathon