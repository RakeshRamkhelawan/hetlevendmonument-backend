"""Integration tests for the scheduling WebSocket via the central app.

NOTE (OP-11 cluster E): deze tests authenticeerden via ``/ws/scheduling?token=...``.
Dat pad is bewust verwijderd (SEC-AGT-004, OWASP ASVS V7: geen sessie-identifiers in
query strings) en de tests stonden daardoor rood met WebSocketDisconnect. Ze gebruiken
nu de canonieke route: de HTTP-only ``access_token``-cookie. Zie
src/core/auth/websocket_auth.py::_extract_token voor de drie toegestane methodes
(cookie, Sec-WebSocket-Protocol subprotocol, Authorization header).
"""

from unittest.mock import AsyncMock

import anyio
from fastapi.testclient import TestClient

from src.core.scheduling.api.websocket import broadcast_to_tenant, get_manager, notify_participants


def test_scheduling_websocket_via_central_app(
    integration_app,
    admin_auth_headers,
):
    """The central app should expose an authenticated scheduling WebSocket."""
    token = admin_auth_headers["Authorization"].split(" ", 1)[1]

    with TestClient(integration_app) as client:
        client.cookies.set("access_token", token)
        with client.websocket_connect("/ws/scheduling") as websocket:
            connected = websocket.receive_json()

            assert connected["type"] == "connected"
            assert connected["user_id"] == "1"
            assert connected["tenant_id"] == 1
            assert connected["heartbeat_interval_s"] == 30

            websocket.send_json({"type": "subscribe", "channel": "calendar_events"})
            subscribed = websocket.receive_json()
            assert subscribed == {
                "type": "subscribed",
                "channel": "calendar_events",
            }

            websocket.send_json({"type": "unsubscribe", "channel": "calendar_events"})
            unsubscribed = websocket.receive_json()
            assert unsubscribed == {
                "type": "unsubscribed",
                "channel": "calendar_events",
            }


def test_scheduling_websocket_error_paths_via_central_app(
    integration_app,
    admin_auth_headers,
):
    """The central app should surface websocket protocol errors clearly."""
    token = admin_auth_headers["Authorization"].split(" ", 1)[1]

    with TestClient(integration_app) as client:
        client.cookies.set("access_token", token)
        with client.websocket_connect("/ws/scheduling") as websocket:
            connected = websocket.receive_json()
            assert connected["type"] == "connected"

            websocket.send_text("not-json")
            invalid_json = websocket.receive_json()
            assert invalid_json == {
                "type": "error",
                "message": "Invalid JSON",
            }

            websocket.send_json({"type": "does-not-exist"})
            unknown_type = websocket.receive_json()
            assert unknown_type == {
                "type": "error",
                "message": "Unknown type: does-not-exist",
            }


def test_scheduling_websocket_broadcasts_to_all_connections_in_tenant(
    integration_app,
    admin_auth_headers,
    normal_user_with_token,
):
    """Tenant-wide broadcasts should reach all connected scheduling clients."""
    admin_token = admin_auth_headers["Authorization"].split(" ", 1)[1]
    normal_token = normal_user_with_token["token"]

    with TestClient(integration_app) as client:
        # Cookie wordt per connect gelezen, dus omwisselen tussen de twee verbindingen.
        client.cookies.set("access_token", admin_token)
        with client.websocket_connect("/ws/scheduling") as ws_admin:
            client.cookies.set("access_token", normal_token)
            with client.websocket_connect("/ws/scheduling") as ws_user:
                assert ws_admin.receive_json()["type"] == "connected"
                assert ws_user.receive_json()["type"] == "connected"

                manager = get_manager()
                connections = manager.tenant_connections(1)
                assert len(connections) == 2

                mocked_senders = []
                for connection in connections:
                    mocked_sender = AsyncMock(return_value=None)
                    connection.ws.send_text = mocked_sender
                    mocked_senders.append(mocked_sender)

                payload = {
                    "event_id": "evt-123",
                    "status": "updated",
                }
                sent = anyio.run(
                    broadcast_to_tenant,
                    1,
                    "calendar_event_updated",
                    payload,
                )

                assert sent == 2
                for mocked_sender in mocked_senders:
                    mocked_sender.assert_awaited_once_with(
                        '{"type": "calendar_event_updated", "data": {"event_id": "evt-123", "status": "updated"}}'
                    )


def test_scheduling_websocket_notifies_only_target_participants(
    integration_app,
    admin_auth_headers,
    normal_user_with_token,
):
    """Participant notifications should only fan out to the targeted user IDs."""
    admin_token = admin_auth_headers["Authorization"].split(" ", 1)[1]
    normal_token = normal_user_with_token["token"]

    with TestClient(integration_app) as client:
        # Cookie wordt per connect gelezen, dus omwisselen tussen de twee verbindingen.
        client.cookies.set("access_token", admin_token)
        with client.websocket_connect("/ws/scheduling") as ws_admin:
            client.cookies.set("access_token", normal_token)
            with client.websocket_connect("/ws/scheduling") as ws_user:
                assert ws_admin.receive_json()["type"] == "connected"
                assert ws_user.receive_json()["type"] == "connected"

                manager = get_manager()
                connections = {conn.user.user_id: conn for conn in manager.tenant_connections(1)}
                assert set(connections) == {"1", "2"}

                admin_sender = AsyncMock(return_value=None)
                user_sender = AsyncMock(return_value=None)
                connections["1"].ws.send_text = admin_sender
                connections["2"].ws.send_text = user_sender

                payload = {
                    "event_id": "evt-456",
                    "status": "participant-notified",
                }
                sent = anyio.run(
                    notify_participants,
                    1,
                    ["2"],
                    "calendar_event_targeted",
                    payload,
                )

                assert sent == 1
                admin_sender.assert_not_awaited()
                user_sender.assert_awaited_once_with(
                    '{"type": "calendar_event_targeted", "data": {"event_id": "evt-456", "status": "participant-notified"}}'
                )
