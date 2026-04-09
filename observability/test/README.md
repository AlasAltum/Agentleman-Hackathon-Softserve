This folder contains local smoke-test scaffolding for the observability stack.

Purpose:
- keep validation independent from the main backend
- install only the Python packages needed for logs, metrics, and traces
- provide a stable place for the emitter scripts added in later tasks

## Local setup

These smoke tests now run through Docker and Poetry instead of a host-side Python environment.

From the repository root, build the dedicated runner image once:

```bash
docker compose --profile test build observability-test-runner
```

The runner uses the same `python:3.12-slim` base image family as the observability Docker stack, and it installs the smoke-test dependencies from `observability/test/pyproject.toml` and `observability/test/poetry.lock` with Poetry.

The command examples below assume the `observability-test-runner` service is already running and execute from `/workspace/observability/test` inside that container. You can start it directly with `docker compose --profile test up -d observability-test-runner`, or by starting the full stack in the runbook below.

## Expected scripts

The observability smoke-test scripts are:
- `emit_logs.py`
- `emit_metrics.py`
- `emit_traces.py`
- `simulate_stack_check.py`

## How this test area works

- `emit_logs.py` will write structured JSON logs to standard output.
- The scripts write log files under `observability/test/logs/` so Alloy can scrape them from the shared repository mount.
- `emit_metrics.py` will expose a local Prometheus endpoint for the stack to scrape.
- `emit_traces.py` will publish traces to the local MLflow server through the Docker network using the runner service environment.

## Available scripts

Emit sample structured logs and write them into the Alloy scrape directory:

```bash
docker compose exec observability-test-runner poetry run python emit_logs.py --output-file logs/emit_logs.log
```

This writes UTF-8 directly from Python inside the runner container and avoids shell redirection encoding problems.

Expose a sample Prometheus endpoint on the port already configured in `observability/prometheus/prometheus.yml`:

```bash
docker compose exec observability-test-runner poetry run python emit_metrics.py --port 9464
```

The metrics emitter runs inside the `observability-test-runner` container until interrupted, so Prometheus can scrape it over the Docker network.

Create a manual MLflow trace with nested phase spans:

```bash
docker compose exec observability-test-runner poetry run python emit_traces.py
```

Run the combined stack validator. This writes a UTF-8 log file, emits a trace, and keeps a metrics endpoint alive briefly so Prometheus can scrape it:

```bash
docker compose exec observability-test-runner poetry run python simulate_stack_check.py --metrics-wait-seconds 25
```

The default Prometheus smoke-test target is now the Docker service name `observability-test-runner:9464`. Only override `OBSERVABILITY_METRICS_TARGET` if you intentionally run the metrics emitter outside Docker.

## Validation Runbook

### 1. Prepare the local env files

From the repository root, create the single env file used by the included root compose project:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Notes:
- The root `.env` provides the local Grafana, MLflow, backend, Jira, and notification settings used by the full stack.
- `backend/.env` is no longer required because the included backend compose file now reads the repository root `.env`.
- The backend-related defaults in `.env.example` are still needed so the root compose file can interpolate the included backend model cleanly.

### 2. Start only the observability services from the repository root

```bash
docker compose --profile test up -d --build grafana prometheus loki alloy mlflow observability-test-runner
docker compose ps
```

Expected result:
- Grafana listens on `http://localhost:3000`
- Prometheus listens on `http://localhost:9090`
- Loki listens on `http://localhost:3100`
- MLflow listens on `http://localhost:5001`
- `observability-test-runner` stays running so Docker can execute the smoke-test scripts with Poetry
- the MLflow container reaches `healthy` status

### 3. Run the standalone smoke-test scripts

Emit logs into the Alloy scrape directory:

```bash
docker compose exec observability-test-runner poetry run python emit_logs.py --request-id 018f0c69-acde-7012-8d6a-000000000101 --output-file logs/emit_logs.log
```

Expose the Prometheus metrics endpoint:

```bash
docker compose exec observability-test-runner poetry run python emit_metrics.py --port 9464
```

Emit a manual MLflow trace:

```bash
docker compose exec observability-test-runner poetry run python emit_traces.py --request-id 018f0c69-acde-7012-8d6a-000000000102
```

Run the combined validator with one correlated request id across logs and traces, while keeping metrics alive briefly for scraping:

```bash
docker compose exec observability-test-runner poetry run python simulate_stack_check.py --request-id 018f0c69-acde-7012-8d6a-000000000103 --metrics-wait-seconds 25
```

### 4. Verify success in each tool

Grafana and Loki:
- Open `http://localhost:3000`.
- Go to Explore and choose the Loki datasource.
- Query logs with a request id such as:

```text
{job="observability-test-logs"} |= "018f0c69-acde-7012-8d6a-000000000103"
```

- Success looks like structured JSON log lines with `request_id`, `service`, `component`, `phase`, and `status` fields.

Prometheus:
- Open `http://localhost:9090`.
- Check `Status -> Targets` and confirm the `observability-test-runner:9464` target is `UP` when the emitter or combined validator is running.
- Query:

```text
observability_test_phase_runs_total
```

- Success looks like per-phase counters for `ingest`, `classify`, and `notify`.

MLflow:
- Open `http://localhost:5001`.
- Open the `observability-local` experiment.
- Success looks like a trace named `incident_triage_smoke_test` with nested phase spans and tags that include the same `request_id` used by the script.

Correlation check:
- For `simulate_stack_check.py`, use the request id printed by the script.
- Success looks like the same request id appearing in Loki log lines and in MLflow trace metadata or tags.

### 5. Clean reset if needed

If you want to wipe the local observability state and start clean again:

```bash
bash observability/reset-data.sh --restart
```

## Current dependency scope

The Poetry dependencies here stay focused on:
- structured logging
- Prometheus metrics
- MLflow tracing

LlamaIndex can be added in the trace emitter task if that implementation path is selected.