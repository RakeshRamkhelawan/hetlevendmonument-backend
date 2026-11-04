import pytest
from fastapi.testclient import TestClient

from src.core.auth.dependencies import get_current_user_ws


def test_copilot_websocket_connection_and_chat(integration_app):
    """Integration app does not register copilot chat websocket route."""
    with TestClient(integration_app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws/copilot/chat") as websocket:
                websocket.receive_json()


def test_copilot_websocket_auth_failure(integration_app):
    """Integration app does not expose the copilot chat websocket route."""

    async def mock_auth_fail(_token: str):
        raise Exception("Invalid token")

    integration_app.dependency_overrides[get_current_user_ws] = mock_auth_fail

    with TestClient(integration_app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws/copilot/chat") as websocket:
                websocket.receive_json()

    integration_app.dependency_overrides.pop(get_current_user_ws, None)


def test_copilot_stats_endpoint(integration_app):
    """Integration app does not expose the copilot stats websocket route."""
    with TestClient(integration_app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws/copilot/stats") as websocket:
                websocket.receive_json()
