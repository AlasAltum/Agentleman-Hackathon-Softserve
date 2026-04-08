from typing import Any

from src.integrations.base import IntegrationProvider
from src.integrations.models import IntegrationConfig, IntegrationResult, IntegrationType


class VectorDBProvider(IntegrationProvider):
    type = IntegrationType.VECTOR_DB

    async def execute(self, *args, **kwargs) -> IntegrationResult:
        return IntegrationResult(success=True, data={"mocked": True})

    async def health_check(self) -> bool:
        return True

    async def upsert(
        self,
        collection: str,
        documents: list[dict[str, Any]],
        ids: list[str] | None = None,
    ) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={"upserted": len(documents), "collection": collection},
        )

    async def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        filter_: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={
                "results": [],
                "collection": collection,
                "query": query,
                "top_k": top_k,
            },
        )

    async def delete(
        self,
        collection: str,
        ids: list[str] | None = None,
        filter_: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={"deleted": True, "collection": collection},
        )


class LLMProvider(IntegrationProvider):
    type = IntegrationType.LLM_PROVIDER

    async def execute(self, *args, **kwargs) -> IntegrationResult:
        return IntegrationResult(success=True, data={"mocked": True})

    async def health_check(self) -> bool:
        return True

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={
                "completion": "Mocked LLM response",
                "model": model or "default",
                "tokens_used": 100,
            },
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            data={
                "message": "Mocked chat response",
                "model": model or "default",
            },
        )