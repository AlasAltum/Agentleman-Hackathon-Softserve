from __future__ import annotations

import dataclasses
import json
import uuid
from contextlib import contextmanager
from enum import Enum
from typing import Any, Iterator

try:
    import structlog
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local envs
    structlog = None

try:
    from opentelemetry import metrics, trace
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local envs
    metrics = None
    trace = None

from src.utils.logger import logger

_TRACER = trace.get_tracer("src.services.notifications") if trace else None
_METER = metrics.get_meter("src.services.notifications") if metrics else None
_COUNTERS: dict[str, Any] = {}
_HISTOGRAMS: dict[str, Any] = {}


def new_request_id() -> str:
    generator = getattr(uuid, "uuid7", uuid.uuid4)
    return str(generator())


def log_event(level: str, event: str, request_id: str, **fields: Any) -> None:
    payload = {"event": event, "request_id": request_id}
    payload.update({key: _serialise(value) for key, value in fields.items()})
    message = _render_json(payload)
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(message)


@contextmanager
def traced_operation(name: str, request_id: str, **attributes: Any) -> Iterator[Any | None]:
    if _TRACER is None:
        yield None
        return

    with _TRACER.start_as_current_span(name) as span:
        span.set_attribute("request.id", request_id)
        for key, value in _normalise_attributes(attributes).items():
            span.set_attribute(key, value)
        yield span


def record_counter(name: str, amount: int = 1, attributes: dict[str, Any] | None = None) -> None:
    if _METER is None:
        return

    counter = _COUNTERS.get(name)
    if counter is None:
        counter = _METER.create_counter(name)
        _COUNTERS[name] = counter
    counter.add(amount, _normalise_attributes(attributes))


def record_histogram(name: str, value: float, attributes: dict[str, Any] | None = None) -> None:
    if _METER is None:
        return

    histogram = _HISTOGRAMS.get(name)
    if histogram is None:
        histogram = _METER.create_histogram(name)
        _HISTOGRAMS[name] = histogram
    histogram.record(value, _normalise_attributes(attributes))


def _normalise_attributes(attributes: dict[str, Any] | None) -> dict[str, Any]:
    if not attributes:
        return {}

    normalised: dict[str, Any] = {}
    for key, value in attributes.items():
        serialised = _serialise(value)
        if isinstance(serialised, (bool, int, float, str)):
            normalised[key] = serialised
        else:
            normalised[key] = _render_json(serialised)
    return normalised


def _serialise(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise(item) for item in value]
    return str(value)


def _render_json(payload: Any) -> str:
    if structlog is not None:
        renderer = structlog.processors.JSONRenderer(sort_keys=True)
        return renderer(None, None, payload)
    return json.dumps(payload, sort_keys=True, default=str)