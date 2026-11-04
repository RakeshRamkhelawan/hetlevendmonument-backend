"""GOV-001: AutonomousAgent must enforce a GovernanceContract before side effects (ADR-031).

Root cause: AutonomousAgent(BaseAgent) never instantiated a GovernanceContract and
never called is_action_permitted() before Redis writes / stream publishes.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.agents.autonomous_agent import AutonomousAgent
from src.core.shared.interfaces import TaskData


def _make_task(tenant_id: int | None = 1, metadata: dict | None = None) -> TaskData:
    return TaskData(
        title="Autonomous workflow step",
        description="A test workflow task",
        tenant_id=tenant_id,
        metadata=metadata or {},
    )


@pytest.fixture
def agent_with_mock_redis():
    agent = AutonomousAgent(agent_id="autonomous-1")
    agent.redis = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_process_task_blocks_redis_and_stream_when_governance_denies(
    agent_with_mock_redis,
):
    """A GovernanceContract that denies the action must prevent Redis writes and stream publishes."""
    with patch(
        "src.core.governance.governance_contract.GovernanceContract.is_action_permitted",
        return_value=False,
    ):
        result = await agent_with_mock_redis.process_task(_make_task())

    assert result.success is False
    agent_with_mock_redis.redis.set.assert_not_called()
    agent_with_mock_redis.redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_process_task_allows_side_effects_when_governance_permits(agent_with_mock_redis):
    """A GovernanceContract that permits the action must let the task run through as before."""
    result = await agent_with_mock_redis.process_task(_make_task())

    assert result.success is True
    assert agent_with_mock_redis.redis.xadd.await_count == 2


@pytest.mark.asyncio
async def test_process_task_creates_governance_contract_bound_to_task_tenant(
    agent_with_mock_redis,
):
    assert agent_with_mock_redis._governance_contract is None

    await agent_with_mock_redis.process_task(_make_task(tenant_id=42))

    assert agent_with_mock_redis._governance_contract is not None
    assert agent_with_mock_redis._governance_contract.tenant_id == 42


@pytest.mark.asyncio
async def test_process_task_fails_closed_without_tenant_id(agent_with_mock_redis):
    """No tenant_id means no GovernanceContract can be built -- fail closed (ADR-031/ADR-005)."""
    result = await agent_with_mock_redis.process_task(_make_task(tenant_id=None))

    assert result.success is False
    agent_with_mock_redis.redis.set.assert_not_called()
    agent_with_mock_redis.redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_process_task_fails_closed_on_non_numeric_tenant_id(agent_with_mock_redis):
    """A non-numeric tenant_id must not raise -- fail closed with an ExecutionResult."""
    result = await agent_with_mock_redis.process_task(
        _make_task(tenant_id=None, metadata={"tenant_id": "not-a-number"})
    )

    assert result.success is False
    agent_with_mock_redis.redis.set.assert_not_called()
    agent_with_mock_redis.redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_process_task_fails_closed_on_negative_tenant_id(agent_with_mock_redis):
    """A negative tenant_id fails GovernanceContract construction -- fail closed, no crash."""
    result = await agent_with_mock_redis.process_task(
        _make_task(tenant_id=None, metadata={"tenant_id": -5})
    )

    assert result.success is False
    agent_with_mock_redis.redis.set.assert_not_called()
    agent_with_mock_redis.redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_governance_contract_for_fails_open_on_db_error(agent_with_mock_redis):
    """SP-GOV-ARCH-8: a DB error during persisted-contract readback must not make
    is_action_permitted() more permissive -- fail-open means the fresh, conservative
    contract stays in effect (no approved_actions leaked in), never a bypass."""
    with (
        patch("src.core.database.database.db_manager.is_initialized", return_value=True),
        patch(
            "src.core.database.database.db_manager.get_session",
            side_effect=RuntimeError("db unavailable"),
        ),
    ):
        contract = await agent_with_mock_redis._governance_contract_for(1)

    # No approval evidence leaked in from a failed/nonexistent read -- the
    # contract is exactly what the fresh classify_agent() call built.
    assert contract.evidence.get("approved_actions") is None
    assert contract.evidence.get("hitl_approval") is None
