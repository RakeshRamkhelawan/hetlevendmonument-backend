import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from src.core.api.sandbox_endpoints import router, create_sandbox, get_sandbox_status
from src.core.auth.api_deps import UserResponse
from src.core.api.setup.app_state import app_state


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/sandbox/create" in paths
    assert "/api/v1/sandbox/{sandbox_id}/status" in paths


@pytest.mark.asyncio
async def test_create_sandbox_not_initialized() -> None:
    current_user = MagicMock(spec=UserResponse)
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = None
    try:
        with pytest.raises(HTTPException) as exc_info:
            await create_sandbox(config={}, current_user=current_user)
        assert exc_info.value.status_code == 503
        assert "not initialized" in exc_info.value.detail
    finally:
        app_state["sandbox_manager"] = orig


@pytest.mark.asyncio
async def test_create_sandbox_success() -> None:
    current_user = MagicMock(spec=UserResponse)
    mock_mgr = MagicMock()
    mock_mgr.create_sandbox = AsyncMock(return_value="sb-12345")
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = mock_mgr
    try:
        res = await create_sandbox(
            config={"isolation_level": "mock", "network_access": True},
            current_user=current_user,
        )
        assert res == {"sandbox_id": "sb-12345", "status": "created"}
        assert mock_mgr.create_sandbox.called
    finally:
        app_state["sandbox_manager"] = orig


@pytest.mark.asyncio
async def test_create_sandbox_error() -> None:
    current_user = MagicMock(spec=UserResponse)
    mock_mgr = MagicMock()
    mock_mgr.create_sandbox = AsyncMock(side_effect=RuntimeError("creation failed"))
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = mock_mgr
    try:
        with pytest.raises(HTTPException) as exc_info:
            await create_sandbox(config={}, current_user=current_user)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."
    finally:
        app_state["sandbox_manager"] = orig


@pytest.mark.asyncio
async def test_get_sandbox_status_not_initialized() -> None:
    current_user = MagicMock(spec=UserResponse)
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = None
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_sandbox_status(sandbox_id="sb-12345", current_user=current_user)
        assert exc_info.value.status_code == 503
    finally:
        app_state["sandbox_manager"] = orig


@pytest.mark.asyncio
async def test_get_sandbox_status_success() -> None:
    current_user = MagicMock(spec=UserResponse)
    mock_mgr = MagicMock()
    mock_mgr.get_sandbox_status = AsyncMock(return_value={"status": "running", "uptime": 120})
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = mock_mgr
    try:
        res = await get_sandbox_status(sandbox_id="sb-12345", current_user=current_user)
        assert res == {"status": "running", "uptime": 120}
    finally:
        app_state["sandbox_manager"] = orig


@pytest.mark.asyncio
async def test_get_sandbox_status_error() -> None:
    current_user = MagicMock(spec=UserResponse)
    mock_mgr = MagicMock()
    mock_mgr.get_sandbox_status = AsyncMock(side_effect=RuntimeError("status lookup failed"))
    orig = app_state.get("sandbox_manager")
    app_state["sandbox_manager"] = mock_mgr
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_sandbox_status(sandbox_id="sb-12345", current_user=current_user)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."
    finally:
        app_state["sandbox_manager"] = orig
