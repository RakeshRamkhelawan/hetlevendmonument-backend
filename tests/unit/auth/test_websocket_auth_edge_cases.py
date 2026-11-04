"""
Unit tests for WebSocketAuthenticator edge cases (websocket_auth.py).

Covers: token extraction from multiple sources, _payload_to_user edge cases,
connection tracking, tenant filtering, role enforcement.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.auth.websocket_auth import (
    AuthenticatedConnection,
    AuthenticatedUser,
    WebSocketAuthenticator,
)


@pytest.fixture
def authenticator():
    return WebSocketAuthenticator()


def _make_websocket(
    query_string: str = "",
    subprotocols: list = None,
    headers: list = None,
):
    """Helper to create a mock WebSocket with specific scope."""
    from unittest.mock import MagicMock

    ws = AsyncMock()
    ws.scope = {
        "type": "websocket",
        "query_string": query_string.encode(),
        "subprotocols": subprotocols or [],
        "headers": headers or [],
    }
    ws.cookies = MagicMock()
    ws.cookies.get.return_value = None
    return ws


class TestExtractToken:
    """Tests for _extract_token() — 3 extraction methods."""

    def test_query_param_is_ignored(self, authenticator):
        """SEC-AGT-004: a token in the query string must NOT be extracted (OWASP ASVS V7)."""
        ws = _make_websocket(query_string="token=abc123&foo=bar")
        token = authenticator._extract_token(ws)
        assert token is None

    def test_extracts_from_subprotocol(self, authenticator):
        ws = _make_websocket(subprotocols=["access_token", "my_jwt_token"])
        token = authenticator._extract_token(ws)
        assert token == "my_jwt_token"

    def test_extracts_from_authorization_header(self, authenticator):
        ws = _make_websocket(headers=[(b"authorization", b"Bearer jwt_here")])
        token = authenticator._extract_token(ws)
        assert token == "jwt_here"

    def test_returns_none_when_no_token(self, authenticator):
        ws = _make_websocket()
        token = authenticator._extract_token(ws)
        assert token is None

    def test_subprotocol_takes_priority_over_header(self, authenticator):
        """SEC-AGT-004: query param removed; subprotocol is checked before the header."""
        ws = _make_websocket(
            query_string="token=from_query",
            subprotocols=["access_token", "from_protocol"],
            headers=[(b"authorization", b"Bearer from_header")],
        )
        token = authenticator._extract_token(ws)
        assert token == "from_protocol"

    def test_subprotocol_without_following_token(self, authenticator):
        """access_token as last element should not extract."""
        ws = _make_websocket(subprotocols=["access_token"])
        token = authenticator._extract_token(ws)
        assert token is None

    def test_authorization_header_without_bearer(self, authenticator):
        ws = _make_websocket(headers=[(b"authorization", b"Basic abc123")])
        token = authenticator._extract_token(ws)
        assert token is None


class TestPayloadToUser:
    """Tests for _payload_to_user()."""

    def test_valid_payload_with_sub(self, authenticator):
        payload = {"sub": "user_42", "email": "test@test.com", "tenant_id": 5, "roles": ["admin"]}
        user = authenticator._payload_to_user(payload)
        assert user is not None
        assert user.user_id == "user_42"
        assert user.email == "test@test.com"
        assert user.tenant_id == 5
        assert user.roles == ["admin"]

    def test_valid_payload_with_user_id(self, authenticator):
        payload = {"user_id": 99, "tenant_id": 3}
        user = authenticator._payload_to_user(payload)
        assert user is not None
        assert user.user_id == "99"
        assert user.tenant_id == 3

    def test_returns_none_when_no_user_identifier(self, authenticator):
        payload = {"email": "test@test.com", "tenant_id": 1}
        user = authenticator._payload_to_user(payload)
        assert user is None

    def test_rejects_payload_missing_tenant_id(self, authenticator):
        """JWT without tenant_id must be rejected -- not defaulted to tenant 1."""
        payload = {"sub": "user_1", "email": "user@example.com"}
        user = authenticator._payload_to_user(payload)
        assert user is None

    def test_defaults_roles_to_empty_list(self, authenticator):
        payload = {"sub": "user_1", "tenant_id": 5}
        user = authenticator._payload_to_user(payload)
        assert user is not None
        assert user.roles == []

    def test_handles_invalid_tenant_id_type(self, authenticator):
        payload = {"sub": "user_1", "tenant_id": "not_a_number"}
        user = authenticator._payload_to_user(payload)
        # Should return None because int("not_a_number") raises ValueError
        assert user is None

    def test_handles_empty_payload(self, authenticator):
        user = authenticator._payload_to_user({})
        assert user is None


class TestAuthenticate:
    """Tests for authenticate() — full flow."""

    @pytest.mark.asyncio
    async def test_no_token_closes_connection(self, authenticator):
        ws = _make_websocket()
        with patch.object(authenticator, "_extract_token", return_value=None):
            user = await authenticator.authenticate(ws)
        assert user is None
        ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_token_closes_connection(self, authenticator):
        ws = _make_websocket(subprotocols=["access_token", "bad"])
        with patch.object(authenticator.jwt_handler, "verify_token", return_value=None):
            user = await authenticator.authenticate(ws)
        assert user is None

    @pytest.mark.asyncio
    async def test_valid_token_accepts_and_returns_user(self, authenticator):
        ws = _make_websocket(subprotocols=["access_token", "good"])
        payload = {"sub": "user_1", "tenant_id": 5, "roles": ["viewer"]}

        with patch.object(authenticator.jwt_handler, "verify_token", return_value=payload):
            user = await authenticator.authenticate(ws)

        assert user is not None
        assert user.user_id == "user_1"
        assert user.tenant_id == 5
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_required_role_closes_connection(self, authenticator):
        ws = _make_websocket(subprotocols=["access_token", "good"])
        payload = {"sub": "user_1", "roles": ["viewer"]}

        with patch.object(authenticator.jwt_handler, "verify_token", return_value=payload):
            user = await authenticator.authenticate(ws, required_roles=["admin"])

        assert user is None

    @pytest.mark.asyncio
    async def test_matching_required_role_succeeds(self, authenticator):
        ws = _make_websocket(subprotocols=["access_token", "good"])
        payload = {"sub": "user_1", "tenant_id": 5, "roles": ["admin", "viewer"]}

        with patch.object(authenticator.jwt_handler, "verify_token", return_value=payload):
            user = await authenticator.authenticate(ws, required_roles=["admin"])

        assert user is not None
        assert "admin" in user.roles


class TestConnectionTracking:
    """Tests for disconnect, get_connection, get_tenant_connections, active_connections."""

    def test_disconnect_removes_connection(self, authenticator):
        authenticator._connections["user_1"] = MagicMock()
        authenticator.disconnect("user_1")
        assert "user_1" not in authenticator._connections

    def test_disconnect_nonexistent_is_noop(self, authenticator):
        authenticator.disconnect("nonexistent")  # Should not raise

    def test_get_connection_returns_existing(self, authenticator):
        mock_conn = MagicMock()
        authenticator._connections["user_1"] = mock_conn
        assert authenticator.get_connection("user_1") is mock_conn

    def test_get_connection_returns_none_for_missing(self, authenticator):
        assert authenticator.get_connection("missing") is None

    def test_get_tenant_connections_filters_by_tenant(self, authenticator):
        user_a = AuthenticatedUser(user_id="a", tenant_id=1)
        user_b = AuthenticatedUser(user_id="b", tenant_id=2)
        user_c = AuthenticatedUser(user_id="c", tenant_id=1)

        now = datetime.now(timezone.utc)
        authenticator._connections = {
            "a": AuthenticatedConnection(
                websocket=MagicMock(), user=user_a, connected_at=now, last_activity=now
            ),
            "b": AuthenticatedConnection(
                websocket=MagicMock(), user=user_b, connected_at=now, last_activity=now
            ),
            "c": AuthenticatedConnection(
                websocket=MagicMock(), user=user_c, connected_at=now, last_activity=now
            ),
        }

        tenant_1_conns = authenticator.get_tenant_connections(1)
        assert len(tenant_1_conns) == 2

        tenant_2_conns = authenticator.get_tenant_connections(2)
        assert len(tenant_2_conns) == 1

    def test_active_connections_count(self, authenticator):
        assert authenticator.active_connections == 0
        authenticator._connections["user_1"] = MagicMock()
        authenticator._connections["user_2"] = MagicMock()
        assert authenticator.active_connections == 2


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
