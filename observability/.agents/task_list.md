# Observability Task List

This task list is aligned with the chosen low-risk implementation:
- MLflow for LlamaIndex traces
- Prometheus for metrics
- Loki for logs
- Grafana for metrics and logs

The tasks are ordered so the team can build the local stack first, then validate it with simple Python emitters before wiring the full backend workflow.

1. [X] task Create Observability Stack Skeleton
Description: Create the base folder structure and Docker Compose definition for the local observability stack under `/observability`.
Requirements:
- Create `observability/docker-compose.yml`.
- Create configuration folders for Grafana, Prometheus, Loki, Promtail, and MLflow.
- Use official images unless a service needs a custom Dockerfile.
- Keep configuration files versioned in the repository.
How to check this is correct:
- `docker compose -f observability/docker-compose.yml config` runs without errors.
- The file structure matches the planned observability layout.
- Every required service is declared in Compose.

2. [X] task Configure Prometheus Scraping
Description: Add the Prometheus configuration needed to scrape local metrics sources used by the observability stack and the later smoke-test scripts.
Requirements:
- Create `observability/prometheus/prometheus.yml`.
- Configure Prometheus to scrape at least its own metrics and the metrics emitter endpoint used in `observability/test`.
- Keep scrape targets simple and local-first.
- Avoid unnecessary remote write or advanced alerting in the first iteration.
How to check this is correct:
- Prometheus starts successfully.
- The `/targets` page in Prometheus shows configured targets as `UP`.
- Sample metrics from the test emitter become queryable in Prometheus.

3. [X]  task Configure Loki and Log Shipping
Description: Set up Loki for log storage and Promtail for shipping structured logs from local containers or test scripts.
Requirements:
- Create `observability/loki/config.yml`.
- Add a Promtail service and corresponding configuration file.
- Use stdout as the default log emission path for Python test scripts.
- Make sure structured JSON logs can reach Loki without custom app-side Loki clients.
How to check this is correct:
- Loki starts successfully.
- Promtail starts successfully and reports active targets.
- A sample JSON log emitted by the test script appears in Loki and is searchable by `request_id` or `phase`.

4. [X] task Provision Grafana Datasources
Description: Configure Grafana so it automatically connects to Prometheus and Loki when the stack starts.
Requirements:
- Add Grafana provisioning files under `observability/grafana/provisioning`.
- Provision Prometheus as a metrics datasource.
- Provision Loki as a logs datasource.
- Do not provision Tempo in this implementation.
- Keep dashboard provisioning optional for the first iteration.
How to check this is correct:
- Grafana starts successfully.
- Prometheus and Loki appear automatically in Grafana datasources.
- Grafana Explore can query both datasources without manual setup.

5. [X] task Add Local MLflow Tracing Server
Description: Add a local MLflow service for storing and viewing traces produced by LlamaIndex and other tracing helpers.
Requirements:
- Add MLflow to `observability/docker-compose.yml`.
- Define how MLflow is started, including the backend store path and listening port.
- Use a persistent volume for MLflow local state.
- Keep the setup local and simple for hackathon use.
How to check this is correct:
- MLflow starts successfully.
- The MLflow UI opens in the browser.
- A sample trace created by the test scripts appears in the selected experiment.

6. [] task Add Persistence and Reset Scripts
Description: Make the local observability stack reproducible while preserving data across normal restarts and allowing a clean reset when needed.
Requirements:
- Add named Docker volumes for Grafana, Prometheus, Loki, and MLflow.
- Create `observability/reset-data.sh`.
- Reset scripts must stop the stack and remove data volumes without deleting repository configuration.
How to check this is correct:
- Stack data survives a normal `docker compose down` and `up` cycle when volumes are not removed.
- Running the reset script removes the persisted state.
- After reset, the stack starts cleanly again.

7. [] task Create Test Folder Scaffolding
Description: Create the `observability/test` folder and add the minimal dependency and usage scaffolding needed for smoke testing.
Requirements:
- Create `observability/test`.
- Add a minimal dependency file such as `requirements.txt`.
- Document how to run the test scripts locally.
- Keep dependencies focused on structured logging, Prometheus metrics, MLflow tracing, and LlamaIndex where needed.
How to check this is correct:
- The test folder can be installed independently of the main backend.
- A developer can follow the local instructions and run the scripts without guessing missing dependencies.

8. [] task Implement Log Emitter Script
Description: Add a simple Python script that emits structured logs for Loki validation.
Requirements:
- Create `observability/test/emit_logs.py`.
- Use structured JSON logging, ideally with `structlog`.
- Include fields like `request_id`, `phase`, `status`, and `service`.
- Write logs to standard output.
How to check this is correct:
- Running the script produces JSON logs in the terminal.
- The logs appear in Loki through Promtail.
- The logs are queryable in Grafana Explore.

9. [] task Implement Metrics Emitter Script
Description: Add a simple Python script that exposes Prometheus metrics for smoke-test validation.
Requirements:
- Create `observability/test/emit_metrics.py`.
- Expose an HTTP `/metrics` endpoint using a Prometheus Python client.
- Include counters and histograms for a few stable test phases.
- Keep labels low-cardinality.
How to check this is correct:
- Running the script exposes a valid Prometheus metrics endpoint.
- Prometheus scrapes the endpoint successfully.
- Sample metrics become queryable in Prometheus and visible in Grafana.

10. [] task Implement MLflow Trace Emitter Script
Description: Add a Python script that produces traces visible in the MLflow UI, ideally close to the intended LlamaIndex usage model.
Requirements:
- Create `observability/test/emit_traces.py`.
- Configure `MLFLOW_TRACKING_URI` and an experiment name.
- Use MLflow tracing APIs.
- Prefer demonstrating either LlamaIndex tracing via `mlflow.llama_index.autolog()` or a small manual tracing example that mirrors the final workflow shape.
- Include stable metadata such as `service`, `phase`, and `status`.
How to check this is correct:
- Running the script creates a trace in MLflow.
- The trace is visible in the MLflow UI under the configured experiment.
- The trace shows a parent-child structure or enough detail to validate the setup.

11. [] task Implement Combined Stack Validation Script
Description: Add a convenience script that triggers logs, metrics, and traces together so the whole observability stack can be validated in one run.
Requirements:
- Create `observability/test/simulate_stack_check.py`.
- Emit at least one structured log, one metric update, and one trace during a single execution.
- Reuse the same `request_id` across all emitted telemetry.
- Keep the script simple and deterministic.
How to check this is correct:
- One script execution produces correlated data across MLflow, Prometheus, and Loki.
- The same `request_id` can be found in logs and trace metadata.
- The script can be rerun after a stack reset without manual cleanup.

12. [] task Write Validation Runbook
Description: Document the exact steps needed to boot the stack, run the smoke tests, and verify the expected outputs.
Requirements:
- Add a short runbook in the observability docs or the test folder.
- Include commands for starting the stack.
- Include commands for running each emitter script.
- Include what success looks like in Grafana, Prometheus, Loki, and MLflow.
How to check this is correct:
- Another developer can follow the runbook without extra explanation.
- The validation workflow reproduces logs, metrics, and traces consistently.
- The runbook matches the actual file paths and commands in the repository.