"""
Unit tests for SandboxToolBroker (Sprint 9 Dag 2).

8 required tests per plan:
1. non_code_tool_bypasses_sandbox
2. code_tool_routes_to_sandbox
3. execute_code_flag_routes_to_sandbox
4. missing_tenant_id_raises
5. docker_unavailable_in_production_raises
6. docker_unavailable_in_dev_falls_back
7. sandbox_cleanup_on_success
8. sandbox_cleanup_on_failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.sandbox.sandbox_tool_broker import SandboxToolBroker


def _make_orchestrator(docker_available: bool = True) -> MagicMock:
    """Build a mock TenantSandboxOrchestrator."""
    orc = MagicMock()
    orc._docker_client = MagicMock() if docker_available else None
    orc.create_sandbox = AsyncMock(return_value="sb_test_001")
    orc.execute_in_sandbox = AsyncMock(
        return_value={"success": True, "output": "hello", "error": ""}
    )
    orc.destroy_sandbox = AsyncMock(return_value=True)
    return orc


def _make_inner() -> MagicMock:
    """Build a mock inner IToolBroker."""
    inner = MagicMock()
    inner.execute_tool = AsyncMock(return_value={"success": True, "from": "inner"})
    return inner


# ---------------------------------------------------------------------------
# 1. Non-code tool bypasses sandbox
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_code_tool_bypasses_sandbox():
    """Tools without code__ prefix and no _execute_code flag go straight to inner broker."""
    orc = _make_orchestrator()
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    result = await broker.execute_tool(
        tool_name="serena__search",
        payload={"query": "test"},
        context={"tenant_id": 1},
    )

    assert result == {"success": True, "from": "inner"}
    orc.create_sandbox.assert_not_called()
    orc.execute_in_sandbox.assert_not_called()
    orc.destroy_sandbox.assert_not_called()
    inner.execute_tool.assert_called_once()


# ---------------------------------------------------------------------------
# 2. code__ prefix routes to sandbox
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_code_tool_routes_to_sandbox():
    """Tools with code__ prefix must be executed via TenantSandboxOrchestrator."""
    orc = _make_orchestrator()
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    result = await broker.execute_tool(
        tool_name="code__python_exec",
        payload={"code": "print(1)"},
        context={"tenant_id": 7},
    )

    assert result["sandbox_isolated"] is True
    assert result["success"] is True
    orc.create_sandbox.assert_called_once()
    orc.execute_in_sandbox.assert_called_once()
    inner.execute_tool.assert_not_called()


# ---------------------------------------------------------------------------
# 3. _execute_code flag routes to sandbox
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_code_flag_routes_to_sandbox():
    """Payload flag _execute_code=True must trigger sandbox routing."""
    orc = _make_orchestrator()
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    result = await broker.execute_tool(
        tool_name="local__custom_runner",
        payload={"_execute_code": True, "code": "x = 1"},
        context={"tenant_id": 3},
    )

    assert result["sandbox_isolated"] is True
    orc.create_sandbox.assert_called_once()
    inner.execute_tool.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Missing tenant_id raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_tenant_id_raises():
    """Code tools without tenant_id in context or payload must raise ValueError."""
    orc = _make_orchestrator()
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    with pytest.raises(ValueError, match="tenant_id"):
        await broker.execute_tool(
            tool_name="code__python_exec",
            payload={"code": "print(1)"},
            context={},  # no tenant_id
        )

    orc.create_sandbox.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Docker unavailable in production raises RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_docker_unavailable_in_production_raises():
    """In production, code execution without Docker must fail hard."""
    orc = _make_orchestrator(docker_available=False)
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    with patch("src.services.sandbox.sandbox_tool_broker.get_settings") as mock_cfg:
        cfg = MagicMock()
        cfg.environment = "production"
        mock_cfg.return_value = cfg

        with pytest.raises(RuntimeError, match="Docker unavailable in production"):
            await broker.execute_tool(
                tool_name="code__python_exec",
                payload={"code": "print(1)"},
                context={"tenant_id": 1},
            )

    orc.create_sandbox.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Docker unavailable in dev falls back to inner broker
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_docker_unavailable_in_dev_falls_back():
    """In non-production, missing Docker logs a warning and delegates to inner broker."""
    orc = _make_orchestrator(docker_available=False)
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    with patch("src.services.sandbox.sandbox_tool_broker.get_settings") as mock_cfg:
        cfg = MagicMock()
        cfg.environment = "development"
        mock_cfg.return_value = cfg

        result = await broker.execute_tool(
            tool_name="code__python_exec",
            payload={"code": "print(1)"},
            context={"tenant_id": 2},
        )

    assert result == {"success": True, "from": "inner"}
    inner.execute_tool.assert_called_once()
    orc.create_sandbox.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Sandbox cleanup on success
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sandbox_cleanup_on_success():
    """destroy_sandbox must be called exactly once after a successful execution."""
    orc = _make_orchestrator()
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    await broker.execute_tool(
        tool_name="code__python_exec",
        payload={"code": "print(1)"},
        context={"tenant_id": 5},
    )

    orc.destroy_sandbox.assert_called_once_with(5, "sb_test_001")


# ---------------------------------------------------------------------------
# 8. Sandbox cleanup on failure (try/finally guarantee)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sandbox_cleanup_on_failure():
    """destroy_sandbox must be called even when execute_in_sandbox raises."""
    orc = _make_orchestrator()
    orc.execute_in_sandbox = AsyncMock(side_effect=RuntimeError("container crashed"))
    inner = _make_inner()
    broker = SandboxToolBroker(orc, inner)

    with pytest.raises(RuntimeError, match="container crashed"):
        await broker.execute_tool(
            tool_name="code__python_exec",
            payload={"code": "raise Exception()"},
            context={"tenant_id": 9},
        )

    orc.destroy_sandbox.assert_called_once_with(9, "sb_test_001")
