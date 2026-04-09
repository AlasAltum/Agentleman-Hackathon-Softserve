from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from prometheus_client import start_http_server

from emit_logs import DEFAULT_PHASES, emit_phase_logs, generate_request_id
from emit_metrics import emit_sample_cycle
from emit_traces import emit_trace_workflow, wait_for_trace_visibility


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit logs, metrics, and traces together for local stack validation.",
    )
    parser.add_argument(
        "--request-id",
        default=generate_request_id(),
        help="Correlation identifier reused across logs and traces.",
    )
    parser.add_argument(
        "--service",
        default="observability-test",
        help="Stable service tag used across emitted telemetry.",
    )
    parser.add_argument(
        "--component",
        default="stack-check",
        help="Stable component field used across emitted telemetry.",
    )
    parser.add_argument(
        "--phases",
        nargs="+",
        default=list(DEFAULT_PHASES),
        help="Stable workflow phases emitted across the validation run.",
    )
    parser.add_argument(
        "--tracking-uri",
        default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        help="MLflow tracking server URI.",
    )
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "observability-local"),
        help="MLflow experiment used for the emitted trace.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/simulate_stack_check.log",
        help="UTF-8 log file path scraped by Alloy.",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=9464,
        help="Port for the temporary Prometheus metrics endpoint.",
    )
    parser.add_argument(
        "--metrics-wait-seconds",
        type=float,
        default=25.0,
        help="How long to keep the metrics endpoint alive for Prometheus scraping.",
    )
    parser.add_argument(
        "--metrics-interval-seconds",
        type=float,
        default=5.0,
        help="Seconds between metrics sample emissions while the endpoint stays up.",
    )
    parser.add_argument(
        "--trace-visibility-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait while confirming the emitted trace is searchable.",
    )
    return parser.parse_args()


def emit_logs_to_file(args: argparse.Namespace) -> str:
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", newline="\n") as handle:
        emit_phase_logs(
            request_id=args.request_id,
            service=args.service,
            component=args.component,
            phases=args.phases,
            target=handle,
        )
    return str(log_path)


def keep_metrics_endpoint_alive(port: int, wait_seconds: float, interval_seconds: float) -> int:
    start_http_server(port)

    cycles_completed = 0
    deadline = time.monotonic() + wait_seconds

    while True:
        emit_sample_cycle()
        cycles_completed += 1

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        time.sleep(min(interval_seconds, remaining))

    return cycles_completed


def main() -> None:
    args = parse_args()

    log_file = emit_logs_to_file(args)
    trace_id, experiment_id = emit_trace_workflow(
        request_id=args.request_id,
        service=args.service,
        component=args.component,
        phases=args.phases,
        tracking_uri=args.tracking_uri,
        experiment_name=args.experiment_name,
    )
    metrics_cycles = keep_metrics_endpoint_alive(
        port=args.metrics_port,
        wait_seconds=args.metrics_wait_seconds,
        interval_seconds=args.metrics_interval_seconds,
    )
    trace_visible = wait_for_trace_visibility(
        trace_id=trace_id,
        experiment_id=experiment_id,
        timeout_seconds=args.trace_visibility_timeout_seconds,
    )

    print(f"Request ID: {args.request_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Log file: {log_file}")
    print(f"Metrics cycles: {metrics_cycles}")

    if not trace_visible:
        raise SystemExit(
            "The combined validator emitted a trace, but it did not become searchable in MLflow before the timeout."
        )

    print("Trace is searchable in MLflow.")


if __name__ == "__main__":
    main()