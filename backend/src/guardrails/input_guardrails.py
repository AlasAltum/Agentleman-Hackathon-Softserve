from typing import Protocol

from src.guardrails.base import BaseGuardrail
from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.guardrails.validators import SqlInjectionGuardrail, XssGuardrail
from src.utils.logger import logger


class GuardrailRule(Protocol):
    name: str

    def check(self, text: str) -> tuple[bool, str]:
        ...


class PromptInjectionGuardrail(BaseGuardrail):
    # Clear attack intent — hard block
    MALICIOUS_PATTERNS = [
        "ignore previous instructions",
        "disregard all",
        "system prompt",
        "forget everything",
    ]
    # Ambiguous — could appear in legitimate SRE logs/templates, soft-flag only
    SUSPICIOUS_PATTERNS = [
        "{{",
        "act as",
        "pretend you are",
        "you are now",
    ]

    def validate(self, content: str) -> GuardrailsResult:
        text_lower = content.lower()

        malicious = [p for p in self.MALICIOUS_PATTERNS if p in text_lower]
        if malicious:
            logger.warning("[guardrails] Malicious injection patterns=%s", malicious)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=malicious,
                message="Input blocked by guardrails: malicious injection pattern detected.",
            )

        suspicious = [p for p in self.SUSPICIOUS_PATTERNS if p in text_lower]
        if suspicious:
            logger.warning("[guardrails] Suspicious injection patterns=%s", suspicious)
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.SUSPICIOUS,
                blocked_patterns=suspicious,
                message="Input flagged as suspicious: potential injection pattern detected.",
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message="Input passed safety check.",
        )


class GuardrailsEngine:
    def __init__(self, guardrails: list[BaseGuardrail] | None = None):
        if guardrails is None:
            self._guardrails = [
                PromptInjectionGuardrail(),
                XssGuardrail(),
                SqlInjectionGuardrail(),
            ]
        else:
            self._guardrails = guardrails

    def add_guardrail(self, guardrail: BaseGuardrail) -> None:
        self._guardrails.append(guardrail)

    def validate(self, content: str) -> GuardrailsResult:
        all_blocked: list[str] = []
        per_threat_levels: list[ThreatLevel] = []

        for guardrail in self._guardrails:
            result = guardrail.validate(content)
            all_blocked.extend(result.blocked_patterns)
            per_threat_levels.append(result.threat_level)

            if not result.is_safe:
                logger.warning(
                    "[guardrails] Guardrail=%s blocked content",
                    guardrail.__class__.__name__,
                )

        # Aggregate threat level without relying on str ordering
        if ThreatLevel.MALICIOUS in per_threat_levels:
            max_threat = ThreatLevel.MALICIOUS
        elif ThreatLevel.SUSPICIOUS in per_threat_levels:
            max_threat = ThreatLevel.SUSPICIOUS
        else:
            max_threat = ThreatLevel.SAFE

        is_safe = len(all_blocked) == 0
        return GuardrailsResult(
            is_safe=is_safe,
            threat_level=max_threat,
            blocked_patterns=all_blocked,
            message="Input blocked by guardrails." if not is_safe else "Input passed all checks.",
        )