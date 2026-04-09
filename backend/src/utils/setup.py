"""LlamaIndex settings configuration for multiple LLM providers.

Supports:
- Google Gemini (direct API)
- OpenRouter (unified API for multiple LLMs)
- OpenAI
- Anthropic
- Ollama (local)
- Mock (testing)
"""

import os
from typing import Optional

from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager


def configure_settings(
    llm=None,
    embed_model=None,
    callback_manager: CallbackManager | None = None,
) -> None:
    """Configure LlamaIndex global settings.
    
    Args:
        llm: LLM instance (e.g., Gemini, OpenAI, Anthropic, or local model)
        embed_model: Embedding model instance for vector operations
        callback_manager: Callback manager for observability (MLflow, etc.)
    
    If arguments are None, uses environment variables or defaults.
    """
    if llm is not None:
        Settings.llm = llm
    
    if embed_model is not None:
        Settings.embed_model = embed_model
    
    if callback_manager is not None:
        Settings.callback_manager = callback_manager


def get_settings() -> dict:
    """Return current LlamaIndex settings as a dictionary."""
    return {
        "llm": Settings.llm,
        "embed_model": Settings.embed_model,
        "callback_manager": Settings.callback_manager,
        "chunk_size": Settings.chunk_size,
        "chunk_overlap": Settings.chunk_overlap,
    }


def setup_defaults() -> None:
    """Setup default LlamaIndex settings from environment variables.
    
    Environment Variables:
        LLM_PROVIDER: "gemini", "openrouter", "openai", "anthropic", "ollama", "mock"
        LLM_MODEL: model name (e.g., "models/gemini-pro", "google/gemini-pro", "gpt-4o-mini")
        LLM_API_KEY: API key for the provider
        
        EMBED_PROVIDER: "gemini", "openai", "openrouter", "local", "mock"
        EMBED_MODEL: embedding model name
        EMBED_API_KEY: API key for embeddings (optional, defaults to LLM_API_KEY)
    """
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    embed_provider = os.getenv("EMBED_PROVIDER", "mock").lower()
    
    if llm_provider == "mock" and embed_provider == "mock":
        _setup_mock_settings()
    else:
        _setup_llm(llm_provider)
        _setup_embeddings(embed_provider)
    
    _setup_mlflow_callbacks()


def _setup_mlflow_callbacks() -> None:
    """Setup MLflow callback manager for LlamaIndex tracing."""
    mlflow_autolog = os.getenv("MLFLOW_AUTOLOG_ENABLED", "true").lower() == "true"
    
    if mlflow_autolog:
        try:
            from src.utils.llama_index_mlflow import configure_mlflow_tracing
            configure_mlflow_tracing()
        except ImportError:
            pass
        except Exception:
            pass


def _setup_mock_settings() -> None:
    """Setup mock LLM and embeddings for testing."""
    from llama_index.core.llms import MockLLM
    from llama_index.core.embeddings import MockEmbedding
    
    Settings.llm = MockLLM()
    Settings.embed_model = MockEmbedding(embed_dim=1536)


def _setup_llm(provider: str) -> None:
    """Setup LLM based on provider."""
    api_key = (
        os.getenv("LLM_API_KEY") or
        os.getenv("GOOGLE_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("OPENROUTER_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        os.getenv("ANTHROPIC_API_KEY")
    )
    model = os.getenv("LLM_MODEL")
    base_url = os.getenv("LLM_BASE_URL")
    
    if provider in ("gemini", "google"):
        _setup_gemini_llm(api_key, model)
    elif provider == "openrouter":
        _setup_openrouter_llm(api_key, model, base_url)
    elif provider == "openai":
        _setup_openai_llm(api_key, model, base_url)
    elif provider == "anthropic":
        _setup_anthropic_llm(api_key, model)
    elif provider == "ollama":
        _setup_ollama_llm(model)
    elif provider == "mock":
        _setup_mock_settings()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _setup_gemini_llm(api_key: Optional[str], model: Optional[str]) -> None:
    """Setup Google Gemini LLM (direct API).
    
    Models:
        - gemini-2.5-flash (default, recommended)
        - gemini-2.0-flash-exp
        - gemini-1.5-pro
        - gemini-1.5-flash
    
    Requires: GOOGLE_API_KEY, GEMINI_API_KEY, or LLM_API_KEY
    """
    from llama_index.llms.google_genai import GoogleGenAI
    
    api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key required for Gemini. Set GOOGLE_API_KEY, GEMINI_API_KEY, or LLM_API_KEY"
        )
    
    model = model or os.getenv("LLM_MODEL", "gemini-2.5-flash")
    
    Settings.llm = GoogleGenAI(model=model, api_key=api_key)


def _setup_openrouter_llm(
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> None:
    """Setup OpenRouter LLM (supports Gemini, Claude, GPT, etc.).
    
    OpenRouter provides a unified API compatible with OpenAI's format.
    Models: google/gemini-pro, anthropic/claude-3-opus, openai/gpt-4, etc.
    """
    from llama_index.llms.openai_like import OpenAILike
    
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY or LLM_API_KEY is required for OpenRouter")
    
    model = model or os.getenv("LLM_MODEL", "google/gemini-pro")
    base_url = base_url or "https://openrouter.ai/api/v1"
    
    Settings.llm = OpenAILike(
        model=model,
        api_key=api_key,
        api_base=base_url,
        is_chat_model=True,
        is_function_calling_model=True,
    )


def _setup_openai_llm(
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> None:
    """Setup OpenAI LLM."""
    from llama_index.llms.openai import OpenAI
    
    model = model or "gpt-4o-mini"
    
    kwargs = {"model": model}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url
    
    Settings.llm = OpenAI(**kwargs)


def _setup_anthropic_llm(
    api_key: Optional[str],
    model: Optional[str],
) -> None:
    """Setup Anthropic LLM."""
    from llama_index.llms.anthropic import Anthropic
    
    model = model or "claude-3-sonnet"
    
    kwargs = {"model": model}
    if api_key:
        kwargs["api_key"] = api_key
    
    Settings.llm = Anthropic(**kwargs)


def _setup_ollama_llm(model: Optional[str]) -> None:
    """Setup Ollama (local) LLM."""
    from llama_index.llms.ollama import Ollama
    
    model = model or "llama2"
    Settings.llm = Ollama(model=model)


def _setup_embeddings(provider: str) -> None:
    """Setup embeddings based on provider."""
    api_key = (
        os.getenv("EMBED_API_KEY") or
        os.getenv("LLM_API_KEY") or
        os.getenv("GOOGLE_API_KEY") or
        os.getenv("GEMINI_API_KEY")
    )
    model = os.getenv("EMBED_MODEL")
    
    if provider in ("gemini", "google"):
        _setup_gemini_embeddings(api_key, model)
    elif provider == "openai":
        _setup_openai_embeddings(api_key, model)
    elif provider == "openrouter":
        _setup_openrouter_embeddings(api_key, model)
    elif provider == "local":
        _setup_local_embeddings(model)
    elif provider == "mock":
        from llama_index.core.embeddings import MockEmbedding
        Settings.embed_model = MockEmbedding(embed_dim=1536)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def _setup_gemini_embeddings(api_key: Optional[str], model: Optional[str]) -> None:
    """Setup Google Gemini embeddings.
    
    Models:
        - gemini-embedding-2-preview (default, recommended)
        - text-embedding-004
    """
    from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
    
    api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key required for Gemini embeddings. Set GOOGLE_API_KEY or LLM_API_KEY"
        )
    
    model = model or os.getenv("EMBED_MODEL", "gemini-embedding-2-preview")
    
    Settings.embed_model = GoogleGenAIEmbedding(model_name=model, api_key=api_key)


def _setup_openrouter_embeddings(
    api_key: Optional[str],
    model: Optional[str],
) -> None:
    """Setup OpenRouter embeddings (via OpenAI-compatible API).
    
    Common models:
    - openai/text-embedding-3-small
    - openai/text-embedding-ada-002
    """
    from llama_index.embeddings.openai import OpenAIEmbedding
    
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("API key required for OpenRouter embeddings")
    
    model = model or "openai/text-embedding-3-small"
    
    Settings.embed_model = OpenAIEmbedding(
        model=model,
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
    )


def _setup_openai_embeddings(
    api_key: Optional[str],
    model: Optional[str],
) -> None:
    """Setup OpenAI embeddings."""
    from llama_index.embeddings.openai import OpenAIEmbedding
    
    model = model or "text-embedding-3-small"
    
    kwargs = {"model": model}
    if api_key:
        kwargs["api_key"] = api_key
    
    Settings.embed_model = OpenAIEmbedding(**kwargs)


def _setup_local_embeddings(model: Optional[str]) -> None:
    """Setup local embeddings (HuggingFace)."""
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    
    model = model or "BAAI/bge-small-en-v1.5"
    Settings.embed_model = HuggingFaceEmbedding(model_name=model)


def reset_settings() -> None:
    """Reset LlamaIndex settings to defaults."""
    Settings.llm = None
    Settings.embed_model = None
    Settings.callback_manager = None
    Settings.chunk_size = 1024
    Settings.chunk_overlap = 200