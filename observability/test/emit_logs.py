from __future__ import annotations

import argparse
import sys
import uuid

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
    return parser.parse_args()


def emit_logs(args: argparse.Namespace) -> None:
    logger = structlog.get_logger("observability.test.logs").bind(
        request_id=args.request_id,
        service=args.service,
        component=args.component,
    )

    for index, phase in enumerate(args.phases, start=1):
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


def main() -> None:
    configure_logging()
    emit_logs(parse_args())


if __name__ == "__main__":
    main()