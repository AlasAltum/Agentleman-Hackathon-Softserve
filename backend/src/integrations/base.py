from abc import ABC, abstractmethod
from typing import Any

from src.integrations.models import IntegrationConfig, IntegrationResult, IntegrationType


class IntegrationProvider(ABC):
    def __init__(self, config: IntegrationConfig):
        self.config = config

    @property
    @abstractmethod
    def type(self) -> IntegrationType:
        ...

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    async def execute(self, *args, **kwargs) -> IntegrationResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class MockIntegrationProvider(IntegrationProvider):
    async def execute(self, *args, **kwargs) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={"mocked": True, "provider": self.name},
            error=None,
        )

    async def health_check(self) -> bool:
        return True


class IntegrationRegistry:
    def __init__(self):
        self._providers: dict[str, IntegrationProvider] = {}

    def register(self, provider: IntegrationProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> IntegrationProvider | None:
        return self._providers.get(name)

    def get_by_type(self, integration_type: IntegrationType) -> list[IntegrationProvider]:
        return [p for p in self._providers.values() if p.type == integration_type]

    def list_all(self) -> list[str]:
        return list(self._providers.keys())

    def remove(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            return True
        return False


class IntegrationFactory:
    _registry: dict[IntegrationType, type[IntegrationProvider]] = {}

    @classmethod
    def register_provider(
        cls, integration_type: IntegrationType, provider_class: type[IntegrationProvider]
    ) -> None:
        cls._registry[integration_type] = provider_class

    @classmethod
    def create(
        cls, integration_type: IntegrationType, config: IntegrationConfig
    ) -> IntegrationProvider | None:
        provider_class = cls._registry.get(integration_type)
        if provider_class:
            return provider_class(config)
        return None