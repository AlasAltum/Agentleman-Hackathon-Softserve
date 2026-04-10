import re
import time
from typing import Protocol

from src.guardrails.base import BaseGuardrail
from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.guardrails.validators import (
    CodeExecutionGuardrail,
    InputSizeGuardrail,
    PathTraversalGuardrail,
    SqlInjectionGuardrail,
    XssGuardrail,
)
from src.utils.logger import logger


class GuardrailRule(Protocol):
    name: str

    def check(self, text: str) -> tuple[bool, str]:
        ...


class PromptInjectionGuardrail(BaseGuardrail):
    """Multi-layer prompt injection detection using regex patterns.

    Separates patterns into MALICIOUS (hard block) and SUSPICIOUS (soft flag)
    tiers so legitimate SRE content that happens to contain template syntax
    or role-play language isn't rejected outright.
    """

    # ── Hard-block patterns ───────────────────────────────────────────────
    _MALICIOUS_PATTERNS = [
        # Direct instruction override
        re.compile(r"\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)\b", re.IGNORECASE),
        re.compile(r"\bdisregard\s+(all\s+)?(previous|prior|above|earlier)?\s*(instructions?|prompts?|rules?|context|guidelines?)\b", re.IGNORECASE),
        re.compile(r"\bforget\s+(everything|all|your)\b", re.IGNORECASE),
        re.compile(r"\breset\s+(your\s+)?(instructions?|context|prompt|system)\b", re.IGNORECASE),
        re.compile(r"\boverride\s+(your\s+)?(instructions?|rules?|guidelines?|system)\b", re.IGNORECASE),
        # System prompt extraction
        re.compile(r"\b(show|reveal|print|display|output|repeat|echo)\s+(me\s+)?(your|the|system)\s+(prompt|instructions?|rules?|context)\b", re.IGNORECASE),
        re.compile(r"\bsystem\s*prompt\b", re.IGNORECASE),
        re.compile(r"\bwhat\s+are\s+your\s+(instructions?|rules?|guidelines?)\b", re.IGNORECASE),
        # Role hijacking
        re.compile(r"\byou\s+are\s+now\s+(a|an|the|my)\b", re.IGNORECASE),
        re.compile(r"\bfrom\s+now\s+on\s+(you|act|behave|respond)\b", re.IGNORECASE),
        re.compile(r"\bswitch\s+to\s+\w+\s+mode\b", re.IGNORECASE),
        re.compile(r"\benter\s+(developer|debug|admin|god|sudo|root)\s+mode\b", re.IGNORECASE),
        # Jailbreak markers
        re.compile(r"\bDAN\b"),  # "Do Anything Now"
        re.compile(r"\bjailbreak\b", re.IGNORECASE),
        re.compile(r"\b(do\s+anything\s+now)\b", re.IGNORECASE),
        # Delimiter injection (trying to close/open system blocks)
        re.compile(r"<\|?(system|im_start|im_end|endoftext)\|?>", re.IGNORECASE),
        re.compile(r"\[INST\]|\[/INST\]|\[SYSTEM\]", re.IGNORECASE),
        re.compile(r"```\s*system\b", re.IGNORECASE),
    ]

    # ── Soft-flag patterns ────────────────────────────────────────────────
    _SUSPICIOUS_PATTERNS = [
        re.compile(r"\bact\s+as\s+(a|an|if)\b", re.IGNORECASE),
        re.compile(r"\bpretend\s+(you\s+are|to\s+be|you're)\b", re.IGNORECASE),
        re.compile(r"\brole\s*play\b", re.IGNORECASE),
        re.compile(r"\bsimulate\s+(being|a|an)\b", re.IGNORECASE),
        # Template injection markers (could be legit in SRE logs)
        re.compile(r"\{\{.*\}\}"),
        re.compile(r"\$\{[^}]+\}"),
        # Excessive special characters (obfuscation attempt)
        re.compile(r"[^\w\s]{20,}"),
    ]

    def validate(self, content: str) -> GuardrailsResult:
        malicious: list[str] = []
        for rx in self._MALICIOUS_PATTERNS:
            if rx.search(content):
                malicious.append(rx.pattern)

        if malicious:
            logger.warning(
                "guardrail_blocked",
                phase="guardrails",
                component="PromptInjectionGuardrail",
                status="error",
                threat_level=ThreatLevel.MALICIOUS.value,
                blocked_patterns=malicious,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.MALICIOUS,
                blocked_patterns=malicious,
                message="Input blocked: prompt injection pattern detected.",
            )

        suspicious: list[str] = []
        for rx in self._SUSPICIOUS_PATTERNS:
            if rx.search(content):
                suspicious.append(rx.pattern)

        if suspicious:
            logger.warning(
                "guardrail_flagged",
                phase="guardrails",
                component="PromptInjectionGuardrail",
                status="warning",
                threat_level=ThreatLevel.SUSPICIOUS.value,
                flagged_patterns=suspicious,
            )
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
            message="Input passed prompt injection check.",
        )


# ── Engine ────────────────────────────────────────────────────────────────────


class GuardrailsEngine:
    """Runs all registered guardrails and aggregates results."""

    def __init__(self, guardrails: list[BaseGuardrail] | None = None):
        if guardrails is None:
            self._guardrails: list[BaseGuardrail] = [
                PromptInjectionGuardrail(),
                XssGuardrail(),
                SqlInjectionGuardrail(),
                CodeExecutionGuardrail(),
                PathTraversalGuardrail(),
                InputSizeGuardrail(),
            ]
        else:
            self._guardrails = guardrails

    def add_guardrail(self, guardrail: BaseGuardrail) -> None:
        self._guardrails.append(guardrail)

    def validate(self, content: str) -> GuardrailsResult:
        all_blocked: list[str] = []
        per_threat_levels: list[ThreatLevel] = []

        logger.info("phase_started", phase="guardrails", status="started", component="GuardrailsEngine")
        start_time = time.perf_counter()

        for guardrail in self._guardrails:
            result = guardrail.validate(content)
            all_blocked.extend(result.blocked_patterns)
            per_threat_levels.append(result.threat_level)

            if not result.is_safe:
                logger.warning(
                    "guardrail_blocked",
                    phase="guardrails",
                    component=guardrail.__class__.__name__,
                    status="error",
                    threat_level=result.threat_level.value,
                    blocked_patterns=result.blocked_patterns,
                )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Aggregate threat level
        if ThreatLevel.MALICIOUS in per_threat_levels:
            max_threat = ThreatLevel.MALICIOUS
        elif ThreatLevel.SUSPICIOUS in per_threat_levels:
            max_threat = ThreatLevel.SUSPICIOUS
        else:
            max_threat = ThreatLevel.SAFE

        is_safe = max_threat == ThreatLevel.SAFE

        logger.info(
            "phase_completed",
            phase="guardrails",
            status="completed",
            component="GuardrailsEngine",
            threat_level=max_threat.value,
            blocked_patterns=all_blocked,
            latency_ms=latency_ms,
        )

        return GuardrailsResult(
            is_safe=is_safe,
            threat_level=max_threat,
            blocked_patterns=all_blocked,
            message=(
                "All guardrails passed."
                if is_safe
                else f"Guardrails triggered ({max_threat.value}): {', '.join(all_blocked[:5])}"
            ),
        )
