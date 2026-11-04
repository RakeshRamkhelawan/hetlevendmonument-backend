"""
Unit tests for honest contract enforcement on ALS background listeners.

Verifies that unimplemented background listeners (ContractManager and ShadowCEO)
raise explicit NotImplementedError referencing ADR-006 instead of silent pass stubs.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.als.enterprise.contracts.a2a_contracts import ContractManager
from src.core.als.enterprise.shadow.shadow_ceo import ShadowCEO


@pytest.fixture
def mock_signal_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.emit = AsyncMock(return_value=None)
    return bus


@pytest.mark.asyncio
async def test_contract_manager_listen_for_contracts_raises_not_implemented(
    mock_signal_bus: AsyncMock,
) -> None:
    """_listen_for_contracts must raise NotImplementedError referencing ADR-006."""
    manager = ContractManager(signal_bus=mock_signal_bus, tenant_id=1)
    with pytest.raises(NotImplementedError, match="ADR-006"):
        await manager._listen_for_contracts()


@pytest.mark.asyncio
async def test_shadow_ceo_listen_for_signals_raises_not_implemented(
    mock_signal_bus: AsyncMock,
) -> None:
    """_listen_for_signals must raise NotImplementedError referencing ADR-006."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=mock_signal_bus, agent_id="shadow_test")
    with pytest.raises(NotImplementedError, match="ADR-006"):
        await shadow._listen_for_signals()


@pytest.mark.asyncio
async def test_contract_manager_clean_shutdown(
    mock_signal_bus: AsyncMock,
) -> None:
    """ContractManager shuts down cleanly without throwing unhandled exceptions."""
    manager = ContractManager(signal_bus=mock_signal_bus, tenant_id=1)
    await manager.shutdown()
    assert manager._listener_task is None or manager._listener_task.done()


@pytest.mark.asyncio
async def test_shadow_ceo_clean_lifecycle(
    mock_signal_bus: AsyncMock,
) -> None:
    """ShadowCEO initializes and shuts down cleanly without unhandled listener exceptions."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=mock_signal_bus, agent_id="shadow_test")
    started = await shadow.initialize()
    assert started is True
    await shadow.shutdown()
    assert shadow._running is False
