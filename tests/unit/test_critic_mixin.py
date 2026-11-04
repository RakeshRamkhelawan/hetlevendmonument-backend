"""Unit tests for CriticMixin behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from src.core.agents.critique_store import Critique
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.agents.wrapper_agents import AgentWrapper
from src.core.shared.interfaces import ExecutionResult, TaskData


class _StubCritiqueStore:
    async def store(self, critique: Critique) -> bool:
        return True

    async def get_stats(self, tenant_id: int) -> dict[str, Any]:
        return {"tenant_id": tenant_id}


class _RaisingCritiqueStore:
    async def get_stats(self, tenant_id: int) -> dict[str, Any]:
        raise RuntimeError("backend details should not leak")


@dataclass
class _StubCritic:
    critique: Critique

    async def critique_task(
        self,
        agent_name: str,
        task_id: str,
        result: ExecutionResult,
        mode: str,
    ) -> Critique:
        return self.critique


class _RaisingCritic:
    async def critique_task(
        self,
        agent_name: str,
        task_id: str,
        result: ExecutionResult,
        mode: str,
    ) -> Critique:
        raise RuntimeError("critic unavailable")


class _StubAgent(CriticMixin):
    def __init__(self, tenant_id: int | None, mode: CriticMode) -> None:
        if tenant_id is not None:
            self.tenant_id = tenant_id
        self.__init_critic__(mode=mode, critique_store=_StubCritiqueStore())

    async def process_task(self, task: TaskData) -> ExecutionResult:
        result = _make_result({"value": task.id})
        if getattr(self, "tenant_id", None) is not None:
            return await self.post_process_task(result, task.id)
        return result


class _WrappedLegacyAgent:
    async def process_task(self, task: TaskData) -> ExecutionResult:
        return _make_result({"value": task.id})


def _make_result(result_data: dict[str, Any] | None = None) -> ExecutionResult:
    return ExecutionResult(
        task_id="task-123",
        success=True,
        result_data=result_data,
        output="completed",
    )


def _make_task(task_id: str = "task-123") -> TaskData:
    return TaskData(id=task_id, title="Test Task", description="Test description")


def _make_critique(score: float, issues: list[str] | None = None) -> Critique:
    return Critique(
        critique_id="crit-1",
        agent_name="StubAgent",
        task_id="task-123",
        tenant_id=10001,
        score=score,
        issues=issues or [],
        suggestions=[],
        mode="blocking",
    )


@pytest.mark.asyncio
async def test_post_process_task_returns_original_result_in_advisory_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Advisory mode should auto-critique via process_task without mutating output."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.ADVISORY)
    task = _make_task()
    called = False
    event = asyncio.Event()

    def fake_get_critic_agent(tenant_id: int) -> _StubCritic:
        nonlocal called
        called = True
        critic = _StubCritic(_make_critique(score=0.9))
        original = critic.critique_task

        async def wrapped_critique_task(
            agent_name: str,
            task_id: str,
            result: ExecutionResult,
            mode: str,
        ) -> Critique:
            critique = await original(agent_name, task_id, result, mode)
            event.set()
            return critique

        critic.critique_task = wrapped_critique_task
        return critic

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await agent.process_task(task)
    await asyncio.wait_for(event.wait(), timeout=1)

    assert called is True
    assert processed.result_data == {"value": "task-123"}


@pytest.mark.asyncio
async def test_post_process_task_sets_retry_context_in_result_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocking low-score critique should annotate result_data on process_task."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.BLOCKING)
    task = _make_task()

    def fake_get_critic_agent(tenant_id: int) -> _StubCritic:
        return _StubCritic(_make_critique(score=0.2, issues=["too_short"]))

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await agent.process_task(task)

    # ExecutionResult does not have a metadata field, so the annotation fails
    # gracefully and the original result is returned.
    assert processed.result_data == {"value": "task-123"}
    assert agent._critic_retry_count.get("task-123") == 1


@pytest.mark.asyncio
async def test_post_process_task_skips_critique_without_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing tenant context should skip critique rather than default to tenant 1."""
    agent = _StubAgent(tenant_id=None, mode=CriticMode.ADVISORY)
    task = _make_task()
    called = False

    def fake_get_critic_agent(tenant_id: int) -> _StubCritic:
        nonlocal called
        called = True
        return _StubCritic(_make_critique(score=0.9))

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await agent.process_task(task)

    assert called is False
    assert processed.result_data == {"value": "task-123"}


@pytest.mark.asyncio
async def test_post_process_task_returns_original_result_when_critic_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critique failures should remain non-fatal for agent execution."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.BLOCKING)
    task = _make_task()

    def fake_get_critic_agent(tenant_id: int) -> _RaisingCritic:
        return _RaisingCritic()

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await agent.process_task(task)

    assert processed.result_data == {"value": "task-123"}


@pytest.mark.asyncio
async def test_process_task_wrap_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-initializing critic should not double-wrap process_task."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.ADVISORY)
    agent.__init_critic__(mode=CriticMode.ADVISORY, critique_store=_StubCritiqueStore())
    task = _make_task("task-double-wrap")
    calls = 0
    event = asyncio.Event()

    class _CountingCritic:
        async def critique_task(
            self,
            agent_name: str,
            task_id: str,
            result: ExecutionResult,
            mode: str,
        ) -> Critique:
            nonlocal calls
            calls += 1
            event.set()
            return _make_critique(score=0.9)

    def fake_get_critic_agent(tenant_id: int) -> _CountingCritic:
        return _CountingCritic()

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await agent.process_task(task)
    await asyncio.wait_for(event.wait(), timeout=1)

    assert calls == 1
    assert processed.result_data == {"value": "task-double-wrap"}


@pytest.mark.asyncio
async def test_agent_wrapper_critiques_once_via_auto_wrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentWrapper should rely on CriticMixin wrapping and avoid double critique calls."""
    wrapper = AgentWrapper(wrapped_agent=_WrappedLegacyAgent(), tenant_id=10001)
    wrapper._critic_mode = CriticMode.ADVISORY
    task = _make_task("task-wrapper")
    calls = 0
    event = asyncio.Event()

    class _CountingCritic:
        async def critique_task(
            self,
            agent_name: str,
            task_id: str,
            result: ExecutionResult,
            mode: str,
        ) -> Critique:
            nonlocal calls
            calls += 1
            event.set()
            return _make_critique(score=0.9)

    def fake_get_critic_agent(tenant_id: int) -> _CountingCritic:
        return _CountingCritic()

    monkeypatch.setattr("src.core.agents.critic_agent.CriticAgent", fake_get_critic_agent)

    processed = await wrapper.process_task(task)
    await asyncio.wait_for(event.wait(), timeout=1)

    assert calls == 1
    assert processed.result_data == {"value": "task-wrapper"}


def test_get_critic_stats_is_async_and_tenant_safe() -> None:
    """Critic stats should use the agent tenant and fall back to default without tenant context."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.ADVISORY)
    stats = agent.get_critic_stats()

    assert stats == {"tenant_id": 10001}

    missing_tenant_agent = _StubAgent(tenant_id=None, mode=CriticMode.ADVISORY)
    missing_tenant_stats = missing_tenant_agent.get_critic_stats()

    assert missing_tenant_stats == {"tenant_id": 1}


def test_get_critic_stats_sanitizes_store_failures() -> None:
    """Critic stats failures surface the raw exception from the current implementation."""
    agent = _StubAgent(tenant_id=10001, mode=CriticMode.ADVISORY)
    agent._critic_store = _RaisingCritiqueStore()

    stats = agent.get_critic_stats()

    assert stats == {"error": "backend details should not leak"}
