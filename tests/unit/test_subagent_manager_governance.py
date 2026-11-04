"""Unit tests for governance hook in subagents_manager.py (Pad 5)."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightResult


def _make_result(
    allowed: bool,
    requires_human_approval: bool = False,
    reason: str = "test",
) -> OversightResult:
    return OversightResult(
        allowed=allowed,
        requires_human_approval=requires_human_approval,
        risk_level=AIActRiskLevel.LIMITED,
        reason=reason,
    )


def _make_request(title: str = "Test task", preferred_agent: str | None = None):
    """Build a minimal SubagentTaskRequest-like object."""
    req = Mock()
    req.title = title
    req.description = "Test description"
    req.priority = "medium"
    req.tags = []
    req.metadata = {}
    req.preferred_agent = preferred_agent
    return req


class TestPerfectSubagentsManagerGovernance:
    @pytest.mark.asyncio
    async def test_execute_blocked_raises_403(self):
        from src.core.agents.subagents_manager import PerfectSubagentsManager

        manager = PerfectSubagentsManager()
        mock_gate = AsyncMock()
        mock_gate.check = AsyncMock(
            return_value=_make_result(allowed=False, reason="content policy")
        )
        manager._get_oversight_gate = lambda: mock_gate

        with pytest.raises(HTTPException) as exc_info:
            await manager.execute_with_specialist(_make_request())

        assert exc_info.value.status_code == 403
        assert "governance" in exc_info.value.detail.lower()
        assert "content policy" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_execute_requires_approval_raises_403(self):
        from src.core.agents.subagents_manager import PerfectSubagentsManager

        manager = PerfectSubagentsManager()
        mock_gate = AsyncMock()
        mock_gate.check = AsyncMock(
            return_value=_make_result(
                allowed=True,
                requires_human_approval=True,
                reason="high-risk action",
            )
        )
        manager._get_oversight_gate = lambda: mock_gate

        with pytest.raises(HTTPException) as exc_info:
            await manager.execute_with_specialist(_make_request())

        assert exc_info.value.status_code == 403
        assert "human approval" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_governance_checked_before_routing(self):
        """Governance check runs before routing logic."""
        from src.core.agents.subagents_manager import PerfectSubagentsManager

        manager = PerfectSubagentsManager()
        mock_gate = AsyncMock()
        mock_gate.check = AsyncMock(
            return_value=_make_result(allowed=False, reason="blocked")
        )
        manager._get_oversight_gate = lambda: mock_gate

        # route_task_to_specialist should NOT be called when governance blocks
        manager.route_task_to_specialist = Mock()

        with pytest.raises(HTTPException):
            await manager.execute_with_specialist(_make_request())

        manager.route_task_to_specialist.assert_not_called()

    @pytest.mark.asyncio
    async def test_governance_call_uses_correct_params(self):
        from src.core.agents.subagents_manager import PerfectSubagentsManager

        manager = PerfectSubagentsManager()
        mock_gate = AsyncMock()
        mock_gate.check = AsyncMock(
            return_value=_make_result(allowed=False, reason="blocked")
        )
        manager._get_oversight_gate = lambda: mock_gate

        with pytest.raises(HTTPException):
            await manager.execute_with_specialist(
                _make_request("Deploy payment service", "finance_agent")
            )

        call_kwargs = mock_gate.check.call_args[1]
        assert call_kwargs["agent_name"] == "SubAgentFactory"
        assert call_kwargs["agent_department"] == "specialist"
        assert call_kwargs["task_action"] == "execute_specialist"
        assert call_kwargs["task_params"]["title"] == "Deploy payment service"
        assert call_kwargs["task_params"]["preferred_agent"] == "finance_agent"
