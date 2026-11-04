"""HITL-websocket met de ECHTE `get_ws_user` en `connection_manager` (meetlat-scenario 5).

De oudere tests overschrijven de auth-dependency, waardoor de dubbele `accept()` (eerst in
`WebSocketAuthenticator.authenticate`, daarna in `ConnectionManager.connect`) onzichtbaar bleef.
Hier draait de echte keten; alleen de JWT-verificatie wordt vervangen door een vaste payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from starlette.testclient import TestClient

from src.core.api.v1.websocket_hitl import limiter
from src.core.api.v1.websocket_hitl import router as hitl_router
from src.core.websocket.manager import connection_manager


def _payload(tenant_id: int) -> dict[str, object]:
    return {"sub": "user-42", "tenant_id": tenant_id, "roles": ["user"], "email": "a@b.nl"}


@pytest.fixture
def ws_client() -> Iterator[TestClient]:
    limiter.buckets.clear()
    app = FastAPI()
    app.include_router(hitl_router)
    with patch(
        "src.core.auth.websocket_auth.websocket_auth.jwt_handler.verify_token",
        side_effect=lambda token: _payload(int(token.split("-")[1])),
    ):
        with TestClient(app) as client:
            yield client


def _connect(client: TestClient, path_tenant: int, jwt_tenant: int):  # type: ignore[no-untyped-def]
    return client.websocket_connect(
        f"/ws/hitl/{path_tenant}",
        headers={"Authorization": f"Bearer tenant-{jwt_tenant}"},
    )


def test_connection_stays_open_and_receives_connected_message(ws_client: TestClient) -> None:
    with _connect(ws_client, 1, 1) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"
        assert hello["channel"] == "hitl:1"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


def test_new_ticket_arrives_live_at_connected_client(ws_client: TestClient) -> None:
    with _connect(ws_client, 1, 1) as ws:
        ws.receive_json()
        message = {"type": "hitl:new", "ticket_ref": "T-1", "data": {}, "timestamp": "x"}
        portal = ws_client.portal
        assert portal is not None
        count = portal.call(connection_manager.broadcast_to_channel, "hitl:1", message)
        assert count >= 1
        received = ws.receive_json()
        assert received["type"] == "hitl:new"
        assert received["ticket_ref"] == "T-1"


def test_other_tenant_in_path_is_refused(ws_client: TestClient) -> None:
    """Tenant komt uit de JWT (1); pad vraagt tenant 2 -> gesloten met 1008."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with _connect(ws_client, 2, 1) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_other_tenant_receives_no_broadcast(ws_client: TestClient) -> None:
    with _connect(ws_client, 2, 2) as ws:
        ws.receive_json()
        portal = ws_client.portal
        assert portal is not None
        count = portal.call(
            connection_manager.broadcast_to_channel, "hitl:1", {"type": "hitl:new"}
        )
        assert count == 0
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"


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
