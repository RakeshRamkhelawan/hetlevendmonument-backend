"""Unit tests for governance hook in workflow_worker.py (Pad 4 - Dramatiq)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.workers.workflow_worker import _check_worker_governance


class TestCheckWorkerGovernance:
    @pytest.mark.asyncio
    async def test_allowed_passes_silently(self):
        with patch(
            "src.workers.workflow_worker.apply_governance_check",
            AsyncMock(return_value=(True, None)),
        ) as governance_check:
            # Should not raise
            await _check_worker_governance("exec-001")
        governance_check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blocked_raises_permission_error(self):
        with patch(
            "src.workers.workflow_worker.apply_governance_check",
            AsyncMock(return_value=(False, "policy violation")),
        ):
            with pytest.raises(PermissionError) as exc_info:
                await _check_worker_governance("exec-002")

        assert "GOVERNANCE_BLOCK" in str(exc_info.value)
        assert "policy violation" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_check_called_with_correct_agent_params(self):
        with patch(
            "src.workers.workflow_worker.apply_governance_check",
            AsyncMock(return_value=(True, None)),
        ) as governance_check:
            await _check_worker_governance(
                "exec-004", agent_name="MyEngine", task_action="custom_action"
            )

        call_kwargs = governance_check.call_args.kwargs
        assert call_kwargs["agent_name"] == "MyEngine"
        assert call_kwargs["task_action"] == "custom_action"
        assert call_kwargs["task_params"]["execution_id"] == "exec-004"
        assert call_kwargs["agent_department"] == "workflow"

    @pytest.mark.asyncio
    async def test_governance_exception_propagates(self):
        """Unexpected errors during governance check must propagate (fail-closed)."""
        with patch(
            "src.workers.workflow_worker.apply_governance_check",
            AsyncMock(side_effect=RuntimeError("Gate unavailable")),
        ):
            with pytest.raises(RuntimeError, match="Gate unavailable"):
                await _check_worker_governance("exec-005")
