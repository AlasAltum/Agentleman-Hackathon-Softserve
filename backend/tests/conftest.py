import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure test environment before any tests run."""
    import os
    
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
    
    # LLM Configuration (mock for testing)
    os.environ["LLM_PROVIDER"] = "mock"
    
    # API Keys (not needed for mock provider)
    os.environ["GOOGLE_API_KEY"] = "test-key"
    os.environ["LLM_MODEL"] = "mock-model"
    
    # Embeddings Configuration (mock for testing)
    os.environ["EMBED_PROVIDER"] = "mock"
    os.environ["EMBED_MODEL"] = "mock-embedding"
    
    yield