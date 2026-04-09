"""Direct tests for rerank_candidates function.

Tests verify the rerank_candidates function:
- Filters candidates down to top-N
- Maintains proper sorting by similarity score
- Handles edge cases (empty list, fewer than N, exactly N)
"""

import pytest
from datetime import datetime, timezone

from src.workflow.phases.classification import rerank_candidates, _RERANKER_TOP_N
from src.workflow.models import HistoricalCandidate


@pytest.fixture
def sample_candidates():
    """Create a list of candidates with varying similarity scores."""
    return [
        HistoricalCandidate(
            incident_id="INC-001",
            description="Database timeout issue",
            resolution="Restarted service",
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            similarity_score=0.95,
        ),
        HistoricalCandidate(
            incident_id="INC-002",
            description="Memory leak detected",
            resolution="Updated code",
            timestamp=datetime(2024, 1, 14, 8, 15, 0, tzinfo=timezone.utc),
            similarity_score=0.72,
        ),
        HistoricalCandidate(
            incident_id="INC-003",
            description="API latency spike",
            resolution="Optimized queries",
            timestamp=datetime(2024, 1, 13, 14, 45, 0, tzinfo=timezone.utc),
            similarity_score=0.88,
        ),
        HistoricalCandidate(
            incident_id="INC-004",
            description="Network connectivity issue",
            resolution="Patched router",
            timestamp=datetime(2024, 1, 12, 9, 0, 0, tzinfo=timezone.utc),
            similarity_score=0.65,
        ),
        HistoricalCandidate(
            incident_id="INC-005",
            description="Cache invalidation bug",
            resolution="Deployed fix",
            timestamp=datetime(2024, 1, 11, 16, 30, 0, tzinfo=timezone.utc),
            similarity_score=0.81,
        ),
    ]


class TestReRankCandidates:
    """Test rerank_candidates function."""

    def test_returns_top_n_candidates(self, sample_candidates):
        """Should return exactly _RERANKER_TOP_N candidates."""
        result = rerank_candidates(sample_candidates)

        assert len(result) == _RERANKER_TOP_N
        assert _RERANKER_TOP_N == 3  # Verify the constant

    def test_sorts_by_similarity_score_descending(self, sample_candidates):
        """Candidates should be sorted by similarity score (highest first)."""
        result = rerank_candidates(sample_candidates)

        # Verify descending order
        for i in range(len(result) - 1):
            assert (
                result[i].similarity_score >= result[i + 1].similarity_score
            ), f"Score {result[i].similarity_score} should be >= {result[i + 1].similarity_score}"

    def test_returns_highest_scoring_candidates(self, sample_candidates):
        """Should return the top-3 highest scoring candidates."""
        result = rerank_candidates(sample_candidates)

        # Expected top 3 by score: 0.95, 0.88, 0.81
        assert result[0].incident_id == "INC-001"  # 0.95
        assert result[0].similarity_score == 0.95

        assert result[1].incident_id == "INC-003"  # 0.88
        assert result[1].similarity_score == 0.88

        assert result[2].incident_id == "INC-005"  # 0.81
        assert result[2].similarity_score == 0.81

    def test_handles_empty_list(self):
        """Should gracefully handle empty input."""
        result = rerank_candidates([])

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_fewer_than_n_candidates(self):
        """Should return all candidates if fewer than _RERANKER_TOP_N."""
        candidates = [
            HistoricalCandidate(
                incident_id="INC-A",
                description="Issue A",
                resolution="Fix A",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.9,
            ),
            HistoricalCandidate(
                incident_id="INC-B",
                description="Issue B",
                resolution="Fix B",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.7,
            ),
        ]

        result = rerank_candidates(candidates)

        # Should return both (even though _RERANKER_TOP_N = 3)
        assert len(result) == 2
        assert result[0].similarity_score == 0.9
        assert result[1].similarity_score == 0.7

    def test_handles_exactly_n_candidates(self):
        """Should return all candidates if exactly _RERANKER_TOP_N."""
        candidates = [
            HistoricalCandidate(
                incident_id=f"INC-{i}",
                description=f"Issue {i}",
                resolution=f"Fix {i}",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.9 - (i * 0.1),
            )
            for i in range(_RERANKER_TOP_N)
        ]

        result = rerank_candidates(candidates)

        assert len(result) == _RERANKER_TOP_N
        # All candidates should be returned in order
        for i in range(len(result) - 1):
            assert result[i].similarity_score >= result[i + 1].similarity_score

    def test_discards_low_scoring_candidates(self, sample_candidates):
        """Should discard candidates below top-N even if they have good scores."""
        result = rerank_candidates(sample_candidates)

        # INC-002 (0.72) and INC-004 (0.65) should not be in results
        result_ids = {c.incident_id for c in result}
        assert "INC-002" not in result_ids
        assert "INC-004" not in result_ids

    def test_preserves_candidate_data(self, sample_candidates):
        """Should preserve all fields of the top candidates."""
        result = rerank_candidates(sample_candidates)

        # Check that all fields are present and correct
        for candidate in result:
            assert candidate.incident_id is not None
            assert candidate.description is not None
            assert candidate.resolution is not None
            assert candidate.timestamp is not None
            assert candidate.similarity_score is not None

    def test_handles_identical_scores(self):
        """Should handle candidates with identical similarity scores."""
        candidates = [
            HistoricalCandidate(
                incident_id=f"INC-{i}",
                description=f"Issue {i}",
                resolution=f"Fix {i}",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.85,  # All same score
            )
            for i in range(5)
        ]

        result = rerank_candidates(candidates)

        # Should return first 3 (stable sort)
        assert len(result) == 3
        # All should have same score
        assert all(c.similarity_score == 0.85 for c in result)

    def test_handles_single_candidate(self):
        """Should handle single candidate."""
        candidate = HistoricalCandidate(
            incident_id="INC-ONLY",
            description="Only issue",
            resolution="Only fix",
            timestamp=datetime.now(tz=timezone.utc),
            similarity_score=0.99,
        )

        result = rerank_candidates([candidate])

        assert len(result) == 1
        assert result[0].incident_id == "INC-ONLY"

    def test_handles_unsorted_input(self):
        """Should sort even if input is not sorted."""
        candidates = [
            HistoricalCandidate(
                incident_id="INC-C",
                description="Issue C",
                resolution="Fix C",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.6,
            ),
            HistoricalCandidate(
                incident_id="INC-A",
                description="Issue A",
                resolution="Fix A",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.9,
            ),
            HistoricalCandidate(
                incident_id="INC-B",
                description="Issue B",
                resolution="Fix B",
                timestamp=datetime.now(tz=timezone.utc),
                similarity_score=0.75,
            ),
        ]

        result = rerank_candidates(candidates)

        # Should be sorted despite input order
        assert result[0].incident_id == "INC-A"  # 0.9
        assert result[1].incident_id == "INC-B"  # 0.75
        assert result[2].incident_id == "INC-C"  # 0.6

    def test_returns_copy_not_reference(self, sample_candidates):
        """Should return new list (not modify original)."""
        original_len = len(sample_candidates)
        original_first = sample_candidates[0].incident_id

        result = rerank_candidates(sample_candidates)

        # Original should be unchanged
        assert len(sample_candidates) == original_len
        assert sample_candidates[0].incident_id == original_first

        # Result should be different
        assert len(result) == 3  # Top-N
        assert result[0].incident_id == "INC-001"  # Sorted by score


class TestReRankCandidatesWithRealData:
    """Integration tests with data from retrieve_candidates."""

    @pytest.mark.asyncio
    async def test_pipeline_retrieve_then_rerank(self):
        """Test the full pipeline: retrieve_candidates → rerank_candidates."""
        from src.workflow.phases.classification import retrieve_candidates
        from src.workflow.models import PreprocessedIncident, IncidentInput
        from src.integrations.qdrant_store import reset_qdrant_index

        reset_qdrant_index()

        incident = PreprocessedIncident(
            original=IncidentInput(
                text_desc="S3 bucket issue",
                reporter_email="test@example.com",
            ),
            consolidated_text="S3 bucket policy error",
        )

        # Step 1: Retrieve candidates
        candidates = await retrieve_candidates(incident)

        # Verify we got some candidates
        assert len(candidates) > 0
        original_count = len(candidates)

        # Step 2: Rerank
        reranked = rerank_candidates(candidates)

        # Verify reranking reduced to top-N
        assert len(reranked) <= _RERANKER_TOP_N
        assert len(reranked) <= original_count

        # Verify still sorted
        for i in range(len(reranked) - 1):
            assert (
                reranked[i].similarity_score >= reranked[i + 1].similarity_score
            ), "Reranked candidates should be sorted by similarity"

    def test_typical_workflow(self, sample_candidates):
        """Simulate typical workflow: 10 candidates → 3 reranked."""
        # Start with 10 candidates from retrieve_candidates
        assert len(sample_candidates) == 5  # Using 5 for demo

        # Rerank to top-3
        reranked = rerank_candidates(sample_candidates)

        # Verify expected behavior
        assert len(reranked) == min(_RERANKER_TOP_N, len(sample_candidates))
        assert reranked[0].similarity_score >= reranked[-1].similarity_score

        # Top candidate should have highest score
        top_score = max(c.similarity_score for c in sample_candidates)
        assert reranked[0].similarity_score == top_score
