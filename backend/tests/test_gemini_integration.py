import pytest
import os
from unittest.mock import MagicMock, patch

from src.utils.setup import setup_defaults, reset_settings, configure_settings
from src.workflow.models import IncidentInput, PreprocessedIncident, FileMetadata


def has_gemini_api_key():
    """Check if Gemini API key is available."""
    return bool(
        os.getenv("GOOGLE_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("LLM_API_KEY")
    )


@pytest.fixture
def gemini_env():
    """Setup Gemini environment for testing."""
    original_env = dict(os.environ)
    
    # Set Gemini as provider
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["EMBED_PROVIDER"] = "gemini"
    
    # Model configuration
    if not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = "models/gemini-pro"
    if not os.getenv("EMBED_MODEL"):
        os.environ["EMBED_MODEL"] = "models/embedding-001"
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
    reset_settings()


@pytest.mark.skipif(
    not has_gemini_api_key(),
    reason="Gemini API key not found. Set GOOGLE_API_KEY, GEMINI_API_KEY, or LLM_API_KEY"
)
class TestGeminiConnection:
    """Test Gemini LLM connection and basic functionality."""
    
    def test_gemini_llm_initialization(self, gemini_env):
        """Test that Gemini LLM initializes correctly."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        assert Settings.llm is not None, "LLM should be initialized"
        assert "Google" in Settings.llm.__class__.__name__ or "Gemini" in Settings.llm.__class__.__name__, "Should use Google/Gemini LLM"
        assert "gemini" in Settings.llm.model.lower(), "Model should be a Gemini model"
    
    def test_gemini_embeddings_initialization(self, gemini_env):
        """Test that Gemini embeddings initialize correctly."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        assert Settings.embed_model is not None, "Embeddings should be initialized"
        assert "Google" in Settings.embed_model.__class__.__name__ or "Gemini" in Settings.embed_model.__class__.__name__, "Should use Google/Gemini embeddings"
    
    def test_gemini_simple_completion(self, gemini_env):
        """Test basic text completion with Gemini."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        response = Settings.llm.complete("Say 'test successful' and nothing else.")
        
        assert response is not None, "Should get a response"
        assert len(response.text) > 0, "Response should have text"
        assert "test successful" in response.text.lower(), "Should contain expected text"
    
    def test_gemini_chat_completion(self, gemini_env):
        """Test chat completion with Gemini."""
        from llama_index.core.llms import ChatMessage
        from llama_index.core import Settings
        
        setup_defaults()
        
        messages = [
            ChatMessage(role="user", content="What is 2+2? Reply with just the number.")
        ]
        
        response = Settings.llm.chat(messages)
        
        assert response is not None, "Should get a response"
        assert len(response.message.content) > 0, "Response should have content"
        assert "4" in response.message.content, "Should contain the answer"
    
    def test_gemini_embeddings_generation(self, gemini_env):
        """Test embedding generation with Gemini."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        text = "This is a test sentence for embeddings."
        embeddings = Settings.embed_model.get_text_embedding(text)
        
        assert embeddings is not None, "Should generate embeddings"
        assert len(embeddings) > 0, "Embeddings should not be empty"
        assert isinstance(embeddings, list), "Embeddings should be a list"
    
    def test_gemini_batch_embeddings(self, gemini_env):
        """Test batch embedding generation."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        texts = [
            "First test sentence.",
            "Second test sentence.",
            "Third test sentence."
        ]
        
        embeddings = Settings.embed_model.get_text_embedding_batch(texts)
        
        assert embeddings is not None, "Should generate batch embeddings"
        assert len(embeddings) == len(texts), "Should have embedding for each text"
        for emb in embeddings:
            assert len(emb) > 0, "Each embedding should not be empty"


@pytest.mark.skipif(
    not has_gemini_api_key(),
    reason="Gemini API key not found. Set GOOGLE_API_KEY, GEMINI_API_KEY, or LLM_API_KEY"
)
class TestGeminiWithWorkflow:
    """Test Gemini LLM within the SRE workflow context."""
    
    @pytest.mark.asyncio
    async def test_gemini_workflow_integration(self, gemini_env):
        """Test full workflow with Gemini (mocked components)."""
        from src.workflow.sre_workflow import SREIncidentWorkflow
        from llama_index.core.workflow import Context
        from unittest.mock import AsyncMock, patch
        from src.workflow.models import ClassificationResult, IncidentType, ToolResult, TriageResult, Severity
        
        setup_defaults()
        
        workflow = SREIncidentWorkflow(timeout=30)
        
        preprocessed = PreprocessedIncident(
            original=IncidentInput(
                text_desc="Database connection timeout",
                reporter_email="test@example.com",
            ),
            consolidated_text="Database connection timeout",
            file_metadata=FileMetadata(),
        )
        
        with patch("src.workflow.sre_workflow._retrieve_candidates") as mock_retrieve, \
             patch("src.workflow.sre_workflow._rerank_candidates") as mock_rerank, \
             patch("src.workflow.sre_workflow._classify_incident") as mock_classify, \
             patch("src.workflow.sre_workflow._select_tools") as mock_select, \
             patch("src.workflow.sre_workflow._dispatch_tools") as mock_dispatch, \
             patch("src.workflow.sre_workflow._consolidate_triage") as mock_consolidate, \
             patch("src.workflow.sre_workflow._create_or_update_ticket") as mock_ticket, \
             patch("src.workflow.sre_workflow._notify_team") as mock_notify:
            
            mock_retrieve.return_value = []
            mock_rerank.return_value = []
            mock_classify.return_value = ClassificationResult(
                incident_type=IncidentType.NEW_INCIDENT
            )
            mock_select.return_value = ["business_impact"]
            mock_dispatch.return_value = [
                ToolResult(tool_name="business_impact", findings="Test findings")
            ]
            mock_consolidate.return_value = TriageResult(
                classification=ClassificationResult(incident_type=IncidentType.NEW_INCIDENT),
                tool_results=[],
                technical_summary="Test summary",
                severity=Severity.MEDIUM,
                business_impact_summary="Low impact",
            )
            mock_ticket.return_value = MagicMock(
                ticket_id="SRE-TEST",
                ticket_url="https://example.com/SRE-TEST",
                action="created",
            )
            
            result = await workflow.run(preprocessed=preprocessed)
            
            assert result is not None, "Workflow should complete"
            assert result.ticket_id == "SRE-TEST", "Should create ticket"


class TestGeminiConfiguration:
    """Test Gemini configuration options."""
    
    def test_gemini_model_selection(self, gemini_env):
        """Test Gemini model configuration."""
        # Test the recommended model
        os.environ["LLM_MODEL"] = "gemini-2.5-flash"
        setup_defaults()
        
        from llama_index.core import Settings
        assert Settings.llm is not None, "Should initialize gemini-2.5-flash"
        
        reset_settings()
    
    def test_gemini_embedding_models(self, gemini_env):
        """Test Gemini embedding model configuration."""
        # Test the recommended embedding model
        os.environ["EMBED_MODEL"] = "gemini-embedding-2-preview"
        setup_defaults()
        
        from llama_index.core import Settings
        assert Settings.embed_model is not None, "Should initialize gemini-embedding-2-preview"
        
        reset_settings()


@pytest.mark.integration
@pytest.mark.skipif(
    not has_gemini_api_key(),
    reason="Gemini API key not found"
)
class TestGeminiRealWorldScenarios:
    """Test real-world scenarios with Gemini."""
    
    def test_gemini_codebase_analysis(self, gemini_env):
        """Test Gemini's ability to analyze code snippets."""
        from llama_index.core import Settings
        
        setup_defaults()
        
        code_snippet = """
        def calculate_total(items):
            total = 0
            for item in items:
                total += item.price
            return total
        """
        
        prompt = f"""
        Analyze this code and identify potential issues:
        {code_snippet}
        
        Reply with specific issues found.
        """
        
        response = Settings.llm.complete(prompt)
        
        assert response is not None
        assert len(response.text) > 100# Should provide detailed analysis
    
    def test_gemini_incident_summarization(self, gemini_env):
        """Test Gemini's ability to summarize incidents."""
        from llama_index.core import Settings
        from llama_index.core.llms import ChatMessage
        
        setup_defaults()
        
        incident_description = """
        Incident Report:
        - Service: Payment API
        - Error: Connection timeout to database
        - Impact: 500 users affected
        - Duration: 15 minutes
        - Stack trace: java.sql.SQLException: Connection refused
        """
        
        messages = [
            ChatMessage(
                role="user",
                content=f"Summarize this incident in 2 sentences: {incident_description}"
            )
        ]
        
        response = Settings.llm.chat(messages)
        
        assert response is not None
        assert len(response.message.content) > 0
        assert len(response.message.content) < 500# Should be concise


def test_gemini_api_key_validation():
    """Test that appropriate error is raised when API key is missing."""
    import os
    
    # Save original env
    original_env = dict(os.environ)
    
    try:
        # Remove all API keys
        for key in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"]:
            if key in os.environ:del os.environ[key]
        
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["EMBED_PROVIDER"] = "gemini"
        
        with pytest.raises(ValueError, match="API key required"):
            setup_defaults()
    
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)
        reset_settings()