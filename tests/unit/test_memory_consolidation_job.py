"""Tests for memory consolidation scheduling."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_consolidation_calls_worker():
    """run_consolidation should instantiate and call ConsolidationWorker.run()."""
    with patch("src.core.scheduling.memory_consolidation_job.get_container") as mock_container:
        mock_session = AsyncMock()
        # session_factory() returns a callable; calling it returns an async CM
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = lambda: mock_cm  # noqa: E731
        mock_container.return_value.session_factory.return_value = mock_session_factory

        with patch(
            "src.core.scheduling.memory_consolidation_job.MemoryConsolidationWorker"
        ) as mock_worker_cls:
            mock_worker = AsyncMock()
            mock_worker.run = AsyncMock(return_value={"processed": 5})
            mock_worker_cls.return_value = mock_worker

            from src.core.scheduling.memory_consolidation_job import run_consolidation

            result = await run_consolidation(tenant_id=1)

            mock_worker.run.assert_called_once()


@pytest.mark.asyncio
async def test_run_drift_check_calls_engine():
    """run_drift_check should call ProfileDriftEngine.detect()."""
    with patch("src.core.scheduling.memory_consolidation_job.get_container") as mock_container:
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = lambda: mock_cm  # noqa: E731
        mock_container.return_value.session_factory.return_value = mock_session_factory

        with patch(
            "src.core.scheduling.memory_consolidation_job.ProfileDriftEngine"
        ) as mock_engine_cls:
            from unittest.mock import MagicMock

            mock_drift_event = MagicMock()
            mock_drift_event.drift_score = 0.3
            mock_drift_event.severity = "none"
            mock_drift_event.agent_id = "test-agent"

            mock_engine = AsyncMock()
            mock_engine.detect = AsyncMock(return_value=mock_drift_event)
            mock_engine_cls.return_value = mock_engine

            from src.core.scheduling.memory_consolidation_job import run_drift_check

            result = await run_drift_check(tenant_id=1, agent_id="test-agent")

            mock_engine.detect.assert_called_once_with("test-agent")
            assert result["severity"] == "none"
            assert result["drift_score"] == 0.3
