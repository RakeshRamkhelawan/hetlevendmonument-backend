from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.als.agents.memory import ContextCompressor
from src.core.als.infrastructure.signal_bus import Signal, SignalTier


@pytest.mark.asyncio
async def test_context_compression_rolling_window():
    # Setup mock LLM
    with patch("src.core.als.agents.memory.LLMService") as mock_llm_cls:
        mock_llm = mock_llm_cls.return_value
        mock_llm.generate = AsyncMock(return_value=("Summary of old events", {}))
        mock_llm_cls.for_tenant = AsyncMock(return_value=mock_llm)

        compressor = ContextCompressor(window_size=2)

        history = [
            Signal(
                tenant_id=1,
                source_agent_id="a",
                target_agent_ids=[],
                tier=SignalTier.COGNITIVE,
                payload={"text": f"Msg {i}"},
            )
            for i in range(5)
        ]

        compressed_context = await compressor.compress(history)

        assert "Summary of old events" in compressed_context
        assert "Msg 3" in compressed_context
        assert "Msg 4" in compressed_context
        assert "Msg 0" not in compressed_context


@pytest.mark.asyncio
async def test_long_term_memory_storage():
    with (
        patch("src.core.als.agents.memory.LLMService") as mock_llm_cls,
        patch("src.core.database.database.db_manager.get_session") as mock_session,
    ):
        mock_llm = mock_llm_cls.return_value
        mock_llm.get_embeddings = AsyncMock(return_value=[0.1] * 1536)
        mock_llm_cls.for_tenant = AsyncMock(return_value=mock_llm)

        mock_db = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_db

        compressor = ContextCompressor()

        await compressor.store_insight(
            tenant_id=1, agent_id="test_agent", insight="Competitor X lowered prices by 10%"
        )

        assert mock_db.execute.called
