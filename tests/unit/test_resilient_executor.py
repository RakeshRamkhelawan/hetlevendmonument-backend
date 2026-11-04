import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.sandbox.resilient_executor import (
    ExecutionResult,
    HealingPolicy,
    ResilientSandboxExecutor,
    SandboxConfig,
    SandboxType,
)
from src.core.sandbox.tenant_sandbox_orchestrator import TenantSandboxOrchestrator


@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock(spec=TenantSandboxOrchestrator)
    # Async methods must be AsyncMock
    orchestrator.create_sandbox = AsyncMock(return_value="sandbox_123")
    orchestrator.execute_in_sandbox = AsyncMock()
    orchestrator.destroy_sandbox = AsyncMock(return_value=True)
    return orchestrator


@pytest.fixture
def executor(mock_orchestrator):
    return ResilientSandboxExecutor(mock_orchestrator)


@pytest.mark.asyncio
async def test_execute_success_no_healing(executor, mock_orchestrator):
    """Test standard execution with no failure"""
    mock_orchestrator.execute_in_sandbox.return_value = {
        "success": True,
        "output": "Success",
        "error": "",
        "exit_code": 0,
        "cost_credits": 0.1,
    }

    result = await executor.execute_with_healing(1, "print('ok')")

    assert result.success is True
    assert result.output == "Success"
    assert result.healing_applied is False
    assert mock_orchestrator.execute_in_sandbox.call_count == 1


@pytest.mark.asyncio
async def test_execute_failure_retry_loop(executor, mock_orchestrator):
    """
    Test that failure triggers the retry loop.
    We verify it runs max_retries times if the patch is applied but fails again.
    """
    # Always fail
    mock_orchestrator.execute_in_sandbox.return_value = {
        "success": False,
        "output": "",
        "error": "SyntaxError",
        "exit_code": 1,
        "cost_credits": 0.1,
    }

    mock_orchestrator.create_sandbox.side_effect = [
        "sandbox_1",
        "sandbox_2",
        "sandbox_3",
    ]

    # Mock diagnose to ALWAYS return "changed" code so loop continues
    with patch.object(executor, "_diagnose_and_patch", new_callable=AsyncMock) as mock_patch:
        mock_patch.side_effect = lambda t, c, e, p, h: c + "\n# patched"

        policy = HealingPolicy(max_retries=2)
        result = await executor.execute_with_healing(tenant_id=1, code="fail", policy=policy)

        assert result.success is False
        assert result.healing_applied is True
        assert result.healing_attempts == 2
        # Call count: 1 initial + 2 retries = 3
        assert mock_orchestrator.execute_in_sandbox.call_count == 3

        # Cost check: 0.1 * 3 = 0.3
        assert abs(result.cost_credits - 0.3) < 0.0001


@pytest.mark.asyncio
async def test_test_driven_verification_logic(executor, mock_orchestrator):
    """Test that verification scripts are wrapped correctly"""
    mock_orchestrator.execute_in_sandbox.return_value = {
        "success": True,
        "output": "VERIFICATION_SUCCESS",
        "exit_code": 0,
    }

    await executor.execute_with_healing(1, "x = 1", verification_script="assert x == 1")

    # Verify the code sent to orchestrator includes the wrapper
    args, _ = mock_orchestrator.execute_in_sandbox.call_args
    sent_code = args[2]  # 3rd arg is code

    assert "try:" in sent_code
    assert "assert x == 1" in sent_code
    assert "VERIFICATION_SUCCESS" in sent_code


@pytest.mark.asyncio
async def test_successful_healing_mock(executor, mock_orchestrator):
    """
    Test a scenario where patching 'works' (simulated by mocking execute to return success on 2nd call).
    And we patch _diagnose_and_patch to return 'fixed_code'
    """
    # 1. Fail
    # 2. Success
    mock_orchestrator.execute_in_sandbox.side_effect = [
        {"success": False, "error": "Fail", "cost_credits": 0.1},
        {"success": True, "output": "Fixed", "cost_credits": 0.1},
    ]

    # Mock the patcher to change the code
    with patch.object(executor, "_diagnose_and_patch", new_callable=AsyncMock) as mock_patch:
        mock_patch.return_value = "fixed_code"

        result = await executor.execute_with_healing(
            1, "broken_code", policy=HealingPolicy(max_retries=1)
        )

        assert result.success is True
        assert result.output == "Fixed"
        assert result.healing_attempts == 1
        assert "SUCCESS. Fix applied" in result.healing_log[-1]

        # Verify patch was called
        mock_patch.assert_called_once()


@pytest.mark.asyncio
async def test_execute_abort_when_no_fix(executor, mock_orchestrator):
    """Test that loop aborts if doctor cannot generate a new patch"""
    mock_orchestrator.execute_in_sandbox.return_value = {
        "success": False,
        "error": "Fail",
        "cost_credits": 0.1,
    }

    # Mock diagnose to return SAME code (no fix)
    # The real implementation is a no-op, so we don't strictly need to patch it if we rely on default,
    # but explicit patching is safer against future changes.
    with patch.object(executor, "_diagnose_and_patch", new_callable=AsyncMock) as mock_patch:
        mock_patch.return_value = "fail"  # Same as input code

        result = await executor.execute_with_healing(1, "fail", policy=HealingPolicy(max_retries=5))

        # Should abort after 1 attempt, not 5
        assert result.healing_attempts == 1
        assert "No fix generated" in result.healing_log[-1]


@pytest.mark.asyncio
async def test_singleton_getter():
    """Test the global getter function"""
    from src.core.sandbox.resilient_executor import get_resilient_executor

    # We need to mock get_sandbox_orchestrator because get_resilient_executor calls it
    with patch("src.core.sandbox.resilient_executor.get_sandbox_orchestrator") as mock_get_orch:
        mock_get_orch.return_value = AsyncMock()  # Mock orchestrator

        instance1 = await get_resilient_executor()
        instance2 = await get_resilient_executor()

        assert isinstance(instance1, ResilientSandboxExecutor)
        assert instance1 is instance2  # Singleton check
