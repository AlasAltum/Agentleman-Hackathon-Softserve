from __future__ import annotations

import argparse
import time

from prometheus_client import Counter, Histogram, start_http_server


PHASE_SAMPLES = (
    ("ingest", "success", 0.08),
    ("classify", "success", 0.35),
    ("notify", "success", 0.12),
)


PHASE_RUNS_TOTAL = Counter(
    "observability_test_phase_runs_total",
    "Total sample phase executions emitted by the observability smoke-test script.",
    labelnames=("phase", "status"),
)

PHASE_DURATION_SECONDS = Histogram(
    "observability_test_phase_duration_seconds",
    "Sample phase latency emitted by the observability smoke-test script.",
    labelnames=("phase",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expose Prometheus metrics for local observability validation.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9464,
        help="Port for the /metrics HTTP endpoint.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="Seconds between sample emission cycles.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of sample cycles to emit. Use 0 to run until interrupted.",
    )
    return parser.parse_args()


def emit_sample_cycle() -> None:
    for phase, status, duration_seconds in PHASE_SAMPLES:
        PHASE_RUNS_TOTAL.labels(phase=phase, status=status).inc()
        PHASE_DURATION_SECONDS.labels(phase=phase).observe(duration_seconds)


def main() -> None:
    args = parse_args()
    start_http_server(args.port)
    print(
        f"Serving Prometheus metrics on http://0.0.0.0:{args.port}/metrics",
        flush=True,
    )

    cycles_completed = 0

    try:
        while args.iterations == 0 or cycles_completed < args.iterations:
            emit_sample_cycle()
            cycles_completed += 1
            print(f"Emitted metrics cycle {cycles_completed}", flush=True)

            if args.iterations != 0 and cycles_completed >= args.iterations:
                break

            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("Stopping metrics emitter.", flush=True)


if __name__ == "__main__":
    main()