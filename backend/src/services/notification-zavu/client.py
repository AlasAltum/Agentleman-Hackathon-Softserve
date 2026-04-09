from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from urllib import error, request

from .observability import log_event, record_counter, record_histogram, traced_operation

_DEFAULT_ZAVU_BASE_URL = "https://api.zavu.dev"


class ZavuConfigurationError(RuntimeError):
    pass


class ZavuClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZavuConfig:
    api_key: str
    base_url: str = _DEFAULT_ZAVU_BASE_URL
    email_reply_to: str | None = None
    sender_id: str | None = None
    include_ticket_url: bool = False
    team_email_recipients: tuple[str, ...] = field(default_factory=tuple)
    team_telegram_chat_ids: tuple[str, ...] = field(default_factory=tuple)
    reporter_telegram_map: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "ZavuConfig":
        api_key = os.getenv("ZAVU_API_KEY", "").strip() or os.getenv("ZAVUDEV_API_KEY", "").strip()
        if not api_key:
            raise ZavuConfigurationError("Missing Zavu configuration: ZAVU_API_KEY")

        reporter_map_raw = os.getenv("ZAVU_REPORTER_TELEGRAM_MAP", "").strip()
        reporter_map: dict[str, str] = {}
        if reporter_map_raw:
            try:
                parsed = json.loads(reporter_map_raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - env parsing
                raise ZavuConfigurationError("ZAVU_REPORTER_TELEGRAM_MAP must be valid JSON") from exc
            if not isinstance(parsed, dict):  # pragma: no cover - env parsing
                raise ZavuConfigurationError("ZAVU_REPORTER_TELEGRAM_MAP must be a JSON object")
            reporter_map = {
                str(key).strip().lower(): str(value).strip()
                for key, value in parsed.items()
                if str(key).strip() and str(value).strip()
            }

        return cls(
            api_key=api_key,
            base_url=(os.getenv("ZAVU_BASE_URL", _DEFAULT_ZAVU_BASE_URL).strip() or _DEFAULT_ZAVU_BASE_URL).rstrip("/"),
            email_reply_to=_optional_env("ZAVU_EMAIL_REPLY_TO"),
            sender_id=_optional_env("ZAVU_SENDER_ID"),
            include_ticket_url=_env_bool("ZAVU_INCLUDE_TICKET_URL"),
            team_email_recipients=_csv_env("ZAVU_TEAM_EMAIL_RECIPIENTS"),
            team_telegram_chat_ids=_csv_env("ZAVU_TEAM_TELEGRAM_CHAT_IDS"),
            reporter_telegram_map=reporter_map,
            timeout_seconds=int(os.getenv("ZAVU_TIMEOUT_SECONDS", "15").strip() or "15"),
        )


class ZavuClient:
    def __init__(self, config: ZavuConfig):
        self.config = config

    def send_message(
        self,
        *,
        to: str,
        channel: str,
        text: str,
        request_id: str,
        subject: str | None = None,
        html_body: str | None = None,
        reply_to: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "to": to,
            "channel": channel,
            "text": text,
        }
        if subject:
            payload["subject"] = subject
        if html_body:
            payload["htmlBody"] = html_body
        if reply_to:
            payload["replyTo"] = reply_to
        if idempotency_key:
            payload["idempotencyKey"] = idempotency_key

        return self._request_json(
            method="POST",
            path="/v1/messages",
            payload=payload,
            request_id=request_id,
            operation=f"send_{channel}",
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
            "http.method": method,
            "http.route": path,
        }
        with traced_operation(f"zavu.http.{operation}", request_id, **attributes):
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                    duration_ms = (perf_counter() - started_at) * 1000
                    metric_attributes = {
                        "operation": operation,
                        "status_code": response.status,
                    }
                    record_counter("zavu_http_requests_total", attributes=metric_attributes)
                    record_histogram(
                        "zavu_http_request_duration_ms",
                        duration_ms,
                        attributes=metric_attributes,
                    )
                    log_event(
                        "info",
                        "zavu.http.completed",
                        request_id,
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
                    "status_code": exc.code,
                }
                record_counter("zavu_http_failures_total", attributes=metric_attributes)
                record_histogram(
                    "zavu_http_request_duration_ms",
                    duration_ms,
                    attributes=metric_attributes,
                )
                log_event(
                    "error",
                    "zavu.http.failed",
                    request_id,
                    operation=operation,
                    status_code=exc.code,
                    duration_ms=round(duration_ms, 2),
                    response_body=raw_body[:1200],
                )
                raise ZavuClientError(
                    f"Zavu {operation} failed with status {exc.code}: {raw_body[:200]}"
                ) from exc
            except error.URLError as exc:
                duration_ms = (perf_counter() - started_at) * 1000
                record_counter("zavu_http_failures_total", attributes={"operation": operation})
                record_histogram(
                    "zavu_http_request_duration_ms",
                    duration_ms,
                    attributes={"operation": operation},
                )
                log_event(
                    "error",
                    "zavu.http.unreachable",
                    request_id,
                    operation=operation,
                    duration_ms=round(duration_ms, 2),
                    error=str(exc.reason),
                )
                raise ZavuClientError(f"Zavu {operation} failed: {exc.reason}") from exc


def _headers(config: ZavuConfig) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if config.sender_id:
        headers["Zavu-Sender"] = config.sender_id
    return headers


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


def _env_bool(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}