# -*- coding: utf-8 -*-
"""
VIBE_BE_005: Unit Tests for WebSocket Authentication

Target: 95% coverage, 100% pass rate
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.auth.websocket_auth import (
    AuthenticatedConnection,
    AuthenticatedUser,
    WebSocketAuthenticator,
    websocket_auth,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def authenticator():
    """Create a WebSocketAuthenticator instance."""
    return WebSocketAuthenticator()


@pytest.fixture
def valid_jwt_payload():
    """Valid JWT payload."""
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "tenant_id": 1,
        "roles": ["user", "admin"],
    }


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}
    ws.cookies = {}
    return ws


# ============================================================================
# AuthenticatedUser Tests
# ============================================================================


class TestAuthenticatedUser:
    """Tests for AuthenticatedUser dataclass."""

    def test_init_required_fields(self):
        """Test initialization with required fields."""
        user = AuthenticatedUser(user_id="user-123", tenant_id=1)
        assert user.user_id == "user-123"
        assert user.email is None
        assert user.tenant_id == 1
        assert user.roles == []

    def test_init_all_fields(self):
        """Test initialization with all fields."""
        user = AuthenticatedUser(
            user_id="user-456",
            email="test@example.com",
            tenant_id=5,
            roles=["admin", "editor"],
        )
        assert user.user_id == "user-456"
        assert user.email == "test@example.com"
        assert user.tenant_id == 5
        assert user.roles == ["admin", "editor"]


# ============================================================================
# AuthenticatedConnection Tests
# ============================================================================


class TestAuthenticatedConnection:
    """Tests for AuthenticatedConnection dataclass."""

    def test_init(self, mock_websocket):
        """Test connection initialization."""
        user = AuthenticatedUser(user_id="user-123", tenant_id=1)
        now = datetime.now(timezone.utc)

        conn = AuthenticatedConnection(
            websocket=mock_websocket, user=user, connected_at=now, last_activity=now
        )

        assert conn.websocket == mock_websocket
        assert conn.user.user_id == "user-123"
        assert conn.messages_sent == 0
        assert conn.messages_received == 0


# ============================================================================
# WebSocketAuthenticator Tests
# ============================================================================


class TestWebSocketAuthenticator:
    """Tests for WebSocketAuthenticator class."""

    def test_init(self, authenticator):
        """Test authenticator initialization."""
        assert authenticator.jwt_handler is not None
        assert authenticator._connections == {}

    @pytest.mark.asyncio
    async def test_authenticate_no_token(self, authenticator, mock_websocket):
        """Test authentication with no token."""
        user = await authenticator.authenticate(mock_websocket)

        assert user is None
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_query_param_token_is_rejected(
        self, authenticator, mock_websocket, valid_jwt_payload
    ):
        """SEC-AGT-004: a token supplied only via ?token= query param must be rejected."""
        # Token present only in the query string (no cookie/subprotocol/header)
        mock_websocket.scope["query_string"] = b"token=valid_token"

        with patch.object(
            authenticator.jwt_handler, "verify_token", return_value=valid_jwt_payload
        ):
            user = await authenticator.authenticate(mock_websocket)

            assert user is None
            mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_token(self, authenticator, mock_websocket):
        """Test authentication with invalid token (delivered via cookie)."""
        mock_websocket.cookies = {"access_token": "invalid_token"}

        with patch.object(authenticator.jwt_handler, "verify_token", return_value=None):
            user = await authenticator.authenticate(mock_websocket)

            assert user is None
            mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_with_required_roles_success(
        self, authenticator, mock_websocket, valid_jwt_payload
    ):
        """Test authentication with required roles met (token via cookie)."""
        mock_websocket.cookies = {"access_token": "valid_token"}

        with patch.object(
            authenticator.jwt_handler, "verify_token", return_value=valid_jwt_payload
        ):
            user = await authenticator.authenticate(mock_websocket, required_roles=["admin"])

            assert user is not None
            assert "admin" in user.roles

    @pytest.mark.asyncio
    async def test_authenticate_with_required_roles_fail(
        self, authenticator, mock_websocket, valid_jwt_payload
    ):
        """Test authentication with required roles not met (token via cookie)."""
        mock_websocket.cookies = {"access_token": "valid_token"}
        valid_jwt_payload["roles"] = ["user"]  # No admin role

        with patch.object(
            authenticator.jwt_handler, "verify_token", return_value=valid_jwt_payload
        ):
            user = await authenticator.authenticate(mock_websocket, required_roles=["superadmin"])

            assert user is None
            mock_websocket.close.assert_called_once()

    def test_disconnect(self, authenticator):
        """Test disconnecting a user."""
        # Add a mock connection
        authenticator._connections["user-123"] = MagicMock()

        authenticator.disconnect("user-123")

        assert "user-123" not in authenticator._connections

    def test_disconnect_nonexistent(self, authenticator):
        """Test disconnecting non-existent user."""
        # Should not raise
        authenticator.disconnect("nonexistent")

    def test_get_connection(self, authenticator, mock_websocket):
        """Test getting connection by user ID."""
        user = AuthenticatedUser(user_id="user-123", tenant_id=1)
        conn = AuthenticatedConnection(
            websocket=mock_websocket,
            user=user,
            connected_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        authenticator._connections["user-123"] = conn

        result = authenticator.get_connection("user-123")
        assert result == conn

    def test_get_connection_nonexistent(self, authenticator):
        """Test getting non-existent connection."""
        result = authenticator.get_connection("nonexistent")
        assert result is None

    def test_get_tenant_connections(self, authenticator, mock_websocket):
        """Test getting connections by tenant."""
        for i in range(3):
            user = AuthenticatedUser(user_id=f"user-{i}", tenant_id=1 if i < 2 else 2)
            conn = AuthenticatedConnection(
                websocket=mock_websocket,
                user=user,
                connected_at=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
            )
            authenticator._connections[f"user-{i}"] = conn

        tenant_1_conns = authenticator.get_tenant_connections(1)
        assert len(tenant_1_conns) == 2

        tenant_2_conns = authenticator.get_tenant_connections(2)
        assert len(tenant_2_conns) == 1

    def test_active_connections_count(self, authenticator, mock_websocket):
        """Test counting active connections."""
        assert authenticator.active_connections == 0

        for i in range(5):
            user = AuthenticatedUser(user_id=f"user-{i}", tenant_id=1)
            conn = AuthenticatedConnection(
                websocket=mock_websocket,
                user=user,
                connected_at=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
            )
            authenticator._connections[f"user-{i}"] = conn

        assert authenticator.active_connections == 5


# ============================================================================
# Token Extraction Tests
# ============================================================================


class TestTokenExtraction:
    """Tests for token extraction methods."""

    def test_extract_token_from_query_is_ignored(self, authenticator, mock_websocket):
        """SEC-AGT-004: a token in the query string must NOT be extracted (OWASP ASVS V7)."""
        mock_websocket.scope["query_string"] = b"token=my_jwt_token"

        token = authenticator._extract_token(mock_websocket)
        assert token is None

    def test_extract_token_from_subprotocol(self, authenticator, mock_websocket):
        """Test extracting token from subprotocol."""
        mock_websocket.scope["subprotocols"] = ["access_token", "my_jwt_token"]

        token = authenticator._extract_token(mock_websocket)
        assert token == "my_jwt_token"

    def test_extract_token_from_cookie(self, authenticator, mock_websocket):
        """Phase 6: Test extracting token from cookie (canonical path)."""
        mock_websocket.cookies = {"access_token": "my_jwt_token"}

        token = authenticator._extract_token(mock_websocket)
        assert token == "my_jwt_token"

    def test_extract_token_cookie_takes_precedence_over_query(self, authenticator, mock_websocket):
        """Phase 6: Cookie token takes precedence over query param token."""
        mock_websocket.cookies = {"access_token": "cookie_token"}
        mock_websocket.scope["query_string"] = b"token=query_token"

        token = authenticator._extract_token(mock_websocket)
        assert token == "cookie_token"

    def test_extract_token_from_header(self, authenticator, mock_websocket):
        """Test extracting token from Authorization header."""
        mock_websocket.scope["headers"] = [(b"authorization", b"Bearer my_jwt_token")]

        token = authenticator._extract_token(mock_websocket)
        assert token == "my_jwt_token"

    def test_extract_token_no_token(self, authenticator, mock_websocket):
        """Test extracting token when none present."""
        token = authenticator._extract_token(mock_websocket)
        assert token is None


# ============================================================================
# Global Instance Tests
# ============================================================================


class TestGlobalInstance:
    """Tests for global websocket_auth instance."""

    def test_global_instance_exists(self):
        """Test that global instance is available."""
        assert websocket_auth is not None
        assert isinstance(websocket_auth, WebSocketAuthenticator)


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over iets anders dan de accountstatus en hebben geen database.

    De controle zelf (uitgezet = geweigerd, aan = door) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import websocket_auth

    from src.core.auth import account_status

    # Ook de intrekkingscontrole (jti-blacklist en de grens na een nieuw wachtwoord) leest de database.
    with (
        patch.object(websocket_auth, "account_is_active_for_ws", AsyncMock(return_value=True)),
        patch.object(account_status, "token_is_ingetrokken", AsyncMock(return_value=False)),
    ):
        yield
