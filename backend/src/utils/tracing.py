import os
import time
from functools import wraps
from typing import Any, Callable, Optional
from contextlib import contextmanager

import mlflow
from mlflow.entities import SpanType

from src.utils.logger import _RunLogCapture, _active_capture

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
    """Wraps the LlamaIndex workflow execution with structlog capture.

    Tagging is done inside the first workflow step via mlflow.update_current_trace()
    while the LlamaIndex autolog trace is still active. This context manager only
    manages the structlog capture buffer and log persistence.

    Also writes the full structlog capture to disk as logs/trace_<id8>.jsonl.
    """
    capture = _RunLogCapture()
    token = _active_capture.set(capture)
    try:
        yield
    finally:
        _write_logs_to_disk(capture, request_id)
        _active_capture.reset(token)
        capture.clear()


def _write_logs_to_disk(capture: _RunLogCapture, request_id: str) -> None:
    """Persist the full structlog capture to a per-request JSONL file."""
    if not capture.events:
        return
    logs_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    out_path = os.path.join(logs_dir, f"trace_{request_id[:8]}.jsonl")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(capture.as_jsonlines())
    except Exception:
        pass

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