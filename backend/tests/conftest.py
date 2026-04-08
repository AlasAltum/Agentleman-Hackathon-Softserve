import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure test environment before any tests run."""
    import os
    
    os.environ["APP_ENV"] = "test"
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["EMBED_PROVIDER"] = "mock"
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    
    yield