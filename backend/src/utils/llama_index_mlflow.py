"""LlamaIndex MLflow integration for automatic tracing.

This module configures MLflow to automatically trace all LlamaIndex operations:
- Workflow execution
- LLM calls
- Embedding operations
- Tool calls

Based on: https://mlflow.org/docs/latest/genai/flavors/llama-index.html

Usage:
    from src.utils.llama_index_mlflow import configure_mlflow_tracing
    
    configure_mlflow_tracing()  # Call once at startup
    
Or automatically via environment:
    export MLFLOW_AUTOLOG_ENABLED=true
    export MLFLOW_TRACKING_URI=http://localhost:5001
    export MLFLOW_EXPERIMENT_NAME=sre-workflow
"""

import os
from typing import Optional

import mlflow

_MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "sre-workflow")
_MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
_MLFLOW_AUTOLOG_ENABLED = os.getenv("MLFLOW_AUTOLOG_ENABLED", "true").lower() == "true"

_configured = False


def configure_mlflow_tracing(
    tracking_uri: Optional[str] = None,
    experiment_name: Optional[str] = None,
    enable_autolog: bool = True,
) -> None:
    """Configure MLflow for LlamaIndex tracing.
    
    Args:
        tracking_uri: MLflow tracking server URI (default: env MLFLOW_TRACKING_URI)
        experiment_name: MLflow experiment name (default: env MLFLOW_EXPERIMENT_NAME)
        enable_autolog: Enable automatic logging of LlamaIndex operations
    
    This enables:
        - Automatic tracing of LlamaIndex workflows
        - Span tracking for LLM calls
        - Token usage logging
        - Input/output logging
    """
    global _configured
    
    if _configured:
        return
    
    tracking_uri = tracking_uri or _MLFLOW_TRACKING_URI
    experiment_name = experiment_name or _MLFLOW_EXPERIMENT_NAME
    
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    
    if enable_autolog and _MLFLOW_AUTOLOG_ENABLED:
        try:
            mlflow.llama_index.autolog(log_traces=True, disable=False, silent=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MLflow LlamaIndex autolog failed: {e}")
    
    _configured = True


def get_mlflow_run(request_id: str, run_name: Optional[str] = None):
    """Get or create an MLflow run for a request.
    
    Args:
        request_id: Unique request identifier (UUIDv7)
        run_name: Optional run name (default: uses request_id)
    
    Returns:
        MLflow run context manager
    """
    from contextlib import contextmanager
    
    @contextmanager
    def run_context():
        run = mlflow.start_run(run_name=run_name or request_id)
        mlflow.log_param("request_id", request_id)
        mlflow.log_param("service", "backend")
        mlflow.log_param("component", "llama_index_workflow")
        try:
            yield run
        finally:
            mlflow.end_run()
    
    return run_context()


def log_llm_interaction(
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: int,
    request_id: Optional[str] = None,
) -> None:
    """Log LLM interaction details to MLflow.
    
    Args:
        model: Model name (e.g., "gemini-2.5-flash")
        provider: Provider name (e.g., "google")
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_tokens: Total tokens used
        latency_ms: Latency in milliseconds
        request_id: Optional request ID for correlation
    """
    mlflow.log_metric("prompt_tokens", prompt_tokens)
    mlflow.log_metric("completion_tokens", completion_tokens)
    mlflow.log_metric("total_tokens", total_tokens)
    mlflow.log_metric("latency_ms", latency_ms)
    mlflow.log_param("model", model)
    mlflow.log_param("provider", provider)
    
    if request_id:
        mlflow.set_tag("request_id", request_id)


def log_workflow_event(
    event_type: str,
    phase: str,
    status: str,
    **kwargs,
) -> None:
    """Log a workflow event to MLflow.
    
    Args:
        event_type: Type of event (e.g., "phase_start", "phase_end")
        phase: Workflow phase name
        status: Status (e.g., "started", "success", "error")
        **kwargs: Additional attributes to log
    """
    with mlflow.start_span(name=f"{phase}_{event_type}", span_type="CHAIN") as span:
        attributes = {
            "event_type": event_type,
            "phase": phase,
            "status": status,
            **kwargs
        }
        span.set_attributes(attributes)


def is_configured() -> bool:
    """Check if MLflow tracing is configured."""
    return _configured


configure_mlflow_tracing()