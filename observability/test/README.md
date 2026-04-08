This folder contains local smoke-test scaffolding for the observability stack.

Purpose:
- keep validation independent from the main backend
- install only the Python packages needed for logs, metrics, and traces
- provide a stable place for the emitter scripts added in later tasks

## Local setup

From the repository root:

```bash
python -m venv .venv-observability
source .venv-observability/bin/activate
pip install -r observability/test/requirements.txt
```

## Expected scripts

The observability smoke-test scripts are:
- `emit_logs.py`
- `emit_metrics.py`
- `emit_traces.py`
- `simulate_stack_check.py`

## How this test area works

- `emit_logs.py` will write structured JSON logs to standard output.
- You can redirect those logs into files under `observability/test/logs/` so Promtail can scrape them.
- `emit_metrics.py` will expose a local Prometheus endpoint for the stack to scrape.
- `emit_traces.py` will publish traces to the local MLflow server using the host-side settings from the root `.env` file.

## Available scripts

Emit sample structured logs and write them into the Promtail scrape directory:

```bash
python observability/test/emit_logs.py --output-file observability/test/logs/emit_logs.log
```

This writes UTF-8 directly from Python and avoids shell redirection encoding problems.

On Windows PowerShell 5.1, avoid `>` and `Out-File -Encoding utf8` for Loki sample logs:
- `>` writes UTF-16 and produces the spaced-character effect in Grafana
- `Out-File -Encoding utf8` writes a UTF-8 BOM, which shows up as `﻿` before the JSON line

If you are using PowerShell 7 and still want shell redirection, use a no-BOM encoding mode instead:

```powershell
python observability/test/emit_logs.py | Out-File -Encoding utf8NoBOM observability/test/logs/emit_logs.log
```

Expose a sample Prometheus endpoint on the port already configured in `observability/prometheus/prometheus.yml`:

```bash
python observability/test/emit_metrics.py --port 9464
```

The metrics emitter runs until interrupted by default so Prometheus has time to scrape it.

Create a manual MLflow trace with nested phase spans:

```bash
python observability/test/emit_traces.py
```

Run the combined stack validator. This writes a UTF-8 log file, emits a trace, and keeps a metrics endpoint alive briefly so Prometheus can scrape it:

```bash
python observability/test/simulate_stack_check.py --metrics-wait-seconds 25
```

If Docker is running through WSL, set `OBSERVABILITY_METRICS_TARGET` in `.env` to the current WSL distro IP before starting the stack, then run `emit_metrics.py` and `simulate_stack_check.py` from that same distro.

## Validation Runbook

### 1. Prepare the local env files

From the repository root, create the env files used by the included root compose project:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
```

Notes:
- `.env` provides the local Grafana and MLflow settings used by the observability stack.
- `backend/.env` must exist because the root `docker-compose.yml` includes the backend compose file, even if you only start observability services.
- The backend-related defaults at the bottom of `.env.example` are needed so the root compose file can interpolate the included backend model cleanly.

If you are running the metrics emitter from Linux in WSL, update `.env` before starting the stack so Prometheus scrapes the distro IP instead of `host.docker.internal`:

```bash
WSL_IP=$(hostname -I | awk '{print $1}')
sed -i "s#^OBSERVABILITY_METRICS_TARGET=.*#OBSERVABILITY_METRICS_TARGET=${WSL_IP}:9464#" .env
```

### 2. Start only the observability services from the repository root

```bash
docker compose up -d grafana prometheus loki promtail mlflow
docker compose ps
```

Expected result:
- Grafana listens on `http://localhost:3000`
- Prometheus listens on `http://localhost:9090`
- Loki listens on `http://localhost:3100`
- MLflow listens on `http://localhost:5000`
- the MLflow container reaches `healthy` status

### 3. Run the standalone smoke-test scripts

Emit logs into the Promtail scrape directory:

```bash
python observability/test/emit_logs.py --request-id 018f0c69-acde-7012-8d6a-000000000101 --output-file observability/test/logs/emit_logs.log
```

Expose the Prometheus metrics endpoint:

```bash
python observability/test/emit_metrics.py --port 9464
```

Emit a manual MLflow trace:

```bash
python observability/test/emit_traces.py --request-id 018f0c69-acde-7012-8d6a-000000000102
```

Run the combined validator with one correlated request id across logs and traces, while keeping metrics alive briefly for scraping:

```bash
python observability/test/simulate_stack_check.py --request-id 018f0c69-acde-7012-8d6a-000000000103 --metrics-wait-seconds 25
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
- Check `Status -> Targets` and confirm the metrics emitter target is `UP` when the emitter or combined validator is running from a Docker-reachable environment.
- Query:

```text
observability_test_phase_runs_total
```

- Success looks like per-phase counters for `ingest`, `classify`, and `notify`.

MLflow:
- Open `http://localhost:5000`.
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

The dependencies here stay focused on:
- structured logging
- Prometheus metrics
- MLflow tracing

LlamaIndex can be added in the trace emitter task if that implementation path is selected.