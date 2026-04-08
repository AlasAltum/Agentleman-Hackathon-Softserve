from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntegrationType(str, Enum):
    TICKETING = "ticketing"
    NOTIFICATION = "notification"
    EMAIL = "email"
    COMMUNICATOR = "communicator"
    VECTOR_DB = "vector_db"
    LLM_PROVIDER = "llm_provider"


@dataclass
class IntegrationConfig:
    type: IntegrationType
    name: str
    enabled: bool = True
    config: dict[str, Any] | None = None


@dataclass
class IntegrationResult:
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None