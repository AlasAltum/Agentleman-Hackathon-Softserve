from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from urllib import error, parse, request

from .observability import log_event, record_counter, record_histogram, traced_operation

_DEFAULT_NYLAS_BASE_URL = "https://api.us.nylas.com/v3"


class NylasConfigurationError(RuntimeError):
    pass


class NylasClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class NylasConfig:
    api_key: str
    grant_id: str
    sender_email: str
    base_url: str = _DEFAULT_NYLAS_BASE_URL
    email_reply_to: str | None = None
    team_email_recipients: tuple[str, ...] = field(default_factory=tuple)
    include_ticket_url: bool = False
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "NylasConfig":
        api_key = _required_env("NYLAS_API_KEY")
        grant_id = _required_env("NYLAS_GRANT_ID")
        sender_email = _first_nonempty_env("NYLAS_EMAIL_ADDRESS", "NYLAS_EMAIL_ADRESS")
        if not sender_email:
            raise NylasConfigurationError(
                "Missing Nylas configuration: NYLAS_EMAIL_ADDRESS"
            )

        timeout_value = _optional_env("NYLAS_TIMEOUT_SECONDS") or "15"

        return cls(
            api_key=api_key,
            grant_id=grant_id,
            sender_email=sender_email,
            base_url=(_optional_env("NYLAS_BASE_URL") or _DEFAULT_NYLAS_BASE_URL).rstrip("/"),
            email_reply_to=_optional_env("NYLAS_EMAIL_REPLY_TO"),
            team_email_recipients=_csv_env("NYLAS_TEAM_EMAIL_RECIPIENTS"),
            include_ticket_url=_env_bool("NYLAS_INCLUDE_TICKET_URL"),
            timeout_seconds=int(timeout_value),
        )


class NylasClient:
    def __init__(self, config: NylasConfig):
        self.config = config

    def send_email(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        request_id: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "to": [{"email": to}],
            "subject": subject,
            "body": _html_body(body),
            "custom_headers": [
                {"name": "X-Agentleman-Request-ID", "value": request_id}
            ],
        }
        if reply_to:
            payload["reply_to"] = [{"email": reply_to}]

        return self._request_json(
            method="POST",
            path=f"/grants/{parse.quote(self.config.grant_id, safe='')}/messages/send",
            payload=payload,
            request_id=request_id,
            operation="send_email",
        )

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any],
        request_id: str,
        operation: str,
    ) -> dict[str, Any]:
        req = request.Request(
            url=f"{self.config.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method=method,
            headers=_headers(self.config),
        )

        started_at = perf_counter()
        attributes = {
            "operation": operation,
            "provider": "nylas",
            "http.method": method,
            "http.route": path,
        }
        with traced_operation(f"notifications.http.{operation}", request_id, **attributes):
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                    duration_ms = (perf_counter() - started_at) * 1000
                    metric_attributes = {
                        "operation": operation,
                        "provider": "nylas",
                        "status_code": response.status,
                    }
                    record_counter("notifications_http_requests_total", attributes=metric_attributes)
                    record_histogram(
                        "notifications_http_request_duration_ms",
                        duration_ms,
                        attributes=metric_attributes,
                    )
                    log_event(
                        "info",
                        "notifications.http.completed",
                        request_id,
                        provider="nylas",
                        operation=operation,
                        status_code=response.status,
                        duration_ms=round(duration_ms, 2),
                    )
                    return json.loads(raw_body) if raw_body else {}
            except error.HTTPError as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                raw_body = exc.read().decode("utf-8", errors="replace")
                metric_attributes = {
                    "operation": operation,
                    "provider": "nylas",
                    "status_code": exc.code,
                }
                record_counter("notifications_http_failures_total", attributes=metric_attributes)
                record_histogram(
                    "notifications_http_request_duration_ms",
                    duration_ms,
                    attributes=metric_attributes,
                )
                log_event(
                    "error",
                    "notifications.http.failed",
                    request_id,
                    provider="nylas",
                    operation=operation,
                    status_code=exc.code,
                    duration_ms=round(duration_ms, 2),
                    response_body=raw_body[:1200],
                )
                raise NylasClientError(
                    f"Nylas {operation} failed with status {exc.code}: {raw_body[:200]}"
                ) from exc
            except error.URLError as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                metric_attributes = {"operation": operation, "provider": "nylas"}
                record_counter("notifications_http_failures_total", attributes=metric_attributes)
                record_histogram(
                    "notifications_http_request_duration_ms",
                    duration_ms,
                    attributes=metric_attributes,
                )
                log_event(
                    "error",
                    "notifications.http.unreachable",
                    request_id,
                    provider="nylas",
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    error=str(exc.reason),
                )
                raise NylasClientError(f"Nylas {operation} failed: {exc.reason}") from exc


def _headers(config: NylasConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _required_env(name: str) -> str:
    value = _optional_env(name)
    if value:
        return value
    raise NylasConfigurationError(f"Missing Nylas configuration: {name}")


def _first_nonempty_env(*names: str) -> str | None:
    for name in names:
        value = _optional_env(name)
        if value:
            return value
    return None


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    value = _strip_wrapping_quotes(value)
    return value or None


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(
        cleaned
        for item in raw.split(",")
        if (cleaned := _strip_wrapping_quotes(item.strip()))
    )


def _env_bool(name: str) -> bool:
    value = _optional_env(name) or "false"
    return value.lower() in {"1", "true", "yes", "on"}


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _html_body(body: str) -> str:
    escaped = html.escape(body.strip())
    return escaped.replace("\n", "<br />")