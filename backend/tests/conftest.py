import pytest
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure test environment before any tests run.
    
    For unit tests: uses MockLLM/MockEmbedding
    For Gemini integration tests: loads real API keys from .env
    """
    
    # Environment
    os.environ["APP_ENV"] = "test"
    
    # API
    os.environ["APP_HOST"] = "0.0.0.0"
    os.environ["APP_PORT"] = "8000"
    
    # DB
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "test-password"
    os.environ["POSTGRES_DBNAME"] = "postgres"
    os.environ["POSTGRES_HOST"] = "db"
    os.environ["POSTGRES_PORT"] = "5432"
    
    # For unit tests, use MockLLM by default
    # .env will be loaded by dotenv, so we only override if needed
    # Integration tests that need real LLM will set these in their fixtures
    
    # Model names (used if .env doesn't specify them)
    if not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = "gemini-2.5-flash"
    if not os.getenv("EMBED_MODEL"):
        os.environ["EMBED_MODEL"] = "gemini-embedding-2-preview"
    
    yield