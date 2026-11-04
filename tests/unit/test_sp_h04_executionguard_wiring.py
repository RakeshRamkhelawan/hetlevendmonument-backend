"""
Unit tests for SP-H04: ExecutionGuard wiring in CopilotService (B-003).

Verifies that _execute_decision correctly uses ExecutionGuard to prevent
duplicate execution of Council decisions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Proposal,
    ProposalTrigger,
)
from src.core.copilot.execution.idempotency import ExecutionGuard, ExecutionStatus
from src.core.copilot.service import CopilotService


DEFAULT_TEST_TENANT = 1


class FakeRedis:
    """In-memory Redis mock for idempotency testing."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._data:
            return False
        self._data[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
        return count


def _make_proposal(action_type: str = "test__action") -> Proposal:
    """Build a minimal Proposal for testing."""
    return Proposal(
        proposal_id=uuid4(),
        tenant_id=DEFAULT_TEST_TENANT,
        user_id=1,
        action_type=action_type,
        action_params={},
        trigger=ProposalTrigger.USER_REQUEST,
        model_id="test-model",
        model_version="1.0",
        context_snapshot={},
        capabilities={},
        message="Test message.",
        reasoning="User requested action.",
        data_classification=DataClassification.PUBLIC,
        confidence=0.95,
    )


def _make_approved_decision(proposal: Proposal) -> CouncilDecision:
    """Build an APPROVED CouncilDecision for testing."""
    return CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved",
        decision_hash="hash-" + str(uuid4()),
        previous_decision_hash=None,
        deliberation_ms=10,
    )


class TestExecutionGuardWiring:
    """Verify ExecutionGuard prevents duplicate execution in CopilotService."""

    @pytest.mark.asyncio
    async def test_guard_blocks_duplicate_execution(self):
        """Second _execute_decision with same decision_id must be blocked."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_broker.execute_tool.return_value = {"status": "ok"}
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        # First execution — must succeed
        res1 = await service._execute_decision(proposal, decision)
        assert res1 == {"status": "ok"}
        assert mock_broker.execute_tool.call_count == 1

        # Second execution — must be blocked
        res2 = await service._execute_decision(proposal, decision)
        assert res2 is None
        assert mock_broker.execute_tool.call_count == 1  # No extra call

    @pytest.mark.asyncio
    async def test_guard_allows_first_execution(self):
        """First _execute_decision must proceed normally."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_broker.execute_tool.return_value = {"created": True}
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        res = await service._execute_decision(proposal, decision)
        assert res == {"created": True}

        # Guard status must be SUCCESS
        status = await guard.get_status(decision.decision_id)
        assert status == ExecutionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_guard_sets_failed_status_on_error(self):
        """On exception guard status must be set to FAILED."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_broker.execute_tool.side_effect = RuntimeError("tool crashed")
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        with pytest.raises(RuntimeError, match="tool crashed"):
            await service._execute_decision(proposal, decision)

        # Guard status must be FAILED
        status = await guard.get_status(decision.decision_id)
        assert status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_audit_bind_called_on_success(self):
        """bind_execution_result must be called with status=success on success."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_broker.execute_tool.return_value = {"status": "ok"}
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        await service._execute_decision(proposal, decision)

        mock_audit.bind_execution_result.assert_awaited_once()
        call_kwargs = mock_audit.bind_execution_result.await_args.kwargs
        assert call_kwargs["status"] == "success"
        assert call_kwargs["decision_id"] == decision.decision_id
        assert call_kwargs["tenant_id"] == proposal.tenant_id

    @pytest.mark.asyncio
    async def test_audit_bind_called_on_failure(self):
        """bind_execution_result must be called with status=failed on failure."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_broker.execute_tool.side_effect = RuntimeError("tool crashed")
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        with pytest.raises(RuntimeError, match="tool crashed"):
            await service._execute_decision(proposal, decision)

        # Check that bind_execution_result was called with failed status
        # It is called twice: once in try-block (not reached) and once in except
        # Actually: the except block calls it, so 1 call total
        assert mock_audit.bind_execution_result.await_count == 1
        call_kwargs = mock_audit.bind_execution_result.await_args.kwargs
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["tenant_id"] == proposal.tenant_id

    @pytest.mark.asyncio
    async def test_no_guard_when_none_injected(self):
        """When execution_guard=None execution must proceed normally."""
        mock_broker = AsyncMock()
        mock_broker.execute_tool.return_value = {"status": "ok"}
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = _make_approved_decision(proposal)

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=None,
        )

        res = await service._execute_decision(proposal, decision)
        assert res == {"status": "ok"}
        assert mock_broker.execute_tool.call_count == 1

    @pytest.mark.asyncio
    async def test_no_execution_on_non_approved_verdict(self):
        """On non-APPROVED verdict execution must be skipped."""
        fake_redis = FakeRedis()
        guard = ExecutionGuard(fake_redis)

        mock_broker = AsyncMock()
        mock_audit = AsyncMock()

        proposal = _make_proposal()
        decision = CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.BLOCKED,
            officer_verdicts=(),
            explanation_for_user="Blocked",
            decision_hash="hash-" + str(uuid4()),
            previous_decision_hash=None,
            deliberation_ms=10,
        )

        service = CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=AsyncMock(),
            tool_broker=mock_broker,
            audit_writer=mock_audit,
            execution_guard=guard,
        )

        res = await service._execute_decision(proposal, decision)
        assert res is None
        assert mock_broker.execute_tool.call_count == 0
