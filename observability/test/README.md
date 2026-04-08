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

The next observability tasks will add:
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

If Docker is running through WSL and Prometheus cannot reach a Windows-hosted emitter on `host.docker.internal:9464`, run the metrics emitter from an environment that is reachable by the Docker engine.

## Current dependency scope

The dependencies here stay focused on:
- structured logging
- Prometheus metrics
- MLflow tracing

LlamaIndex can be added in the trace emitter task if that implementation path is selected.