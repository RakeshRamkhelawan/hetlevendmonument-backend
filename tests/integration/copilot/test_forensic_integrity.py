"""
Integration tests for Co-Pilot forensic integrity.

Covers:
1. Idempotency (ExecutionGuard) prevents duplicate actions.
2. Result binding hashes tool output and links it to the decision.
3. Tool failure states are correctly captured in the audit chain.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.copilot.council.audit_writer import CouncilAuditWriter
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.copilot.council.types import DecisionVerdict
from src.core.copilot.execution.idempotency import ExecutionGuard, ExecutionStatus
from src.core.copilot.service import CopilotService
from src.services.tool_broker.scoped_broker import ScopedToolBroker


class FakeRedis:
    """Fake Redis for idempotency testing."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._data:
            return False
        self._data[key] = value
        if ex:
            self._ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
        return count


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_execution(db_session):
    """Scenario 1: Double execution-poging wordt geblokkeerd door lock."""
    # Setup
    fake_redis = FakeRedis()
    guard = ExecutionGuard(fake_redis)

    # Mock dependencies
    mock_broker = AsyncMock()
    mock_broker.execute_tool.return_value = {"status": "ok"}

    mock_audit = AsyncMock()

    # We need a Proposal and CouncilDecision
    from tests.integration.copilot.conftest import make_proposal

    proposal = make_proposal(action_type="local__test")

    from src.core.copilot.council.types import CouncilDecision

    decision = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved",
        decision_hash="some-hash",
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

    # First execution
    res1 = await service._execute_decision(proposal, decision)
    assert res1 == {"status": "ok"}
    assert mock_broker.execute_tool.call_count == 1

    # Second execution (same decision_id)
    res2 = await service._execute_decision(proposal, decision)
    assert res2 is None  # Skipped
    assert mock_broker.execute_tool.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_result_binding_forensic_hash(db_session):
    """Scenario 2: Tool-output hash matcht na reconstructie."""
    # Setup
    fake_redis = FakeRedis()
    guard = ExecutionGuard(fake_redis)

    class _SessionCtx:
        async def __aenter__(self) -> Any:
            return db_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    def db_session_factory() -> _SessionCtx:
        return _SessionCtx()

    audit_writer = CouncilAuditWriter(db_session_factory)

    # Mock broker
    result_payload = {"user_created": True, "id": 123}
    mock_broker = AsyncMock()
    mock_broker.execute_tool.return_value = result_payload

    # Prepare decision in DB
    from tests.integration.copilot.conftest import make_proposal, seed_tenants

    await seed_tenants(db_session, [1])

    proposal = make_proposal(tenant_id=1, action_type="local__create_user")

    from src.core.copilot.council.types import CouncilDecision

    decision = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved",
        decision_hash="initial-hash",
        previous_decision_hash=None,
        deliberation_ms=10,
    )

    # Persist decision first
    await audit_writer.persist(decision, proposal, ())

    service = CopilotService(
        council=AsyncMock(),
        llm_handler=AsyncMock(),
        proposal_builder=AsyncMock(),
        tool_broker=mock_broker,
        audit_writer=audit_writer,
        execution_guard=guard,
    )

    # Execute
    await service._execute_decision(proposal, decision)

    # Verify DB
    stmt = select(CouncilDecisionRow).where(CouncilDecisionRow.decision_id == decision.decision_id)
    row = (await db_session.execute(stmt)).scalar_one()

    assert row.execution_status == "success"
    assert row.result_hash is not None

    # Reconstruct hash. ADR-036 OP-39: result_hash is a tenant-scoped keyed HMAC
    # (safe_digest_result -> digest_result, src/core/tool_broker/redaction.py), not a bare
    # SHA-256 -- a bare hash over low-entropy tool output (a bool, a small int) would be a
    # confirmation oracle for anyone who can read the row. audit_writer.py::bind_execution_result
    # computes it the same way.
    from src.core.tool_broker.redaction import safe_digest_result

    expected_digest = safe_digest_result(result_payload, tenant_id=1)
    assert expected_digest is not None
    assert row.result_hash == expected_digest["hmac"]


@pytest.mark.asyncio
async def test_tool_failure_audit_status(db_session):
    """Scenario 3: Tool-fout resulteert in correcte audit-status."""
    # Setup
    fake_redis = FakeRedis()
    guard = ExecutionGuard(fake_redis)

    class _SessionCtx:
        async def __aenter__(self) -> Any:
            return db_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    def db_session_factory() -> _SessionCtx:
        return _SessionCtx()

    audit_writer = CouncilAuditWriter(db_session_factory)

    # Mock broker to fail
    mock_broker = AsyncMock()
    mock_broker.execute_tool.side_effect = ValueError("Database connection failed")

    # Prepare decision in DB
    from tests.integration.copilot.conftest import make_proposal, seed_tenants

    await seed_tenants(db_session, [1])
    proposal = make_proposal(tenant_id=1, action_type="local__fail")

    from src.core.copilot.council.types import CouncilDecision

    decision = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved",
        decision_hash="fail-hash",
        previous_decision_hash=None,
        deliberation_ms=10,
    )
    await audit_writer.persist(decision, proposal, ())

    service = CopilotService(
        council=AsyncMock(),
        llm_handler=AsyncMock(),
        proposal_builder=AsyncMock(),
        tool_broker=mock_broker,
        audit_writer=audit_writer,
        execution_guard=guard,
    )

    # Execute (should raise)
    with pytest.raises(ValueError, match="Database connection failed"):
        await service._execute_decision(proposal, decision)

    # Verify DB
    stmt = select(CouncilDecisionRow).where(CouncilDecisionRow.decision_id == decision.decision_id)
    row = (await db_session.execute(stmt)).scalar_one()

    assert row.execution_status == "failed"
    assert row.result_hash is not None  # It hashes the error dict {"error": ...}

    # Verify guard status
    status = await guard.get_status(decision.decision_id)
    assert status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_scoped_tool_broker_propagation():
    """Verify ScopedToolBroker injects context into payload."""
    inner_mock = AsyncMock()
    inner_mock.execute_tool.return_value = {"ok": True}

    scoped = ScopedToolBroker(inner_mock)

    payload = {"some": "data"}
    context = {"tenant_id": 42, "user_id": 99}

    await scoped.execute_tool(tool_name="test_tool", payload=payload, context=context)

    # Check what inner_mock received
    call_args = inner_mock.execute_tool.call_args
    sent_payload = call_args.kwargs["payload"]

    assert sent_payload["tenant_id"] == 42
    assert sent_payload["user_id"] == 99
    assert sent_payload["some"] == "data"
    assert call_args.kwargs["context"] == context
