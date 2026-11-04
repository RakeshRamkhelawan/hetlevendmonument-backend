import time
from unittest.mock import AsyncMock, patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.learning.auto_learning import auto_learn
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class _DecoratedAgent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"ok": True})

    @auto_learn()
    async def custom_async(self, value: int) -> dict:
        return {"value": value, "success": True}

    @auto_learn(enabled=False)
    async def disabled_async(self) -> dict:
        return {"success": True}

    @auto_learn()
    async def failing_async(self) -> dict:
        raise RuntimeError("boom")

    @auto_learn()
    def sync_method(self, value: int) -> int:
        return value + 1

    @auto_learn()
    async def numeric_async(self) -> int:
        return 7


def _make_agent() -> _DecoratedAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.agents.mixins.learning_mixin.get_feature_flag", return_value=True),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return _DecoratedAgent(
            agent_id="decorated-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )


@pytest.mark.asyncio
async def test_decorator_records_generic_async_method() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock(return_value="obs-1")
    result = await agent.custom_async(5)
    assert result["value"] == 5
    agent._record_method_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_decorator_records_process_task_via_task_observation() -> None:
    agent = _make_agent()
    agent._record_task_observation = AsyncMock(return_value="obs-task")
    task = TaskData(id="t1", title="Task", description="Desc", metadata={"type": "text"})
    result = await agent.process_task(task)
    assert result.success is True
    agent._record_task_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_decorator_preserves_exception_and_records_failure() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock(return_value="obs-fail")
    with pytest.raises(RuntimeError, match="boom"):
        await agent.failing_async()
    agent._record_method_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_decorator_disabled_skips_recording() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock()
    await agent.disabled_async()
    agent._record_method_observation.assert_not_called()


def test_decorator_preserves_metadata() -> None:
    assert _DecoratedAgent.custom_async.__name__ == "custom_async"


def test_sync_wrapper_preserves_return_value() -> None:
    agent = _make_agent()
    assert agent.sync_method(2) == 3


@pytest.mark.asyncio
async def test_execute_tool_is_decorated() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock(return_value="obs-tool")
    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True, "data": 1})
    agent._tool_broker = broker
    agent.emit_event = AsyncMock()
    result = await agent.execute_tool("test__echo", {"value": 1})
    assert result["data"] == 1
    agent._record_method_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_decorator_records_non_dict_results() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock(return_value="obs-number")

    result = await agent.numeric_async()

    assert result == 7
    agent._record_method_observation.assert_awaited_once()


@pytest.mark.asyncio
async def test_decorator_overhead_stays_small() -> None:
    agent = _make_agent()
    agent._record_method_observation = AsyncMock(return_value="obs-perf")
    start = time.perf_counter()
    for _ in range(50):
        await agent.custom_async(1)
    elapsed_ms = (time.perf_counter() - start) * 1000 / 50
    assert elapsed_ms < 20
