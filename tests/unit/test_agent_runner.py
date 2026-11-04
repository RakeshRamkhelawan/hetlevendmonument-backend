"""Unit tests for AgentRunner pacemaker."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.agent_runner import AgentRunner
from src.core.als.infrastructure.signal_bus import SignalBus, Signal, SignalTier

@pytest.fixture
def mock_db_factory():
    session = AsyncMock()
    session.close = AsyncMock()
    return AsyncMock(return_value=session)

@pytest.fixture
def mock_signal_bus():
    bus = MagicMock(spec=SignalBus)
    bus.wait_for_signal = AsyncMock(side_effect=asyncio.TimeoutError)
    return bus

@pytest.fixture
def mock_agent_factory():
    agent = AsyncMock()
    agent.execute_ooda = AsyncMock()
    async def factory(c):
        return agent
    return factory

@pytest.mark.asyncio
async def test_start_with_no_configs(mock_db_factory, mock_signal_bus) -> None:
    repo_mock = MagicMock()
    repo_mock.get_active_configs = AsyncMock(return_value=[])
    with patch("src.core.agent_runner.AgentConfigRepository", return_value=repo_mock):
        runner = AgentRunner(mock_db_factory, mock_signal_bus)
        await runner.start()
    repo_mock.get_active_configs.assert_awaited_once()

@pytest.mark.asyncio
async def test_stop_sets_event(mock_db_factory, mock_signal_bus) -> None:
    runner = AgentRunner(mock_db_factory, mock_signal_bus)
    await runner.stop()
    assert runner._stop_event.is_set()

@pytest.mark.asyncio
async def test_run_agent_loop_executes_ooda(mock_db_factory, mock_signal_bus, mock_agent_factory) -> None:
    signal = Signal(tenant_id=1, source_agent_id="test", target_agent_ids=[], tier=SignalTier.COGNITIVE, topic="test", payload={})
    cfg = MagicMock()
    cfg.tenant_id = 1
    cfg.agent_id = "a1"
    cfg.subscribed_topics = ["test"]
    cfg.department_user_id = 42
    runner = AgentRunner(mock_db_factory, mock_signal_bus, agent_factory=mock_agent_factory)
    call_count = 0
    async def ws(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return signal
        runner._stop_event.set()
        raise asyncio.TimeoutError
    mock_signal_bus.wait_for_signal = ws
    await runner._run_agent_loop(cfg)
    agent = await mock_agent_factory(cfg)
    agent.execute_ooda.assert_awaited_once()

@pytest.mark.asyncio
async def test_dispatch_action_sets_tenant_context(mock_db_factory, mock_signal_bus, mock_agent_factory) -> None:
    signal = Signal(tenant_id=1, source_agent_id="test", target_agent_ids=[], tier=SignalTier.COGNITIVE, topic="test", payload={})
    cfg = MagicMock()
    cfg.tenant_id = 1
    cfg.agent_id = "a1"
    cfg.department_user_id = 99
    agent = await mock_agent_factory(cfg)
    runner = AgentRunner(mock_db_factory, mock_signal_bus, agent_factory=mock_agent_factory)
    with patch("src.core.agent_runner.set_tenant_id") as mock_set_tenant:
        await runner._dispatch_action(agent, signal, cfg)
    mock_set_tenant.assert_called_with(1)
