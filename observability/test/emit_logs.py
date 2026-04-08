from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Sequence, TextIO

import structlog


DEFAULT_PHASES = ("ingest", "classify", "notify")


def generate_request_id() -> str:
    generator = getattr(uuid, "uuid7", uuid.uuid4)
    return str(generator())


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def build_logger(target: TextIO):
    return structlog.wrap_logger(
        structlog.PrintLogger(target),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
    )


def emit_phase_logs(
    request_id: str,
    service: str,
    component: str,
    phases: Sequence[str],
    target: TextIO,
) -> None:
    logger = build_logger(target).bind(
        request_id=request_id,
        service=service,
        component=component,
    )

    for index, phase in enumerate(phases, start=1):
        logger.info(
            "phase_started",
            phase=phase,
            status="started",
            sequence=index,
        )
        logger.info(
            "phase_completed",
            phase=phase,
            status="success",
            sequence=index,
            latency_ms=index * 100,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit structured JSON logs for Loki and Grafana validation.",
    )
    parser.add_argument(
        "--request-id",
        default=generate_request_id(),
        help="Correlation identifier reused across emitted log records.",
    )
    parser.add_argument(
        "--service",
        default="observability-test",
        help="Service name stored in each log line.",
    )
    parser.add_argument(
        "--component",
        default="log-emitter",
        help="Component name stored in each log line.",
    )
    parser.add_argument(
        "--phases",
        nargs="+",
        default=list(DEFAULT_PHASES),
        help="Stable workflow phases to emit.",
    )
    parser.add_argument(
        "--output-file",
        help="Optional file path to write UTF-8 encoded JSON logs directly.",
    )
    return parser.parse_args()


def emit_logs(args: argparse.Namespace, target: TextIO) -> None:
    emit_phase_logs(
        request_id=args.request_id,
        service=args.service,
        component=args.component,
        phases=args.phases,
        target=target,
    )


def main() -> None:
    configure_logging()
    args = parse_args()

    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            emit_logs(args, handle)
        return

    emit_logs(args, sys.stdout)


if __name__ == "__main__":
    main()