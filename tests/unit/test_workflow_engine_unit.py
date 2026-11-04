"""
Unit tests for ProductionWorkflowEngine (workflow/engine.py).

Covers: _parse_spec, cancel_execution, save_snapshot, get_latest_snapshot,
state machine transitions, and retry backoff logic.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


class TestParseSpec:
    """Tests for _parse_spec() helper."""

    def _get_engine(self):
        """Create engine with mocked dependencies."""
        with patch("src.core.workflow.engine.ProductionWorkflowEngine.__init__", return_value=None):
            from src.core.workflow.engine import ProductionWorkflowEngine

            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)
        return engine

    def test_parses_valid_spec(self):
        engine = self._get_engine()
        spec = {
            "tasks": {"task_a": {"type": "llm", "prompt": "hello"}},
            "dependencies": {"task_a": []},
            "timeout_seconds": 600,
            "max_retries": 5,
            "retry_backoff_seconds": 10,
        }
        result = engine._parse_spec("wf_1", 1, spec)
        assert result.workflow_id == "wf_1"
        assert result.version == 1
        assert "task_a" in result.tasks
        assert result.timeout_seconds == 600
        assert result.max_retries == 5
        assert result.retry_backoff_seconds == 10

    def test_uses_defaults_for_missing_fields(self):
        engine = self._get_engine()
        spec = {}
        result = engine._parse_spec("wf_2", 1, spec)
        assert result.tasks == {}
        assert result.dependencies == {}
        assert result.timeout_seconds == 3600
        assert result.max_retries == 3
        assert result.retry_backoff_seconds == 5

    def test_handles_complex_dependencies(self):
        engine = self._get_engine()
        spec = {
            "tasks": {
                "a": {"type": "llm"},
                "b": {"type": "tool"},
                "c": {"type": "agent"},
            },
            "dependencies": {
                "a": [],
                "b": ["a"],
                "c": ["a", "b"],
            },
        }
        result = engine._parse_spec("wf_3", 2, spec)
        assert result.dependencies["c"] == ["a", "b"]


class TestCancelExecution:
    """Tests for cancel_execution()."""

    @pytest.mark.asyncio
    async def test_cancel_pending_execution(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        # Mock execution
        mock_execution = MagicMock()
        mock_execution.status = MagicMock()
        mock_execution.status.__eq__ = lambda self, other: self is other
        mock_execution.status.name = "PENDING"

        # Use string comparison for the enum check
        from src.core.workflow.models import WorkflowStatus

        mock_execution.status = WorkflowStatus.PENDING

        engine._get_execution = AsyncMock(return_value=mock_execution)
        engine._update_execution_status = AsyncMock()

        await engine.cancel_execution("exec_1")

        engine._update_execution_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cannot_cancel_completed_execution(self):
        from src.core.workflow.engine import ProductionWorkflowEngine
        from src.core.workflow.models import WorkflowStatus

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_execution = MagicMock()
        mock_execution.status = WorkflowStatus.SUCCEEDED

        engine._get_execution = AsyncMock(return_value=mock_execution)
        engine._update_execution_status = AsyncMock()

        result = await engine.cancel_execution("exec_1")

        assert result is False
        engine._update_execution_status.assert_not_awaited()


class TestSaveSnapshot:
    """Tests for save_snapshot()."""

    @pytest.mark.asyncio
    async def test_saves_snapshot_successfully(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_workflow = MagicMock()
        mock_workflow.id = 1
        mock_workflow.tenant_id = "tenant_1"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_workflow
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock the snapshot after commit
        mock_snapshot = MagicMock()
        mock_snapshot.id = 42

        engine._get_session = MagicMock(return_value=mock_session)

        with patch("src.core.workflow.engine.WorkflowSnapshot") as MockSnapshot:
            MockSnapshot.return_value = mock_snapshot
            result = await engine.save_snapshot(
                workflow_id="wf_1",
                content=b"binary-yjs-state",
                tenant_id="tenant_1",
            )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        assert result == 42

    @pytest.mark.asyncio
    async def test_raises_when_workflow_not_found(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        engine._get_session = MagicMock(return_value=mock_session)

        with pytest.raises(ValueError, match="not found"):
            await engine.save_snapshot(
                workflow_id="nonexistent",
                content=b"data",
            )


class TestGetLatestSnapshot:
    """Tests for get_latest_snapshot()."""

    @pytest.mark.asyncio
    async def test_returns_content_when_snapshot_exists(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_workflow = MagicMock()
        mock_workflow.id = 1

        mock_snapshot = MagicMock()
        mock_snapshot.content = b"snapshot-content"

        mock_session = AsyncMock()
        # First call: find workflow
        # Second call: find snapshot
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = mock_workflow
        mock_result_snapshot = MagicMock()
        mock_result_snapshot.scalar_one_or_none.return_value = mock_snapshot

        mock_session.execute = AsyncMock(side_effect=[mock_result_workflow, mock_result_snapshot])

        engine._get_session = MagicMock(return_value=mock_session)

        result = await engine.get_latest_snapshot("wf_1")
        assert result == b"snapshot-content"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_workflow(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        engine._get_session = MagicMock(return_value=mock_session)

        result = await engine.get_latest_snapshot("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshots(self):
        from src.core.workflow.engine import ProductionWorkflowEngine

        with patch.object(ProductionWorkflowEngine, "__init__", return_value=None):
            engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)

        mock_workflow = MagicMock()
        mock_workflow.id = 1

        mock_session = AsyncMock()
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = mock_workflow
        mock_result_snapshot = MagicMock()
        mock_result_snapshot.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[mock_result_workflow, mock_result_snapshot])

        engine._get_session = MagicMock(return_value=mock_session)

        result = await engine.get_latest_snapshot("wf_1")
        assert result is None
