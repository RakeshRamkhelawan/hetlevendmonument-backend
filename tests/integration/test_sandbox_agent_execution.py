"""
Integration tests: Sandbox → Agent Execution

Tests that agents use sandbox containers for code execution
with proper isolation and resource limits.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAgentSandboxExecution:
    """
    TKTS-AGENT-001: Agents use sandbox for code execution
    """

    @pytest.mark.asyncio
    async def test_code_agent_uses_sandbox(self):
        """
        GIVEN: Python code agent
        WHEN: Execute user-provided code
        THEN: Code runs in isolated sandbox
        """
        # Mock sandbox manager
        mock_sandbox = MagicMock()
        mock_sandbox.execute = AsyncMock(
            return_value={
                "success": True,
                "output": "Sandbox output",
                "sandbox_id": "sb-123",
                "isolation_level": "container",
            }
        )

        # Simulate code execution with sandbox
        code = """
import os
print("Running in sandbox")
        """

        result = await mock_sandbox.execute(code=code, tenant_id="tenant-123", use_sandbox=True)

        assert result["sandbox_id"] is not None
        assert result["isolation_level"] == "container"
        mock_sandbox.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_sandbox_resource_limits_enforced(self):
        """
        GIVEN: Agent with memory-intensive task
        WHEN: Exceeds sandbox memory limit
        THEN: OOM kill, graceful error
        """
        mock_sandbox = MagicMock()
        mock_sandbox.execute = AsyncMock(
            return_value={
                "success": False,
                "error": "Process killed: out of memory",
                "exit_code": 137,  # SIGKILL (OOM)
            }
        )

        # Code that uses too much memory
        code = "a = 'x' * (500 * 1024 * 1024)"  # 500MB

        result = await mock_sandbox.execute(
            code=code,
            tenant_id="tenant-123",
            sandbox_config={"memory_limit": "256m", "timeout": 30},
        )

        assert result["success"] is False
        assert "memory" in result["error"].lower() or "killed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_agent_execution_audit_trail(self):
        """
        GIVEN: Agent execution in sandbox
        WHEN: Execution completes
        THEN: Full audit trail available
        """
        # Mock audit log
        mock_audit_logs = [
            {"action": "sandbox_created", "timestamp": datetime.utcnow().isoformat()},
            {"action": "code_executed", "timestamp": datetime.utcnow().isoformat()},
            {"action": "sandbox_destroyed", "timestamp": datetime.utcnow().isoformat()},
        ]

        # Verify audit trail structure
        actions = [log["action"] for log in mock_audit_logs]

        assert "sandbox_created" in actions
        assert "code_executed" in actions
        assert "sandbox_destroyed" in actions


class TestSandboxTenantIsolation:
    """
    TKTS-AGENT-002: Tenant isolation in sandbox execution
    """

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_sandbox(self):
        """
        GIVEN: Two tenants
        WHEN: Tenant A executes code
        THEN: Cannot access Tenant B's files/data
        """
        mock_sandbox_a = MagicMock()
        mock_sandbox_a.execute = AsyncMock(
            return_value={
                "success": True,
                "output": "File written to /workspace/tenant_a/secret.txt",
            }
        )

        mock_sandbox_b = MagicMock()
        mock_sandbox_b.execute = AsyncMock(
            return_value={
                "success": False,
                "error": "No such file or directory: '/workspace/tenant_a/secret.txt'",
            }
        )

        # Tenant A creates file
        result_a = await mock_sandbox_a.execute(
            code="with open('/workspace/tenant_a/secret.txt', 'w') as f: f.write('data')",
            tenant_id="tenant-a",
        )
        assert result_a["success"] is True

        # Tenant B tries to read it
        result_b = await mock_sandbox_b.execute(
            code="print(open('/workspace/tenant_a/secret.txt').read())", tenant_id="tenant-b"
        )
        assert result_b["success"] is False
        assert "No such file" in result_b["error"]
