from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.monitoring.trace import TraceOrchestrator


@pytest.mark.asyncio
async def test_trace_graph_generation():
    # Setup mock DB results for agent A calling agent B and C
    mock_db = AsyncMock()
    mock_result = MagicMock()
    # (source, targets, tier, sig_id, timestamp)
    mock_result.all.return_value = [
        ("agent_a", ["agent_b", "agent_c"], "cognitive", "sig_1", "2026-03-02")
    ]
    mock_db.execute.return_value = mock_result

    with patch("src.core.database.database.db_manager.get_session") as mock_session:
        mock_session.return_value.__aenter__.return_value = mock_db

        orchestrator = TraceOrchestrator()
        graph = await orchestrator.get_execution_trace("corr_123", tenant_id=1)

        # Should have 3 nodes: A, B, C
        assert len(graph["nodes"]) == 3
        # Should have 2 edges: A->B, A->C
        assert len(graph["edges"]) == 2
        assert graph["edges"][0]["source"] == "agent_a"
        assert graph["edges"][0]["target"] == "agent_b"
