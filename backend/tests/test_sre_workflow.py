import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from llama_index.core.workflow import Context

from src.utils.setup import setup_defaults, reset_settings
from src.workflow.events import (
    ContextEnrichedEvent,
    ToolCallEvent,
    ToolResultEvent,
    TriageCompleteEvent,
)
from src.workflow.models import (
    ClassificationResult,
    FileMetadata,
    IncidentInput,
    IncidentType,
    PreprocessedIncident,
    Severity,
    ToolResult,
    TriageResult,
)
from src.workflow.sre_workflow import SREIncidentWorkflow


@pytest.fixture(autouse=True)
def setup_llama_index():
    """Setup mock LLM/embeddings before each test."""
    # Force mock provider for unit tests
    original_provider = os.environ.get("LLM_PROVIDER")
    original_embed = os.environ.get("EMBED_PROVIDER")
    
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["EMBED_PROVIDER"] = "mock"
    
    setup_defaults()
    yield
    reset_settings()
    
    # Restore original values
    if original_provider:
        os.environ["LLM_PROVIDER"] = original_provider
    if original_embed:
        os.environ["EMBED_PROVIDER"] = original_embed


@pytest.fixture
def sample_preprocessed() -> PreprocessedIncident:
    """Create a sample preprocessed incident for testing."""
    return PreprocessedIncident(
        original=IncidentInput(
            text_desc="Database connection timeout error",
            reporter_email="engineer@company.com",
        ),
        consolidated_text="Database connection timeout error",
        file_metadata=FileMetadata(),
    )


@pytest.fixture
def sample_classification() -> ClassificationResult:
    """Create a sample classification result."""
    return ClassificationResult(
        incident_type=IncidentType.NEW_INCIDENT,
        top_candidates=[],
        historical_rca=None,
    )


class TestSREIncidentWorkflowEvents:
    """Test event creation and properties."""
    
    def test_context_enriched_event(self, sample_preprocessed, sample_classification):
        """Test ContextEnrichedEvent creation."""
        event = ContextEnrichedEvent(
            preprocessed=sample_preprocessed,
            classification=sample_classification,
        )
        assert event.preprocessed == sample_preprocessed
        assert event.classification == sample_classification
    
    def test_tool_call_event(self, sample_preprocessed, sample_classification):
        """Test ToolCallEvent creation."""
        event = ToolCallEvent(
            preprocessed=sample_preprocessed,
            classification=sample_classification,
            tools_to_dispatch=["business_impact", "codebase_analyzer"],
            previous_results=[],
            iteration=1,
        )
        assert event.tools_to_dispatch == ["business_impact", "codebase_analyzer"]
        assert event.iteration == 1
        assert event.previous_results == []
    
    def test_tool_result_event(self, sample_preprocessed, sample_classification):
        """Test ToolResultEvent creation."""
        results = [
            ToolResult(tool_name="business_impact", findings="Low impact"),
        ]
        event = ToolResultEvent(
            preprocessed=sample_preprocessed,
            classification=sample_classification,
            tool_results=results,
            iteration=1,
        )
        assert len(event.tool_results) == 1
        assert event.tool_results[0].tool_name == "business_impact"
    
    def test_triage_complete_event(self, sample_preprocessed):
        """Test TriageCompleteEvent creation."""
        triage = TriageResult(
            classification=ClassificationResult(incident_type=IncidentType.NEW_INCIDENT),
            tool_results=[],
            technical_summary="Test summary",
            severity=Severity.MEDIUM,
            business_impact_summary="No impact",
        )
        event = TriageCompleteEvent(
            preprocessed=sample_preprocessed,
            triage=triage,
        )
        assert event.triage.severity == Severity.MEDIUM


class TestSREIncidentWorkflowSteps:
    """Test individual workflow steps."""
    
    @pytest.mark.asyncio
    async def test_classify_step(self, sample_preprocessed):
        """Test the classify step emits ContextEnrichedEvent."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        with patch("src.workflow.sre_workflow._retrieve_candidates") as mock_retrieve, \
             patch("src.workflow.sre_workflow._rerank_candidates") as mock_rerank, \
             patch("src.workflow.sre_workflow._classify_incident") as mock_classify:
            
            mock_retrieve.return_value = []
            mock_rerank.return_value = []
            mock_classify.return_value = ClassificationResult(
                incident_type=IncidentType.NEW_INCIDENT
            )
            
            event = await workflow.classify(ctx, MagicMock(preprocessed=sample_preprocessed))
            
            assert isinstance(event, ContextEnrichedEvent)
            mock_retrieve.assert_called_once()
            mock_rerank.assert_called_once()
            mock_classify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_router_step_first_iteration(self, sample_preprocessed, sample_classification):
        """Test router on first iteration (ContextEnrichedEvent)."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        await ctx.store.set("max_iterations", 2)
        
        with patch("src.workflow.sre_workflow._select_tools") as mock_select:
            mock_select.return_value = ["business_impact"]
            
            event = ContextEnrichedEvent(
                preprocessed=sample_preprocessed,
                classification=sample_classification,
            )
            
            result = await workflow.router(ctx, event)
            
            assert isinstance(result, ToolCallEvent)
            assert "business_impact" in result.tools_to_dispatch
    
    @pytest.mark.asyncio
    async def test_router_step_max_iterations(self, sample_preprocessed, sample_classification):
        """Test router stops after max iterations."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        await ctx.store.set("max_iterations", 1)
        
        tool_results = [
            ToolResult(tool_name="business_impact", findings="Test"),
        ]
        
        event = ToolResultEvent(
            preprocessed=sample_preprocessed,
            classification=sample_classification,
            tool_results=tool_results,
            iteration=2,  # Above max_iterations
        )
        
        result = await workflow.router(ctx, event)
        
        assert isinstance(result, TriageCompleteEvent)
    
    @pytest.mark.asyncio
    async def test_router_step_no_tools(self, sample_preprocessed, sample_classification):
        """Test router proceeds to ticketing when no tools selected."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        await ctx.store.set("max_iterations", 2)
        
        with patch("src.workflow.sre_workflow._select_tools") as mock_select:
            mock_select.return_value = []  # No tools to dispatch
            
            event = ContextEnrichedEvent(
                preprocessed=sample_preprocessed,
                classification=sample_classification,
            )
            
            result = await workflow.router(ctx, event)
            
            assert isinstance(result, TriageCompleteEvent)
    
    @pytest.mark.asyncio
    async def test_dispatch_tools_step(self, sample_preprocessed, sample_classification):
        """Test dispatch_tools executes tools and returns results."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        mock_result = ToolResult(tool_name="business_impact", findings="Test findings")
        
        with patch("src.workflow.sre_workflow._dispatch_tools") as mock_dispatch:
            mock_dispatch.return_value = [mock_result]
            
            event = ToolCallEvent(
                preprocessed=sample_preprocessed,
                classification=sample_classification,
                tools_to_dispatch=["business_impact"],
                previous_results=[],
                iteration=0,
            )
            
            result = await workflow.dispatch_tools(ctx, event)
            
            assert isinstance(result, ToolResultEvent)
            assert len(result.tool_results) == 1
            assert result.iteration == 1
    
    @pytest.mark.asyncio
    async def test_process_results_step(self, sample_preprocessed, sample_classification):
        """Test process_results consolidates and returns ToolResultEvent."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        tool_results = [
            ToolResult(tool_name="business_impact", findings="High impact"),
        ]
        
        event = ToolResultEvent(
            preprocessed=sample_preprocessed,
            classification=sample_classification,
            tool_results=tool_results,
            iteration=1,
        )
        
        result = await workflow.process_results(ctx, event)
        
        assert isinstance(result, ToolResultEvent)
        assert result.iteration == 1
    
    @pytest.mark.asyncio
    async def test_create_ticket_step(self, sample_preprocessed):
        """Test create_ticket_and_notify step."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        triage = TriageResult(
            classification=ClassificationResult(incident_type=IncidentType.NEW_INCIDENT),
            tool_results=[],
            technical_summary="Test",
            severity=Severity.MEDIUM,
            business_impact_summary="None",
        )
        
        with patch("src.workflow.sre_workflow._create_or_update_ticket") as mock_ticket, \
             patch("src.workflow.sre_workflow.dispatch_notifications") as mock_notify:
            
            mock_ticket.return_value = MagicMock(
                ticket_id="SRE-123",
                ticket_url="https://jira.example.com/SRE-123",
                action="created",
            )
            
            event = TriageCompleteEvent(
                preprocessed=sample_preprocessed,
                triage=triage,
            )
            
            result = await workflow.create_ticket_and_notify(ctx, event)
            
            mock_ticket.assert_called_once()
            mock_notify.assert_called_once()
            assert result.result.ticket_id == "SRE-123"


class TestSREIncidentWorkflowIntegration:
    """Integration tests for the full workflow."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, sample_preprocessed):
        """Test full workflow from start to finish."""
        workflow = SREIncidentWorkflow(timeout=60)
        
        with patch("src.workflow.sre_workflow._retrieve_candidates") as mock_retrieve, \
             patch("src.workflow.sre_workflow._rerank_candidates") as mock_rerank, \
             patch("src.workflow.sre_workflow._classify_incident") as mock_classify, \
             patch("src.workflow.sre_workflow._select_tools") as mock_select, \
             patch("src.workflow.sre_workflow._dispatch_tools") as mock_dispatch, \
             patch("src.workflow.sre_workflow._consolidate_triage") as mock_consolidate, \
             patch("src.workflow.sre_workflow._create_or_update_ticket") as mock_ticket, \
             patch("src.workflow.sre_workflow.dispatch_notifications") as mock_notify:
            
            mock_retrieve.return_value = []
            mock_rerank.return_value = []
            mock_classify.return_value = ClassificationResult(
                incident_type=IncidentType.NEW_INCIDENT
            )
            mock_select.return_value = ["business_impact"]
            mock_dispatch.return_value = [
                ToolResult(tool_name="business_impact", findings="Low impact")
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
                ticket_url="https://jira.example.com/SRE-TEST",
                action="created",
            )
            
            result = await workflow.run(preprocessed=sample_preprocessed)
            
            assert result.ticket_id == "SRE-TEST"
            mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_workflow_with_alert_storm(self, sample_preprocessed):
        """Test workflow with ALERT_STORM classification."""
        workflow = SREIncidentWorkflow(timeout=60)
        
        from datetime import datetime, timezone
        from src.workflow.models import HistoricalCandidate
        
        historical = HistoricalCandidate(
            incident_id="SRE-001",
            similarity_score=0.85,
            timestamp=datetime.now(timezone.utc),
            summary="Previous incident",
        )
        
        with patch("src.workflow.sre_workflow._retrieve_candidates") as mock_retrieve, \
             patch("src.workflow.sre_workflow._rerank_candidates") as mock_rerank, \
             patch("src.workflow.sre_workflow._classify_incident") as mock_classify, \
             patch("src.workflow.sre_workflow._select_tools") as mock_select, \
             patch("src.workflow.sre_workflow._dispatch_tools") as mock_dispatch, \
             patch("src.workflow.sre_workflow._consolidate_triage") as mock_consolidate, \
             patch("src.workflow.sre_workflow._create_or_update_ticket") as mock_ticket, \
             patch("src.workflow.sre_workflow.dispatch_notifications") as mock_notify:
            
            mock_retrieve.return_value = [historical]
            mock_rerank.return_value = [historical]
            mock_classify.return_value = ClassificationResult(
                incident_type=IncidentType.ALERT_STORM,
                top_candidates=[historical],
            )
            mock_select.return_value = ["business_impact"]
            mock_dispatch.return_value = [
                ToolResult(tool_name="business_impact", findings="Critical impact")
            ]
            mock_consolidate.return_value = TriageResult(
                classification=ClassificationResult(
                    incident_type=IncidentType.ALERT_STORM,
                    top_candidates=[historical],
                ),
                tool_results=[],
                technical_summary="Alert storm detected",
                severity=Severity.CRITICAL,
                business_impact_summary="Critical",
            )
            mock_ticket.return_value = MagicMock(
                ticket_id="SRE-001",
                ticket_url="https://jira.example.com/SRE-001",
                action="updated",
            )
            
            result = await workflow.run(preprocessed=sample_preprocessed)
            
            assert result.action == "updated"


class TestWorkflowStateManagement:
    """Test Context state management in workflow."""
    
    @pytest.mark.asyncio
    async def test_context_state_persistence(self, sample_preprocessed, sample_classification):
        """Test that state persists across steps."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        await ctx.store.set("iteration", 0)
        await ctx.store.set("accumulated_results", [])
        await ctx.store.set("max_iterations", 3)
        
        iteration = await ctx.store.get("iteration", default=0)
        max_iter = await ctx.store.get("max_iterations", default=2)
        
        assert iteration == 0
        assert max_iter == 3
    
    @pytest.mark.asyncio
    async def test_accumulated_results_across_iterations(self, sample_preprocessed, sample_classification):
        """Test that tool results accumulate across iterations."""
        workflow = SREIncidentWorkflow()
        ctx = Context(workflow)
        
        await ctx.store.set("accumulated_results", [])
        
        first_result = ToolResult(tool_name="business_impact", findings="First")
        await ctx.store.set("accumulated_results", [first_result])
        
        stored = await ctx.store.get("accumulated_results", default=[])
        
        assert len(stored) == 1
        assert stored[0].tool_name == "business_impact"