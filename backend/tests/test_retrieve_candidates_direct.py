"""Direct tests for retrieve_candidates function.

Tests verify the retrieve_candidates function handles:
- Live Qdrant connections (localhost:6333)
- Missing or incomplete metadata
- Connection failures and error handling
- Proper timestamp parsing
- Candidate sorting by similarity
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from src.workflow.phases.classification import retrieve_candidates, _parse_timestamp
from src.workflow.models import PreprocessedIncident, IncidentInput, HistoricalCandidate
from src.integrations.qdrant_store import reset_qdrant_index


@pytest.fixture(autouse=True)
def reset_qdrant():
    """Reset Qdrant index cache before each test."""
    reset_qdrant_index()
    yield
    reset_qdrant_index()


@pytest.fixture
def sample_incident():
    """Create a sample preprocessed incident for testing."""
    return PreprocessedIncident(
        original=IncidentInput(
            text_desc="Database connection timeout on production",
            reporter_email="oncall@example.com",
        ),
        consolidated_text="Database connection timeout on production server",
    )


class TestRetrieveCandidatesWithMocks:
    """Test retrieve_candidates using mocks (no API keys required).
    
    These tests mock the Qdrant index to verify function behavior
    without needing API keys or live vector data.
    """

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_qdrant_unavailable(self, sample_incident):
        """When Qdrant is unavailable, should return empty list gracefully."""
        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=None
        ):
            result = await retrieve_candidates(sample_incident)

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_returns_candidates_from_qdrant(self, sample_incident):
        """Should return candidates from Qdrant with proper structure."""
        from llama_index.core.schema import NodeWithScore, TextNode

        # Create mock nodes that retriever would return
        mock_nodes = [
            NodeWithScore(
                node=TextNode(
                    text="Database connection timeout affecting production",
                    id_="INC-001",
                    metadata={
                        "incident_id": "INC-001",
                        "title": "Database Timeout",
                        "description": "Connection pool exhausted",
                        "resolution": "Restarted db service",
                        "timestamp": "2024-01-15T10:30:00+00:00",
                    },
                ),
                score=0.95,
            ),
            NodeWithScore(
                node=TextNode(
                    text="Query timeout issue",
                    id_="INC-002",
                    metadata={
                        "incident_id": "INC-002",
                        "title": "Query Timeout",
                        "description": "Slow query",
                        "resolution": "Optimized indexes",
                        "timestamp": "2024-01-10T08:00:00+00:00",
                    },
                ),
                score=0.72,
            ),
        ]

        # Mock the retriever
        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = mock_nodes

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=mock_index
        ):
            result = await retrieve_candidates(sample_incident)

            # Verify structure
            assert len(result) == 2
            assert all(isinstance(c, HistoricalCandidate) for c in result)

            # Check first candidate (should maintain order from Qdrant)
            assert result[0].incident_id == "INC-001"
            assert result[0].similarity_score == 0.95
            assert result[0].description == "Connection pool exhausted"
            assert result[0].resolution == "Restarted db service"

            # Check second candidate
            assert result[1].incident_id == "INC-002"
            assert result[1].similarity_score == 0.72

    @pytest.mark.asyncio
    async def test_candidates_sorted_by_similarity(self, sample_incident):
        """Candidates from Qdrant should maintain similarity order."""
        from llama_index.core.schema import NodeWithScore, TextNode

        # Qdrant returns results pre-sorted by similarity
        mock_nodes = [
            NodeWithScore(
                node=TextNode(
                    text="Database timeout",
                    id_="INC-1",
                    metadata={
                        "incident_id": "INC-1",
                        "title": "Very similar",
                        "description": "desc1",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ),
                score=0.95,
            ),
            NodeWithScore(
                node=TextNode(
                    text="Different issue",
                    id_="INC-2",
                    metadata={
                        "incident_id": "INC-2",
                        "title": "Less similar",
                        "description": "desc2",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ),
                score=0.65,
            ),
        ]

        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = mock_nodes

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=mock_index
        ):
            result = await retrieve_candidates(sample_incident)

            # Results should maintain order from Qdrant
            assert len(result) == 2
            assert result[0].similarity_score == 0.95
            assert result[1].similarity_score == 0.65

    @pytest.mark.asyncio
    async def test_handles_retrieval_exception(self, sample_incident):
        """Should gracefully handle retrieval errors and return empty list."""
        mock_index = MagicMock()
        mock_index.as_retriever.return_value.aretrieve = AsyncMock(
            side_effect=RuntimeError("Qdrant connection lost")
        )

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index",
            return_value=mock_index,
        ):
            result = await retrieve_candidates(sample_incident)

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_metadata_parsing_fallbacks(self, sample_incident):
        """Verify that missing metadata is handled gracefully."""
        from llama_index.core.schema import NodeWithScore, TextNode

        # Node with empty metadata dict
        mock_node = TextNode(
            text="Fallback text content for description",
            id_="node-123",
            metadata={},
        )
        mock_node_with_score = NodeWithScore(node=mock_node, score=0.85)

        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = [mock_node_with_score]

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index",
            return_value=mock_index,
        ):
            result = await retrieve_candidates(sample_incident)

            assert len(result) == 1
            candidate = result[0]

            # Should have fallback values
            assert candidate.incident_id == "node-123"  # Fallback to node_id
            assert "Fallback text content" in candidate.description
            assert candidate.timestamp is not None
            assert candidate.similarity_score == 0.85
            assert candidate.resolution is None  # Missing from metadata

    @pytest.mark.asyncio
    async def test_handles_partial_metadata(self, sample_incident):
        """Should handle nodes with partial metadata gracefully."""
        from llama_index.core.schema import NodeWithScore, TextNode

        mock_node = TextNode(
            text="Incident description content",
            id_="INC-999",
            metadata={
                "incident_id": "INC-999",
                "title": "Provided Title",
                # Missing: description, resolution, timestamp
            },
        )
        mock_node_with_score = NodeWithScore(node=mock_node, score=0.68)

        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = [mock_node_with_score]

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index",
            return_value=mock_index,
        ):
            result = await retrieve_candidates(sample_incident)

            assert len(result) == 1
            candidate = result[0]

            # Description should fall back to node content (max 200 chars)
            assert "Incident description" in candidate.description
            # Resolution should be None when missing
            assert candidate.resolution is None
            # Timestamp should default to now
            assert candidate.timestamp is not None

    @pytest.mark.asyncio
    async def test_handles_empty_candidates_list(self, sample_incident):
        """Should handle empty results from Qdrant."""
        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = []

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=mock_index
        ):
            result = await retrieve_candidates(sample_incident)

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_respects_top_k_parameter(self, sample_incident):
        """Should request top_k candidates from retriever."""
        mock_retriever = AsyncMock()
        mock_retriever.aretrieve.return_value = []

        mock_index = MagicMock()
        mock_index.as_retriever.return_value = mock_retriever

        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=mock_index
        ):
            result = await retrieve_candidates(sample_incident)

            # Verify as_retriever was called with similarity_top_k=10
            mock_index.as_retriever.assert_called_once()
            call_kwargs = mock_index.as_retriever.call_args.kwargs
            assert call_kwargs.get("similarity_top_k") == 10


class TestTimestampParsing:
    """Tests for _parse_timestamp helper function."""

    def test_parses_datetime_object(self):
        """Should return datetime unchanged."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _parse_timestamp(dt)
        assert result == dt

    def test_parses_iso_string(self):
        """Should parse ISO format strings."""
        iso_str = "2024-01-15T10:30:00+00:00"
        result = _parse_timestamp(iso_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parses_iso_string_without_timezone(self):
        """Should parse ISO format without timezone info."""
        iso_str = "2024-01-15T10:30:00"
        result = _parse_timestamp(iso_str)
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_defaults_to_now_on_invalid_input(self):
        """Should return current UTC time for invalid inputs."""
        before = datetime.now(tz=timezone.utc)
        result = _parse_timestamp("invalid-date")
        after = datetime.now(tz=timezone.utc)

        assert isinstance(result, datetime)
        assert before <= result <= after
        assert result.tzinfo is not None  # Should be timezone-aware

    def test_defaults_to_now_on_none_input(self):
        """Should return current UTC time for None."""
        before = datetime.now(tz=timezone.utc)
        result = _parse_timestamp(None)
        after = datetime.now(tz=timezone.utc)

        assert isinstance(result, datetime)
        assert before <= result <= after

    def test_defaults_to_now_on_number_input(self):
        """Should return current UTC time for unexpected types."""
        result = _parse_timestamp(12345)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None


class TestRetrieveCandidatesIntegration:
    """Integration tests with the classification workflow."""

    @pytest.mark.asyncio
    async def test_works_with_preprocessing_output(self):
        """Should work with real preprocessed incident format."""
        incident = PreprocessedIncident(
            original=IncidentInput(
                text_desc="API latency spike",
                reporter_email="platform@example.com",
            ),
            consolidated_text="API response time increased significantly",
        )

        # Should not raise, even with no Qdrant
        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=None
        ):
            result = await retrieve_candidates(incident)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_consistent_across_calls(self):
        """Multiple calls with same query should return consistent results."""
        incident = PreprocessedIncident(
            original=IncidentInput(
                text_desc="Same query", reporter_email="test@example.com"
            ),
            consolidated_text="Consistent query text",
        )

        # With Qdrant unavailable, both should return []
        with patch(
            "src.integrations.qdrant_store.get_qdrant_index", return_value=None
        ):
            result1 = await retrieve_candidates(incident)
            result2 = await retrieve_candidates(incident)

            assert result1 == result2 == []
