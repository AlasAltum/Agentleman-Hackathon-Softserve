from src.guardrails.base import BaseGuardrail
from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.utils.logger import logger


class XssGuardrail(BaseGuardrail):
    XSS_PATTERNS = [
        "<script>",
        "javascript:",
        "onerror=",
        "onload=",
        "<img",
        "<svg",
        "alert(",
    ]

    def validate(self, content: str) -> GuardrailsResult:
        blocked = [p for p in self.XSS_PATTERNS if p.lower() in content.lower()]

        if blocked:
            logger.warning("xss_patterns_detected", patterns=blocked)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential XSS attack detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No XSS patterns detected.",
        )


class SqlInjectionGuardrail(BaseGuardrail):
    SQL_PATTERNS = [
        "SELECT * FROM",
        "DROP TABLE",
        "--",
        "'; --",
        "UNION SELECT",
        "OR 1=1",
        "exec(",
    ]

    def validate(self, content: str) -> GuardrailsResult:
        blocked = [p for p in self.SQL_PATTERNS if p.lower() in content.lower()]

        if blocked:
            logger.warning("sql_injection_patterns_detected", patterns=blocked)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Potential SQL injection detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="No SQL injection patterns detected.",
        )


class ContentTypeGuardrail(BaseGuardrail):
    def __init__(self, allowed_mime_types: list[str] | None = None):
        self._allowed_mime_types = allowed_mime_types or [
            # Text / logs
            "text/plain",
            "text/log",
            # Structured data
            "application/json",
            "text/csv",
            "application/csv",
            # Images
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
        ]

    def validate(self, content: str, mime_type: str | None = None) -> GuardrailsResult:
        if mime_type is None:
            return GuardrailsResult(
                is_safe=True,
                threat_level=ThreatLevel.SAFE,
                blocked_patterns=[],
                message="No file content to validate.",
            )

        if mime_type not in self._allowed_mime_types:
            logger.warning("disallowed_mime_type", mime_type=mime_type)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.SUSPICIOUS,
                blocked_patterns=[f"mime:{mime_type}"],
                message=f"Disallowed MIME type: {mime_type}",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="MIME type allowed.",
        )