"""
Sprint 9 Dag 1 -- unit tests for the four P0 bug fixes.

Fix 1: executor_agent._execute_system_commands uses sandbox, no subprocess.run()
Fix 2: sandbox_manager._prepare_execution_script f-string interpolation
Fix 3: health.DegradationStrategy.execute no longer raises NotImplementedError
Fix 4: tool_broker/router /auth/token returns 501 in production
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Deze tests bouwen een sandbox in een constructor, en die roept `docker.from_env()` aan
# -- een ECHTE verbinding naar de Docker-daemon (ADR-036 OP-214).
from tests.fixtures.docker_sandbox import geen_echte_docker_daemon  # noqa: F401

# Stubs used in tests -- these are NOT real credentials
_PW_VALID = "x" * 12  # satisfies the >= 8 chars check
_PW_INVALID = "short"  # fails the >= 8 chars check


# ---------------------------------------------------------------------------
# Fix 1 -- ExecutorAgent: subprocess elimination
# ---------------------------------------------------------------------------


class TestExecutorAgentSandboxFix:
    """_execute_system_commands must route through sandbox, never subprocess."""

    def _make_agent_with_sandbox(self, sandbox_mock):
        from src.core.agents.executor_agent import ExecutorAgent

        agent = ExecutorAgent()
        agent.sandbox_manager = sandbox_mock
        return agent

    def _make_task(self, commands):
        from src.core.shared.interfaces import TaskData

        return TaskData(
            id="t1",
            title="test",
            description="",
            metadata={"type": "system_commands", "commands": commands},
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_routes_through_sandbox(self):
        """When sandbox is available, commands execute inside sandbox isolation."""
        from src.core.shared.interfaces import ExecutionResult

        sandbox = MagicMock()
        sandbox.create_sandbox = AsyncMock(return_value="sb_123")
        sandbox.execute_in_sandbox = AsyncMock(
            return_value=ExecutionResult(
                task_id="t1",
                success=True,
                result_data={"output": "hi"},
            )
        )
        sandbox.destroy_sandbox = AsyncMock()

        agent = self._make_agent_with_sandbox(sandbox)
        task = self._make_task(["echo hi"])

        result = await agent._execute_system_commands(task)

        assert result["success"] is True
        assert result["sandbox_isolated"] is True
        sandbox.create_sandbox.assert_called_once()
        sandbox.destroy_sandbox.assert_called_once_with("sb_123")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unhappy_path_no_sandbox_returns_error(self):
        """When sandbox_manager is None, return structured error without crashing."""
        from src.core.agents.executor_agent import ExecutorAgent
        from src.core.shared.interfaces import TaskData

        agent = ExecutorAgent()
        agent.sandbox_manager = None
        task = TaskData(
            id="t2",
            title="test",
            description="",
            metadata={"type": "system_commands", "commands": ["echo hi"]},
        )

        result = await agent._execute_system_commands(task)

        assert result["success"] is False
        assert "sandbox" in result["error"].lower()
        assert result.get("sandbox_isolated") is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sandbox_cleanup_called_even_on_exception(self):
        """destroy_sandbox must be called even when execute_in_sandbox raises."""
        sandbox = MagicMock()
        sandbox.create_sandbox = AsyncMock(return_value="sb_456")
        sandbox.execute_in_sandbox = AsyncMock(side_effect=RuntimeError("boom"))
        sandbox.destroy_sandbox = AsyncMock()

        agent = self._make_agent_with_sandbox(sandbox)
        from src.core.shared.interfaces import TaskData

        task = TaskData(
            id="t3",
            title="test",
            description="",
            metadata={"type": "system_commands", "commands": ["echo hi"]},
        )

        result = await agent._execute_system_commands(task)

        assert result["success"] is False
        sandbox.destroy_sandbox.assert_called_once_with("sb_456")

    @pytest.mark.unit
    def test_subprocess_not_imported_at_module_level(self):
        """subprocess must not appear as a module-level import in executor_agent."""
        import types

        import src.core.agents.executor_agent as mod

        assert not isinstance(getattr(mod, "subprocess", None), types.ModuleType), (
            "subprocess must not be a top-level attribute of executor_agent"
        )


# ---------------------------------------------------------------------------
# Fix 2 -- sandbox_manager._prepare_execution_script f-string
# ---------------------------------------------------------------------------


class TestSandboxManagerFStringFix:
    """_prepare_execution_script must interpolate code into the template."""

    def _make_manager(self):
        from src.core.sandbox.sandbox_manager import DockerSandboxManager

        return DockerSandboxManager()

    def _make_task(self, task_type: str, **meta):
        from src.core.shared.interfaces import TaskData

        return TaskData(
            id="t-fstr",
            title="MyTask",
            description="",
            metadata={"type": task_type, **meta},
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_python_code_interpolates_code_into_template(self):
        """python_code template must contain the user code, not the literal placeholder."""
        manager = self._make_manager()
        task = self._make_task("python_code", code="x = 42\nprint(x)")

        script = await manager._prepare_execution_script(task)

        assert "    x = 42" in script, "Code must be indented inside the try block"
        assert "    print(x)" in script
        assert "{indented_code}" not in script, "Literal placeholder must not appear in output"
        assert "try:" in script
        assert "except Exception as e:" in script

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_python_code_default_when_no_code_provided(self):
        """Without 'code' key in metadata, the default code must be emitted."""
        manager = self._make_manager()
        task = self._make_task("python_code")

        script = await manager._prepare_execution_script(task)

        assert "No code provided" in script
        assert "{indented_code}" not in script

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generic_task_interpolates_title_and_id(self):
        """Generic template must interpolate task.title and task.id."""
        manager = self._make_manager()
        task = self._make_task("generic_task")

        script = await manager._prepare_execution_script(task)

        assert "MyTask" in script, "task.title must be interpolated"
        assert "t-fstr" in script, "task.id must be interpolated"
        assert "{task.title}" not in script, "Literal placeholder must not appear"
        assert "{task.id}" not in script


# ---------------------------------------------------------------------------
# Fix 3 -- DegradationStrategy.execute no longer raises NotImplementedError
# ---------------------------------------------------------------------------


class TestDegradationStrategyFix:
    """Base DegradationStrategy.execute must return {} rather than raising."""

    def _make_health(self):
        from src.core.tool_broker.health import ServiceHealth

        return ServiceHealth(service_name="test_svc")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_returns_empty_dict(self):
        """Base class execute must return an empty dict without raising."""
        from src.core.tool_broker.health import DegradationStrategy

        strategy = DegradationStrategy(name="base", description="test")
        health = self._make_health()

        result = await strategy.execute(health)

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unhappy_path_no_not_implemented_error(self):
        """NotImplementedError must never be raised by the base class."""
        from src.core.tool_broker.health import DegradationStrategy

        strategy = DegradationStrategy(name="base", description="test")
        health = self._make_health()

        try:
            await strategy.execute(health)
        except NotImplementedError:
            pytest.fail("DegradationStrategy.execute raised NotImplementedError")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_circuit_breaker_subclass_still_overrides(self):
        """CircuitBreakerDegradation must still return its own result."""
        from src.core.tool_broker.health import CircuitBreakerDegradation

        strategy = CircuitBreakerDegradation()
        health = self._make_health()

        result = await strategy.execute(health)

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Fix 4 -- tool_broker/router /auth/token production guard
# ---------------------------------------------------------------------------

