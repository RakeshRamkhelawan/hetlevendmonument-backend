"""Unit tests for deprecated security auth router (src.core.api.v1.security.auth_router).

Follows Pattern A from API-LAAG-MASTERPROMPT.md: direct invocation of endpoint handlers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.security.auth_router import (
    LoginRequest,
    TokenResponse,
    auth_router,
    login,
)
from src.core.api.v1.security.dependencies import SecurityLevel, ThreatLevel


def test_security_auth_router_registration() -> None:
    """Verify route registration, method, and deprecated status."""
    from fastapi.routing import APIRoute

    api_routes = [r for r in auth_router.routes if isinstance(r, APIRoute)]
    route = next((r for r in api_routes if r.path == "/auth/login"), None)
    assert route is not None
    assert "POST" in route.methods
    assert getattr(route, "deprecated", False) is True



@pytest.mark.unit
async def test_login_invalid_credentials_returns_401() -> None:
    """Verify unhappy path: unknown user or wrong password raises 401 and logs security event."""
    mock_request = LoginRequest(username="unknown@example.com", password="wrongpassword")
    mock_http_request = MagicMock()
    mock_http_request.client.host = "10.0.0.5"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    mock_security_mgr = MagicMock()

    with patch("src.core.api.v1.security.auth_router.get_security_manager", return_value=mock_security_mgr):
        with pytest.raises(HTTPException) as exc_info:
            await login(request=mock_request, http_request=mock_http_request, db=mock_db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid credentials"

    mock_security_mgr._log_security_event.assert_called_once_with(
        "login_failed",
        ThreatLevel.MEDIUM,
        "10.0.0.5",
        "unknown@example.com",
        "/auth/login",
        "Failed login - invalid credentials for user: unknown@example.com",
    )


@pytest.mark.unit
async def test_login_success_regular_user() -> None:
    """Verify happy path for regular user: returns token with AUTHORIZED security level."""
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("validpassword")

    mock_user = MagicMock()
    mock_user.email = "regular@example.com"
    mock_user.hashed_password = hashed
    role = MagicMock()
    role.name = "member"
    mock_user.roles = [role]

    mock_request = LoginRequest(username="regular@example.com", password="validpassword")
    mock_http_request = MagicMock()
    mock_http_request.client.host = "127.0.0.1"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    mock_security_mgr = MagicMock()
    mock_security_mgr.generate_token.return_value = "jwt-token-regular"

    with patch("src.core.api.v1.security.auth_router.get_security_manager", return_value=mock_security_mgr):
        response = await login(request=mock_request, http_request=mock_http_request, db=mock_db)

    assert isinstance(response, TokenResponse)
    assert response.access_token == "jwt-token-regular"
    assert response.security_level == SecurityLevel.AUTHORIZED.value
    assert response.expires_in == 86400

    mock_security_mgr.generate_token.assert_called_once_with(
        "user_regular@example.com", SecurityLevel.AUTHORIZED
    )


@pytest.mark.unit
async def test_login_success_admin_user() -> None:
    """Verify happy path for admin user: returns token with ADMIN security level."""
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash("adminsecret")

    mock_user = MagicMock()
    mock_user.email = "admin@example.com"
    mock_user.hashed_password = hashed
    admin_role = MagicMock()
    admin_role.name = "admin"
    mock_user.roles = [admin_role]

    mock_request = LoginRequest(username="admin@example.com", password="adminsecret")
    mock_http_request = MagicMock()
    mock_http_request.client.host = "127.0.0.1"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    mock_security_mgr = MagicMock()
    mock_security_mgr.generate_token.return_value = "jwt-token-admin"

    with patch("src.core.api.v1.security.auth_router.get_security_manager", return_value=mock_security_mgr):
        response = await login(request=mock_request, http_request=mock_http_request, db=mock_db)

    assert isinstance(response, TokenResponse)
    assert response.access_token == "jwt-token-admin"
    assert response.security_level == SecurityLevel.ADMIN.value

    mock_security_mgr.generate_token.assert_called_once_with(
        "user_admin@example.com", SecurityLevel.ADMIN
    )


@pytest.mark.unit
async def test_login_unexpected_error_returns_500() -> None:
    """Verify error path: unexpected database exception raises 500 Authentication error."""
    mock_request = LoginRequest(username="user@example.com", password="password")
    mock_http_request = MagicMock()

    mock_db = AsyncMock()
    mock_db.execute.side_effect = RuntimeError("Database connection exploded")

    with pytest.raises(HTTPException) as exc_info:
        await login(request=mock_request, http_request=mock_http_request, db=mock_db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Authentication error"
