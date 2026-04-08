from abc import ABC, abstractmethod

from src.guardrails.models import GuardrailsResult


class BaseGuardrail(ABC):
    @abstractmethod
    def validate(self, content: str) -> GuardrailsResult:
        ...