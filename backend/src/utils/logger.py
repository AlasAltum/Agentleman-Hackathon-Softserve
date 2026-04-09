import logging
import sys
from uuid_extensions import uuid7
import time
from functools import wraps
from typing import Any, Callable

import structlog

from dotenv import load_dotenv

load_dotenv()

def generate_request_id() -> str:
    return str(uuid7())

def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
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