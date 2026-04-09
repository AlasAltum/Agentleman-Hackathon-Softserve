import os
import time
from functools import wraps
from typing import Any, Callable, Optional
from contextlib import contextmanager

import mlflow
from mlflow.entities import SpanType

_MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "sre-workflow")
_MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
_MLFLOW_AUTOLOG_ENABLED = os.getenv("MLFLOW_AUTOLOG_ENABLED", "true").lower() == "true"

_configured = False

def configure_mlflow() -> None:
    """Configure MLflow tracking and enable LlamaIndex autologging."""
    global _configured
    if not _configured:
        mlflow.set_tracking_uri(_MLFLOW_TRACKING_URI)
        mlflow.set_experiment(_MLFLOW_EXPERIMENT_NAME)
        
        if _MLFLOW_AUTOLOG_ENABLED:
            try:
                mlflow.llama_index.autolog(log_traces=True, disable=False, silent=False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"MLflow LlamaIndex autolog failed: {e}")
        
        _configured = True

@contextmanager
def start_run(request_id: str, run_name: Optional[str] = None):
    """Context manager for MLflow run with request_id tracking."""
    run = mlflow.start_run(run_name=run_name or request_id)
    mlflow.log_param("request_id", request_id)
    mlflow.log_param("service", "backend")
    try:
        yield run
    finally:
        mlflow.end_run()

def log_span(phase: str, status: str = "started", **kwargs: Any) -> None:
    with mlflow.start_span(name=phase, span_type=SpanType.CHAIN) as span:
        span.set_attributes({"phase": phase, "status": status, **kwargs})

def trace_phase(phase: str, span_type: SpanType = SpanType.CHAIN):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            with mlflow.start_span(name=phase, span_type=span_type) as span:
                try:
                    result = await func(*args, **kwargs)
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    span.set_attributes({
                        "phase": phase,
                        "status": "success",
                        "latency_ms": latency_ms
                    })
                    return result
                except Exception as e:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    span.set_attributes({
                        "phase": phase,
                        "status": "error",
                        "error_type": type(e).__name__,
                        "latency_ms": latency_ms
                    })
                    span.record_exception(e)
                    raise
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            with mlflow.start_span(name=phase, span_type=span_type) as span:
                try:
                    result = func(*args, **kwargs)
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    span.set_attributes({
                        "phase": phase,
                        "status": "success",
                        "latency_ms": latency_ms
                    })
                    return result
                except Exception as e:
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    span.set_attributes({
                        "phase": phase,
                        "status": "error",
                        "error_type": type(e).__name__,
                        "latency_ms": latency_ms
                    })
                    span.record_exception(e)
                    raise
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

def log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: int,
    provider: str = "unknown"
) -> None:
    mlflow.log_metric("prompt_tokens", prompt_tokens)
    mlflow.log_metric("completion_tokens", completion_tokens)
    mlflow.log_metric("total_tokens", total_tokens)
    mlflow.log_metric("latency_ms", latency_ms)
    mlflow.log_param("model", model)
    mlflow.log_param("provider", provider)

def log_tool_call(tool_name: str, status: str, latency_ms: int) -> None:
    mlflow.log_metric(f"tool_{tool_name}_latency_ms", latency_ms)
    mlflow.log_param(f"tool_{tool_name}_status", status)

def log_ticket_operation(operation: str, status: str) -> None:
    mlflow.log_param(f"ticket_{operation}_status", status)