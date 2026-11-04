"""E2E integration test: Copilot -> SandboxToolBroker -> TenantSandboxOrchestrator.

Behavioral: a user sends a code execution request via Copilot.
SandboxToolBroker routes it to the orchestrator.
Result contains sandbox_isolated=True and cleanup is guaranteed.

Security: destroy_sandbox is always called, even on failure.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.copilot.protocols import IToolBroker
from src.core.sandbox.tenant_sandbox_orchestrator import TenantSandboxOrchestrator
from src.services.sandbox.sandbox_tool_broker import SandboxToolBroker


@pytest.mark.integration
class TestCopilotSandboxE2E:
    @pytest.mark.asyncio
    async def test_code_tool_executes_in_sandbox(self):
        """
        Code tool with 'code__' prefix routes to orchestrator.
        Result contains sandbox_isolated=True.
        """
        orchestrator = MagicMock(spec=TenantSandboxOrchestrator)
        orchestrator._docker_client = MagicMock()  # Docker available
        orchestrator.create_sandbox = AsyncMock(return_value="sandbox_test_001")
        orchestrator.execute_in_sandbox = AsyncMock(
            return_value={
                "success": True,
                "output": "hello world",
                "error": "",
                "exit_code": 0,
                "execution_time": 0.4,
                "cost_credits": 1,
            }
        )
        orchestrator.destroy_sandbox = AsyncMock(return_value=True)

        inner_broker = MagicMock(spec=IToolBroker)
        inner_broker.execute_tool = AsyncMock()
        broker = SandboxToolBroker(orchestrator, inner_broker)

        result = await broker.execute_tool(
            tool_name="code__python_exec",
            payload={"code": "print('hello world')", "language": "python"},
            context={"tenant_id": 1, "user_id": 42},
        )

        assert result["sandbox_isolated"] is True
        assert result["success"] is True
        orchestrator.create_sandbox.assert_awaited_once()
        orchestrator.execute_in_sandbox.assert_awaited_once()
        inner_broker.execute_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_destroy_sandbox_called_on_success(self):
        """Cleanup is guaranteed after successful execution."""
        orchestrator = MagicMock(spec=TenantSandboxOrchestrator)
        orchestrator._docker_client = MagicMock()
        orchestrator.create_sandbox = AsyncMock(return_value="sandbox_cleanup_test")
        orchestrator.execute_in_sandbox = AsyncMock(
            return_value={"success": True, "output": "ok", "error": "", "exit_code": 0}
        )
        orchestrator.destroy_sandbox = AsyncMock(return_value=True)

        broker = SandboxToolBroker(orchestrator, MagicMock(spec=IToolBroker))

        await broker.execute_tool(
            tool_name="code__python_exec",
            payload={"code": "pass"},
            context={"tenant_id": 1},
        )

        orchestrator.destroy_sandbox.assert_awaited_once_with(1, "sandbox_cleanup_test")

    @pytest.mark.asyncio
    async def test_destroy_sandbox_called_on_failure(self):
        """Cleanup is guaranteed even when execute_in_sandbox raises."""
        orchestrator = MagicMock(spec=TenantSandboxOrchestrator)
        orchestrator._docker_client = MagicMock()
        orchestrator.create_sandbox = AsyncMock(return_value="sandbox_fail_test")
        orchestrator.execute_in_sandbox = AsyncMock(side_effect=RuntimeError("container died"))
        orchestrator.destroy_sandbox = AsyncMock(return_value=True)

        broker = SandboxToolBroker(orchestrator, MagicMock(spec=IToolBroker))

        with pytest.raises(RuntimeError):
            await broker.execute_tool(
                tool_name="code__python_exec",
                payload={"code": "raise RuntimeError()"},
                context={"tenant_id": 1},
            )

        # Cleanup must still have been called
        orchestrator.destroy_sandbox.assert_awaited_once_with(1, "sandbox_fail_test")

    @pytest.mark.asyncio
    async def test_non_code_tool_bypasses_sandbox(self):
        """Non-code tools pass directly to inner broker, no sandbox created."""
        orchestrator = MagicMock(spec=TenantSandboxOrchestrator)
        orchestrator._docker_client = MagicMock()

        inner_broker = MagicMock(spec=IToolBroker)
        inner_broker.execute_tool = AsyncMock(return_value={"result": "searched"})
        broker = SandboxToolBroker(orchestrator, inner_broker)

        result = await broker.execute_tool(
            tool_name="serena__search",
            payload={"query": "hello"},
            context={"tenant_id": 1},
        )

        assert result == {"result": "searched"}
        orchestrator.create_sandbox.assert_not_called()
        inner_broker.execute_tool.assert_awaited_once()
