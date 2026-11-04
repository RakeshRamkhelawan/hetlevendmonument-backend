"""GOV-002: ChiefOrchestrator.delegate_task() must enforce a GovernanceContract (ADR-031).

Root cause: delegate_task() emitted a Signal (side effect) without any prior
governance/permission check.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.als.agents.chief_orchestrator import ChiefOrchestrator
from src.core.shared.interfaces import TaskData


def _make_task() -> TaskData:
    return TaskData(title="Delegate me", description="A test task to delegate")


@pytest.fixture
def orchestrator():
    signal_bus = AsyncMock()
    signal_bus.query = AsyncMock(
        return_value=[{"responder": "agent-a", "payload": {"current_load": 0.1}}]
    )
    signal_bus.emit = AsyncMock(return_value="signal-1")
    return ChiefOrchestrator(tenant_id=7, signal_bus=signal_bus)


def test_orchestrator_has_governance_contract_after_init(orchestrator):
    assert orchestrator._governance_contract is not None
    assert orchestrator._governance_contract.tenant_id == 7


@pytest.mark.asyncio
async def test_delegate_task_blocks_signal_emit_when_governance_denies(orchestrator):
    with patch(
        "src.core.governance.governance_contract.GovernanceContract.is_action_permitted",
        return_value=False,
    ):
        result = await orchestrator.delegate_task(_make_task())

    assert result.success is False
    orchestrator.signal_bus.emit.assert_not_called()


@pytest.mark.asyncio
async def test_delegate_task_emits_signal_when_governance_permits(orchestrator):
    result = await orchestrator.delegate_task(_make_task())

    assert result.success is True
    orchestrator.signal_bus.emit.assert_awaited_once()
