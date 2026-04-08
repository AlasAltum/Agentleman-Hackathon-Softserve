from __future__ import annotations

import argparse
import os
import time
from typing import Sequence

import mlflow
from mlflow.entities import SpanType

from emit_logs import DEFAULT_PHASES, generate_request_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a manual MLflow trace for local observability validation.",
    )
    parser.add_argument(
        "--request-id",
        default=generate_request_id(),
        help="Correlation identifier stored in the trace tags and span attributes.",
    )
    parser.add_argument(
        "--tracking-uri",
        default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
        help="MLflow tracking server URI.",
    )
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", "observability-local"),
        help="MLflow experiment used for the trace.",
    )
    parser.add_argument(
        "--service",
        default="observability-test",
        help="Stable service tag stored on the trace.",
    )
    parser.add_argument(
        "--component",
        default="trace-emitter",
        help="Stable component tag stored on the trace.",
    )
    parser.add_argument(
        "--phases",
        nargs="+",
        default=list(DEFAULT_PHASES),
        help="Stable workflow phases represented as nested spans.",
    )
    parser.add_argument(
        "--visibility-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait while checking that the trace is searchable in MLflow.",
    )
    return parser.parse_args()


def configure_tracking(tracking_uri: str, experiment_name: str) -> str:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise RuntimeError(f"Unable to resolve MLflow experiment: {experiment_name}")
    return experiment.experiment_id


def emit_trace_workflow(
    request_id: str,
    service: str,
    component: str,
    phases: Sequence[str],
    tracking_uri: str,
    experiment_name: str,
) -> tuple[str, str]:
    experiment_id = configure_tracking(tracking_uri, experiment_name)
    phase_outputs: list[dict[str, object]] = []

    with mlflow.start_span(
        name="incident_triage_smoke_test",
        span_type=SpanType.CHAIN,
    ) as root_span:
        trace_id = mlflow.get_active_trace_id()

        mlflow.update_current_trace(
            tags={
                "service": service,
                "component": component,
                "request_id": request_id,
                "status": "success",
                "phase_sequence": ",".join(phases),
            },
            metadata={
                "service": service,
                "component": component,
                "request_id": request_id,
                "status": "success",
            },
        )

        root_span.set_inputs(
            {
                "request_id": request_id,
                "service": service,
                "component": component,
                "phase_count": len(phases),
            }
        )
        root_span.set_attribute("service", service)
        root_span.set_attribute("component", component)
        root_span.set_attribute("request_id", request_id)
        root_span.set_attribute("status", "success")

        for index, phase in enumerate(phases, start=1):
            phase_output = {
                "phase": phase,
                "status": "success",
                "sequence": index,
                "summary": f"{phase} phase completed",
            }

            with mlflow.start_span(
                name=f"{phase}_phase",
                span_type=SpanType.CHAIN,
            ) as phase_span:
                phase_span.set_inputs(
                    {
                        "request_id": request_id,
                        "phase": phase,
                        "sequence": index,
                    }
                )
                phase_span.set_outputs(phase_output)
                phase_span.set_attribute("service", service)
                phase_span.set_attribute("component", component)
                phase_span.set_attribute("phase", phase)
                phase_span.set_attribute("status", "success")
                phase_span.set_attribute("sequence", index)

            phase_outputs.append(phase_output)

        root_span.set_outputs(
            {
                "request_id": request_id,
                "service": service,
                "status": "success",
                "phases": phase_outputs,
            }
        )

    return trace_id, experiment_id


def wait_for_trace_visibility(
    trace_id: str,
    experiment_id: str,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        traces = mlflow.search_traces(
            experiment_ids=[experiment_id],
            max_results=25,
            include_spans=False,
            return_type="list",
        )
        if any(trace.info.trace_id == trace_id for trace in traces):
            return True
        time.sleep(1.0)

    return False


def main() -> None:
    args = parse_args()
    trace_id, experiment_id = emit_trace_workflow(
        request_id=args.request_id,
        service=args.service,
        component=args.component,
        phases=args.phases,
        tracking_uri=args.tracking_uri,
        experiment_name=args.experiment_name,
    )
    is_visible = wait_for_trace_visibility(
        trace_id=trace_id,
        experiment_id=experiment_id,
        timeout_seconds=args.visibility_timeout_seconds,
    )

    print(f"Trace ID: {trace_id}")
    print(f"Experiment: {args.experiment_name}")
    print(f"Request ID: {args.request_id}")

    if not is_visible:
        raise SystemExit(
            "Trace was emitted but did not become searchable in MLflow before the timeout."
        )

    print("Trace is searchable in MLflow.")


if __name__ == "__main__":
    main()