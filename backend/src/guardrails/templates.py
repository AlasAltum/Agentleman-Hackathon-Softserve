from dataclasses import dataclass
from typing import Callable

from src.guardrails.input_guardrails import BaseGuardrail
from src.guardrails.models import GuardrailsResult, ThreatLevel
from src.utils.logger import logger


@dataclass
class GuardrailConfig:
    name: str
    patterns: list[str]
    on_match: Callable[[str, list[str]], str] | None = None


class TemplateGuardrail(BaseGuardrail):
    def __init__(self, config: GuardrailConfig):
        self.config = config
        self._patterns = [p.lower() for p in config.patterns]

    def validate(self, content: str) -> GuardrailsResult:
        text_lower = content.lower()
        blocked = [p for p in self._patterns if p in text_lower]

        if blocked:
            message = (
                self.config.on_match(content, blocked)
                if self.config.on_match
                else f"Blocked by {self.config.name}: patterns detected."
            )
            logger.warning(
                "template_guardrail_blocked",
                template=self.config.name,
                patterns=blocked,
            )
            return GuardrailsResult(
                is_safe=False,
                threat_level=ThreatLevel.SUSPICIOUS,
                blocked_patterns=blocked,
                message=message,
            )

        return GuardrailsResult(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            blocked_patterns=[],
            message=f"Passed {self.config.name} check.",
        )


class GuardrailsTemplateRegistry:
    def __init__(self):
        self._templates: dict[str, GuardrailConfig] = {}

    def register(self, name: str, patterns: list[str]) -> None:
        self._templates[name] = GuardrailConfig(name=name, patterns=patterns)

    def create(self, name: str) -> TemplateGuardrail | None:
        if name not in self._templates:
            return None
        return TemplateGuardrail(self._templates[name])

    def list_templates(self) -> list[str]:
        return list(self._templates.keys())


DEFAULT_TEMPLATES: dict[str, list[str]] = {
    "prompt_injection": [
        "ignore previous instructions",
        "disregard all",
        "system prompt",
        "forget everything",
        "override your instructions",
        "you are now",
        "enter developer mode",
        "jailbreak",
    ],
    "xss": ["<script", "javascript:", "onerror=", "onload=", "vbscript:", "data:text/html"],
    "sql_injection": ["UNION SELECT", "DROP TABLE", "DELETE FROM", "TRUNCATE TABLE", "SLEEP(", "BENCHMARK("],
    "code_execution": ["eval(", "exec(", "os.system(", "subprocess", "popen(", "Invoke-Expression"],
    "path_traversal": ["../", "..\\", "/etc/passwd", "/proc/self/", "%2e%2e"],
}


def create_default_registry() -> GuardrailsTemplateRegistry:
    registry = GuardrailsTemplateRegistry()
    for name, patterns in DEFAULT_TEMPLATES.items():
        registry.register(name, patterns)
    return registry