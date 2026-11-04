from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.auth.websocket_auth import WebSocketAuthenticator


def make_ws_mock(token: str = "valid.jwt.token") -> MagicMock:
    ws = MagicMock()
    ws.cookies = {}
    ws.scope = {
        "type": "websocket",
        # SEC-AGT-004: query-param auth removed; deliver the token via subprotocol.
        "query_string": b"",
        "subprotocols": ["access_token", token],
        "headers": [],
    }
    ws.accept = AsyncMock()
    return ws


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_sets_tenant_context():
    """After WS authentication, the tenant ContextVar must be set."""
    from src.core.middleware.tenant_context import clear_tenant_context, get_tenant_id

    authenticator = WebSocketAuthenticator()
    ws = make_ws_mock()

    valid_payload = {"sub": "user123", "tenant_id": 7, "email": "u@t.com", "roles": []}
    with patch.object(authenticator.jwt_handler, "verify_token", return_value=valid_payload):
        user = await authenticator.authenticate(ws)

    assert user is not None
    assert get_tenant_id() == 7  # ContextVar must be set

    clear_tenant_context()  # test cleanup


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authenticate_rejects_token_without_tenant_id():
    """A JWT missing tenant_id must be rejected -- no silent fallback to tenant 1."""
    authenticator = WebSocketAuthenticator()
    ws = make_ws_mock()
    ws.close = AsyncMock()

    payload_no_tenant = {"sub": "user123", "email": "u@t.com", "roles": []}
    with patch.object(authenticator.jwt_handler, "verify_token", return_value=payload_no_tenant):
        user = await authenticator.authenticate(ws)

    assert user is None  # rejected, not silently assigned to tenant 1


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
