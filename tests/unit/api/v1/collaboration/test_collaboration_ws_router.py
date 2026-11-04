import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.api.v1.collaboration.router import router, collaborate_ws
from src.core.auth.api_deps import AuthenticatedUser


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/ws/collaborate/{workspace_id}" in paths


@pytest.mark.asyncio
async def test_collaborate_ws_join_and_leave() -> None:
    ws = AsyncMock()
    # Send a join message then raise exception/disconnect
    ws.receive_json.side_effect = [
        {
            "type": "join",
            "data": {
                "user_id": "user-123",
                "display_name": "Bob",
                "color": "#FF0000",
            },
        },
        Exception("Client disconnect"),
    ]

    mock_collab = AsyncMock()
    mock_presence = MagicMock()
    mock_presence.user_id = "user-123"
    mock_presence.display_name = "Bob"
    mock_presence.color = "#FF0000"
    mock_collab.join_workspace.return_value = {"user-123": mock_presence}

    user = MagicMock(spec=AuthenticatedUser)
    user.id = 123

    with patch("src.core.api.v1.collaboration.router.get_collaboration_manager", return_value=mock_collab):
        await collaborate_ws(
            websocket=ws,
            workspace_id="ws-99",
            user=user,
        )

    mock_collab.join_workspace.assert_awaited_once()
    mock_collab.leave_workspace.assert_awaited_once_with("ws-99", "user-123")
    # Verify that users_list was sent to client
    ws.send_json.assert_awaited()
    sent_data = ws.send_json.await_args[0][0]
    assert sent_data["type"] == "users_list"
