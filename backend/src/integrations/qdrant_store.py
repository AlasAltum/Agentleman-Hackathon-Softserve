"""Qdrant vector store — local instance, no API key required.

Environment variables:
    QDRANT_HOST       — Qdrant host (default: localhost)
    QDRANT_PORT       — Qdrant gRPC/HTTP port (default: 6333)
    QDRANT_COLLECTION — Collection name for historical incidents (default: incidents)

Usage:
    index = get_qdrant_index()   # returns None when Qdrant is unreachable
    if index:
        retriever = index.as_retriever(similarity_top_k=10)
        nodes = await retriever.aretrieve(query_text)
"""

import os
from urllib.parse import urlparse

from src.utils.logger import logger

# Support either QDRANT_URL (Docker-compose style) or QDRANT_HOST/QDRANT_PORT (legacy).
_qdrant_url = os.getenv("QDRANT_URL", "")
if _qdrant_url:
    _parsed = urlparse(_qdrant_url)
    QDRANT_HOST = _parsed.hostname or "localhost"
    QDRANT_PORT = _parsed.port or 6333
else:
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "incidents")

# Module-level cache — one index per process lifetime.
_index = None
_initialized = False


def get_qdrant_index():
    """Return a cached LlamaIndex VectorStoreIndex backed by local Qdrant.

    Returns None (and logs a warning) when:
    - llama-index-vector-stores-qdrant is not installed
    - Qdrant is unreachable (connection refused, timeout, etc.)

    Callers must handle None gracefully (degrade to NEW_INCIDENT classification).
    """
    global _index, _initialized

    if _initialized:
        return _index

    _initialized = True

    try:
        from qdrant_client import AsyncQdrantClient
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        from llama_index.core import VectorStoreIndex, Settings

        # Use async client for retrieval
        aclient = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

        # Ping to surface connection errors early (before first retrieval)
        vector_store = QdrantVectorStore(
            aclient=aclient,
            collection_name=QDRANT_COLLECTION,
        )
        _index = VectorStoreIndex.from_vector_store(vector_store)
        logger.info(
            "qdrant_connected",
            phase="retrieve",
            component="qdrant_store",
            status="success",
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            collection=QDRANT_COLLECTION,
        )

    except ImportError:
        logger.warning(
            "qdrant_import_error",
            phase="retrieve",
            component="qdrant_store",
            status="error",
            error_type="ImportError",
        )
    except Exception as exc:
        logger.warning(
            "qdrant_connection_failed",
            phase="retrieve",
            component="qdrant_store",
            status="error",
            error_type=type(exc).__name__,
            host=QDRANT_HOST,
            port=QDRANT_PORT,
        )

    return _index


def reset_qdrant_index() -> None:
    """Force re-initialisation on next call (useful in tests)."""
    global _index, _initialized
    _index = None
    _initialized = False


async def store_incident(
    incident_id: str,
    text: str,
    summary: str,
    resolution: str | None,
    timestamp: str,
) -> None:
    """Upsert a resolved incident into Qdrant for future retrieval (feedback loop).

    Called from the resolution phase after a Jira ticket is closed.
    Silently no-ops when Qdrant is unavailable.
    """
    index = get_qdrant_index()
    if index is None:
        return

    try:
        from llama_index.core.schema import TextNode

        node = TextNode(
            text=text,
            id_=incident_id,
            metadata={
                "incident_id": incident_id,
                "summary": summary,
                "resolution": resolution or "",
                "timestamp": timestamp,
            },
        )
        index.insert_nodes([node])
        logger.info(
            "qdrant_incident_stored",
            phase="resolve",
            component="qdrant_store",
            status="success",
            incident_id=incident_id,
        )
    except Exception as exc:
        logger.warning(
            "qdrant_incident_store_failed",
            phase="resolve",
            component="qdrant_store",
            status="error",
            error_type=type(exc).__name__,
            incident_id=incident_id,
        )
