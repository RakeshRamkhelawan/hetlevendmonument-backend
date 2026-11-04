from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.focus_builder.router import router
from services.focusbuilder.ws_manager import manager
from src.core.api.v1.focus_builder.ws_dependencies import (
    WSUser,
    WebSocketAuthHandler,
    WebSocketManager,
    FlowVerifier,
    get_ws_auth,
    get_ws_manager,
    get_flow_verifier,
)
from src.core.database.database import get_async_session


@pytest.fixture
def ws_client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def _override_db():
        yield AsyncMock()

    # Mock auth handler to accept any token
    mock_auth = MagicMock(spec=WebSocketAuthHandler)

    async def _mock_validate_token(token: str) -> WSUser:
        return WSUser(id=1, tenant_id=1)

    mock_auth.validate_token = _mock_validate_token

    # Mock flow verifier
    mock_flow_verifier = MagicMock(spec=FlowVerifier)

    async def _mock_flow_exists(flow_id: int, db, tenant_id: int) -> bool:
        return True

    mock_flow_verifier.flow_exists = _mock_flow_exists

    # Use the same manager instance that the tests will broadcast to
    mock_manager = manager

    app.dependency_overrides[get_async_session] = _override_db
    app.dependency_overrides[get_ws_auth] = lambda: mock_auth
    app.dependency_overrides[get_flow_verifier] = lambda: mock_flow_verifier
    app.dependency_overrides[get_ws_manager] = lambda: mock_manager

    with TestClient(app) as client:
        # SEC-AGT-004: het ?token=-pad is verwijderd (2026-07-31); de endpoint leest
        # uitsluitend de access_token-cookie. De mock-auth hierboven accepteert elke
        # waarde, dus een dummy-cookie volstaat voor deze broadcast-tests.
        client.cookies.set("access_token", "test")
        yield client


@pytest.fixture(autouse=True)
def cleanup_manager_state():
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


@pytest.mark.asyncio
async def test_sprint5_websocket_broadcast_reaches_connected_client(
    ws_client: TestClient,
):
    with ws_client.websocket_connect(
        "/api/v1/focus-builder/flows/101/status"
    ) as websocket:
        await manager.broadcast_status(
            flow_id=101,
            status={"type": "status_update", "status": "RUNNING", "flow_id": 101},
        )

        message = websocket.receive_json()
        assert message["type"] == "status_update"
        assert message["status"] == "RUNNING"
        assert message["flow_id"] == 101


@pytest.mark.asyncio
async def test_sprint5_websocket_broadcast_isolated_per_flow(ws_client: TestClient):
    with ws_client.websocket_connect(
        "/api/v1/focus-builder/flows/201/status"
    ) as ws_flow_201:
        with ws_client.websocket_connect(
            "/api/v1/focus-builder/flows/202/status"
        ) as ws_flow_202:
            await manager.broadcast_status(
                flow_id=201,
                status={
                    "type": "status_update",
                    "status": "RUNNING",
                    "flow_id": 201,
                },
            )
            await manager.broadcast_status(
                flow_id=202,
                status={
                    "type": "status_update",
                    "status": "SUCCEEDED",
                    "flow_id": 202,
                },
            )

            msg_201 = ws_flow_201.receive_json()
            msg_202 = ws_flow_202.receive_json()

            assert msg_201["flow_id"] == 201
            assert msg_201["status"] == "RUNNING"

            assert msg_202["flow_id"] == 202
            assert msg_202["status"] == "SUCCEEDED"
