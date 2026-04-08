from abc import ABC, abstractmethod
from typing import Protocol

from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.utils.logger import logger


class GuardrailRule(Protocol):
    name: str

    def check(self, text: str) -> tuple[bool, str]:
        ...


class BaseGuardrail(ABC):
    @abstractmethod
    def validate(self, content: str) -> GuardrailsResult:
        ...


class PromptInjectionGuardrail(BaseGuardrail):
    INJECTION_PATTERNS = [
        "ignore previous instructions",
        "disregard all",
        "system prompt",
        "you are now",
        "<script>",
        "{{",
        "act as",
        "pretend you are",
        "forget everything",
    ]

    def validate(self, content: str) -> GuardrailsResult:
        text_lower = content.lower()
        blocked = []

        for pattern in self.INJECTION_PATTERNS:
            if pattern in text_lower:
                blocked.append(pattern)

        if blocked:
            logger.warning("[guardrails] Blocked_patterns=%s", blocked)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=blocked,
                message="Input blocked by guardrails: suspicious pattern detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="Input passed safety check.",
        )


class GuardrailsEngine:
    def __init__(self, guardrails: list[BaseGuardrail] | None = None):
        self._guardrails = guardrails or [PromptInjectionGuardrail()]

    def add_guardrail(self, guardrail: BaseGuardrail) -> None:
        self._guardrails.append(guardrail)

    def validate(self, content: str) -> GuardrailsResult:
        all_blocked: list[str] = []
        max_threat = ThreatLevel.SAFE

        for guardrail in self._guardrails:
            result = guardrail.validate(content)
            all_blocked.extend(result.blocked_patterns)

            if result.threat_level.value > max_threat.value:
                max_threat = result.threat_level

            if not result.is_safe:
                logger.warning(
                    "[guardrails] Guardrail=%s blocked content",
                    guardrail.__class__.__name__,
                )

        is_safe = len(all_blocked) == 0
        return GuardrailsResult(
            is_safe=is_safe,
            threat_level=max_threat,
            blocked_patterns=all_blocked,
            message="Input blocked by guardrails." if not is_safe else "Input passed all checks.",
        )