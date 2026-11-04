"""Tests: GoalAlignmentValidator is called before step execution (Golden Rule R1)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.company.context import AgentExecutionContext, GoalChain
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_orchestrator_calls_goal_alignment_validator():
    """DomainPackOrchestrator validates goal alignment before each step."""
    from src.core.procedures.domain_pack_orchestrator import DomainPackOrchestrator

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    with patch(
        "src.core.procedures.domain_pack_orchestrator.GoalAlignmentValidator"
    ) as MockValidator:
        mock_validator = MockValidator.return_value
        mock_validator.validate = AsyncMock(return_value=MagicMock(status="ALIGNED"))

        orchestrator = DomainPackOrchestrator()
        await orchestrator.validate_step("Analyse Q1 financials", ctx)

        mock_validator.validate.assert_called_once_with("Analyse Q1 financials", ctx)


@pytest.mark.asyncio
async def test_orchestrator_blocks_misaligned_action():
    """MISALIGNED result raises GoalMisalignmentError instead of executing."""
    from src.core.procedures.domain_pack_orchestrator import (
        DomainPackOrchestrator,
        GoalMisalignmentError,
    )

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(mission_id=uuid4()),
    )

    with patch(
        "src.core.procedures.domain_pack_orchestrator.GoalAlignmentValidator"
    ) as MockValidator:
        MockValidator.return_value.validate = AsyncMock(
            return_value=MagicMock(status="MISALIGNED", reason="Off-topic")
        )

        orchestrator = DomainPackOrchestrator()
        with pytest.raises(GoalMisalignmentError):
            await orchestrator.validate_step("Delete all data", ctx)


def test_external_agent_bridge_prefers_company_context():
    """Bridge uses task.company_context (typed field) over task.context alias."""
    from src.core.company.external_agent_bridge import ExternalAgentBridge

    ctx = AgentExecutionContext(
        tenant_id=1,
        task_id=uuid4(),
        trace_id=uuid4(),
        company_id=uuid4(),
        department_id=uuid4(),
        goal_chain=GoalChain(),
    )
    task = TaskData(title="t", description="d", company_context=ctx)

    bridge = ExternalAgentBridge.__new__(ExternalAgentBridge)
    resolved = bridge._resolve_context(task)
    assert resolved is ctx
