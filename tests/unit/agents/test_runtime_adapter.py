"""Tests for MasterOrchestratorRuntimeAdapter (ADR-034 SP-AGT-001 Dag 2)."""

import importlib

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.unit
def test_runtime_adapter_importable() -> None:
    spec = importlib.util.find_spec("src.core.agents.runtime_adapter")
    assert spec is not None, "src/core/agents/runtime_adapter.py bestaat niet"


@pytest.mark.unit
async def test_adapter_satisfies_iagent_runtime_protocol() -> None:
    from src.core.agents.api import IAgentRuntime
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter

    mock_orchestrator = AsyncMock()
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    assert isinstance(adapter, IAgentRuntime), "Adapter voldoet niet aan IAgentRuntime Protocol"


@pytest.mark.unit
async def test_adapter_orchestrate_delegates_to_process_task() -> None:
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter
    from src.core.shared.interfaces import ExecutionResult, TaskData

    mock_orchestrator = AsyncMock()
    mock_orchestrator.process_task.return_value = ExecutionResult(task_id="t1", success=True)
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    task = TaskData(title="test", description="test task")
    result = await adapter.orchestrate(task)
    mock_orchestrator.process_task.assert_awaited_once_with(task)
    assert result.success is True


@pytest.mark.unit
async def test_adapter_get_health_returns_status_dict() -> None:
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter

    mock_orchestrator = AsyncMock()
    mock_orchestrator.get_capabilities.return_value = []
    mock_orchestrator.llm_client = MagicMock()  # explicit: healthy path
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    health = await adapter.get_health()
    assert "status" in health
    assert isinstance(health["status"], str)


@pytest.mark.unit
def test_get_agent_runtime_works_after_register(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.core.agents.api as facade
    from src.core.agents.api import get_agent_runtime, register_agent_runtime, IAgentRuntime

    monkeypatch.setattr(facade, "_agent_runtime_instance", None)
    fake_runtime = MagicMock(spec=IAgentRuntime)
    register_agent_runtime(fake_runtime)
    result = get_agent_runtime()
    assert result is fake_runtime


@pytest.mark.unit
def test_get_agent_runtime_raises_if_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.core.agents.api as facade
    from src.core.agents.api import get_agent_runtime

    monkeypatch.setattr(facade, "_agent_runtime_instance", None)
    with pytest.raises(RuntimeError, match="not registered"):
        get_agent_runtime()


@pytest.mark.unit
async def test_adapter_route_delegates_to_process_task() -> None:
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter
    from src.core.shared.interfaces import ExecutionResult, TaskData

    mock_orchestrator = AsyncMock()
    mock_orchestrator.process_task.return_value = ExecutionResult(task_id="t1", success=True)
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    task = TaskData(title="test", description="route test")
    result = await adapter.route(task)
    mock_orchestrator.process_task.assert_awaited_once_with(task)
    assert result.success is True


@pytest.mark.unit
async def test_adapter_get_health_reflects_llm_state() -> None:
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter

    mock_orchestrator = AsyncMock()
    mock_orchestrator.get_capabilities.return_value = []
    mock_orchestrator.llm_client = None
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    health = await adapter.get_health()
    assert health["status"] == "degraded"
    assert health["llm_ready"] is False


@pytest.mark.unit
async def test_adapter_get_health_healthy_when_llm_ready() -> None:
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter

    mock_orchestrator = AsyncMock()
    mock_orchestrator.get_capabilities.return_value = []
    mock_orchestrator.llm_client = MagicMock()
    adapter = MasterOrchestratorRuntimeAdapter(mock_orchestrator)
    health = await adapter.get_health()
    assert health["status"] == "healthy"
    assert health["llm_ready"] is True


@pytest.mark.unit
async def test_facade_not_registered_when_orchestrator_init_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When orchestrator init returns False, facade is not registered (lifespan conditional)."""
    import src.core.agents.api as facade_module
    from src.core.agents.api import get_agent_runtime, register_agent_runtime
    from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter

    monkeypatch.setattr(facade_module, "_agent_runtime_instance", None)
    mock_orch = AsyncMock()
    mock_orch.initialize = AsyncMock(return_value=False)

    init_ok = await mock_orch.initialize()
    if init_ok:
        register_agent_runtime(MasterOrchestratorRuntimeAdapter(mock_orch))

    with pytest.raises(RuntimeError, match="not registered"):
        get_agent_runtime()
