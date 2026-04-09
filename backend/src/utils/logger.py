import contextvars
import json
import logging
import sys
from uuid_extensions import uuid7
import time
from functools import wraps
from typing import Any, Callable

import structlog

# ---------------------------------------------------------------------------
# MLflow log capture — one capture buffer per async context (request-scoped)
# ---------------------------------------------------------------------------

class _RunLogCapture:
    """Accumulates structlog events during an MLflow run."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    def append(self, event: dict) -> None:
        self._events.append(event)

    def as_jsonlines(self) -> str:
        return "\n".join(json.dumps(e) for e in self._events)

    def clear(self) -> None:
        self._events.clear()

    @property
    def events(self) -> list[dict]:
        return self._events


# ContextVar so concurrent async requests each get their own capture buffer
_active_capture: contextvars.ContextVar[_RunLogCapture | None] = contextvars.ContextVar(
    "mlflow_log_capture", default=None
)


def _capture_processor(_logger: Any, _method: str, event_dict: dict) -> dict:
    """Structlog processor that mirrors events to the active MLflow capture buffer."""
    capture = _active_capture.get()
    if capture is not None:
        capture.append(dict(event_dict))  # shallow copy — don't mutate the pipeline dict
    return event_dict


def generate_request_id() -> str:
    return str(uuid7())

def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger.addHandler(stdout_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _capture_processor,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

configure_logging()

logger = structlog.get_logger("estampapro")

def bind_request_context(request_id: str, **kwargs: Any) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        service="backend",
        **kwargs
    )

def log_phase_start(phase: str, **kwargs: Any) -> None:
    logger.info("phase_started", phase=phase, status="started", **kwargs)

def log_phase_success(phase: str, latency_ms: int, **kwargs: Any) -> None:
    logger.info(
        "phase_completed",
        phase=phase,
        status="success",
        latency_ms=latency_ms,
        **kwargs
    )

def log_phase_failure(phase: str, error_type: str, **kwargs: Any) -> None:
    logger.error(
        "phase_failed",
        phase=phase,
        status="error",
        error_type=error_type,
        exc_info=True,
        **kwargs
    )

def phase_logger(phase: str):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            log_phase_start(phase)
            try:
                result = await func(*args, **kwargs)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                log_phase_success(phase, latency_ms=latency_ms)
                return result
            except Exception as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                log_phase_failure(phase, error_type=type(e).__name__, latency_ms=latency_ms)
                raise
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            log_phase_start(phase)
            try:
                result = func(*args, **kwargs)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                log_phase_success(phase, latency_ms=latency_ms)
                return result
            except Exception as e:
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                log_phase_failure(phase, error_type=type(e).__name__, latency_ms=latency_ms)
                raise
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator