"""De websocketlaag kiest nooit een standaardtenant (acceptant scenario 5, 2026-10-05).

`ConnectionManager.connect` deed `int(payload.get("tenant_id", 1))`: een geldig token zonder
`tenant_id` kwam binnen als tenant 1 en kreeg dus elke `broadcast_to_tenant(1)` te zien. En een
verbinding zonder token (`require_auth=False`) stond standaard ook op tenant 1. Beide moeten
anders: een token zonder tenant wordt geweigerd met 1008, een verbinding zonder token hoort bij
geen enkele tenant.

Hier over de echte `/ws/{channel}`-route en de echte `connection_manager`; alleen de
JWT-verificatie is vervangen door een vaste payload.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from starlette.testclient import TestClient

from src.core.api.v1.websocket.router import router as ws_router
from src.core.websocket.manager import ChannelConnection, connection_manager

_PAYLOADS: dict[str, dict[str, object]] = {
    "zonder-tenant": {"sub": "user-7", "roles": ["admin"]},
    "tenant-leeg": {"sub": "user-7", "tenant_id": None},
    "tenant-tekst": {"sub": "user-7", "tenant_id": "abc"},
    "tenant-waar": {"sub": "user-7", "tenant_id": True},
    "tenant-superscript": {"sub": "user-7", "tenant_id": chr(0xB2)},
    "tenant-nul": {"sub": "user-7", "tenant_id": 0},
    "tenant-2": {"sub": "user-7", "tenant_id": 2},
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(ws_router)
    with patch(
        "src.core.auth.jwt_handler.jwt_handler.verify_token",
        side_effect=lambda token: _PAYLOADS.get(token),
    ):
        with TestClient(app) as c:
            yield c


def _verbind(client: TestClient, token: str):  # type: ignore[no-untyped-def]
    return client.websocket_connect("/ws/algemeen", headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize(
    "token",
    ["zonder-tenant", "tenant-leeg", "tenant-tekst", "tenant-waar", "tenant-superscript", "tenant-nul"],
)
def test_een_token_zonder_bruikbare_tenant_wordt_geweigerd(client: TestClient, token: str) -> None:
    with pytest.raises(WebSocketDisconnect) as fout:
        with _verbind(client, token) as ws:
            ws.receive_json()
    assert fout.value.code == 1008


def test_een_token_met_tenant_komt_binnen_bij_die_tenant(client: TestClient) -> None:
    with _verbind(client, "tenant-2") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"type": "status"})
        assert ws.receive_json()["tenant_id"] == 2


def test_een_verbinding_zonder_tenant_hoort_bij_geen_tenant() -> None:
    assert ChannelConnection(websocket=None, channel="x").tenant_id is None  # type: ignore[arg-type]


def test_een_geweigerd_token_staat_niet_in_het_kanaal(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with _verbind(client, "zonder-tenant") as ws:
            ws.receive_json()
    assert connection_manager.get_channel_count("algemeen") == 0


@pytest.mark.parametrize("ruw", [True, False, 0, -3, 1.9, chr(0xB2), "abc", None])
def test_de_gedeelde_lezer_weigert_wat_geen_tenant_is(ruw: object) -> None:
    from src.core.auth.websocket_auth import tenant_from_claim

    assert tenant_from_claim(ruw) is None


def test_de_websocketauthenticatie_maakt_van_true_geen_tenant_1() -> None:
    from src.core.auth.websocket_auth import WebSocketAuthenticator

    gebruiker = WebSocketAuthenticator()._payload_to_user({"sub": "u", "tenant_id": True})  # type: ignore[arg-type]
    assert gebruiker is None


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over de tenantclaim en hebben geen database.

    De accountcontrole zelf wordt gemeten in
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
