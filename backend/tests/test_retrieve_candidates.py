import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from llama_index.core.workflow import Context, StartEvent

from src.workflow.sre_workflow import SREIncidentWorkflow
from src.workflow.events import CandidatesRetrievedEvent
from src.workflow.models import (
    PreprocessedIncident, 
    IncidentInput, 
    HistoricalCandidate
)

@pytest.mark.asyncio
async def test_retrieve_candidates_step_returns_qdrant_data():
    print("\n" + "="*50)
    print("🚀 STARTING TEST: retrieve_candidates_step")
    print("="*50)

    workflow = SREIncidentWorkflow()
    ctx = Context(workflow)
    
    # 1. Input Incident
    sample_incident = PreprocessedIncident(
        original=IncidentInput(
            text_desc="Website is down and payments are failing",
            reporter_email="test@example.com"
        ),
        consolidated_text="Website is down and payments are failing"
    )
    print(f"📥 INPUT TEXT: {sample_incident.consolidated_text}")
    
    # 2. Mock Output
    mock_historical_data = [
        HistoricalCandidate(
            incident_id="INC-055",
            similarity_score=0.92,
            timestamp=datetime.now(timezone.utc),
            title="DDoS Attack",
            description="Website inaccessible due to malicious traffic (DDoS).",
            resolution="Activated Cloudflare Under Attack mode."
        )
    ]
    print(f"🎭 MOCKING QDRANT: Prepared {len(mock_historical_data)} candidates")

    # 3. Patching
    with patch("src.workflow.sre_workflow.retrieve_candidates", new_callable=AsyncMock) as mock_retriever:
        mock_retriever.return_value = mock_historical_data
        print("🔗 PATCH: 'retrieve_candidates' successfully diverted to mock.")
        
        ev = StartEvent(preprocessed=sample_incident)
        
        # 4. Run Step
        print("🏃 RUNNING: Executing workflow step...")
        result_event = await workflow.retrieve_candidates_step(ctx, ev)
        
        # 5. Inspect Results
        print("\n" + "-"*30)
        print("📊 STEP EXECUTION RESULTS:")
        print(f"   Event Type: {type(result_event).__name__}")
        print(f"   Candidates Found: {len(result_event.candidates)}")
        
        for i, cand in enumerate(result_event.candidates):
            print(f"   [{i}] ID: {cand.incident_id} | Score: {cand.similarity_score}")
            print(f"       Desc: {cand.description[:50]}...")

        # 6. Verify State
        iter_count = await ctx.store.get("iteration")
        print(f"📍 CONTEXT STATE: iteration = {iter_count}")
        print("-"*30)

        # Assertions
        assert isinstance(result_event, CandidatesRetrievedEvent)
        assert iter_count == 0
        print("✅ TEST PASSED: Metadata and state verified.")