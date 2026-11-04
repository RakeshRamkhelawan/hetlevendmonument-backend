import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from src.core.api.main import app
from src.core.config.unified_config import config

# Mock Redis to avoid needing a real instance for this test if possible,
# or use the test container. For integration, we usually use the real setup.


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="[RED PHASE] Graph update WebSocket feature not yet implemented",
    strict=False,
)
async def test_copilot_websocket_graph_manipulation(async_client, normal_user_token):
    """
    [RED PHASE]
    Test that sending a command to the WebSocket triggers a 'graph_update' event.
    Current implementation only echoes text. This test expects advanced behavior.
    """
    # Simulate a user asking to modify the graph
    user_prompt = "Create a new agent node for Market Intelligence"

    # Note: TestClient used as context manager for websockets

    with TestClient(app) as client:
        # SEC-AGT-004: authenticatie via de access_token-cookie; het ?token=-pad in de
        # URL is verwijderd (2026-07-31).
        client.cookies.set("access_token", normal_user_token)
        # Connect to WebSocket
        # Adjust URL to match your router structure (api/v1/copilot/ws/{client_id})
        try:
            with client.websocket_connect("/api/v1/copilot/ws/test-client-1") as websocket:
                # 1. Send Message
                websocket.send_text(user_prompt)

                # 2. Receive Acknowledgement (Text)
                # We expect the LLM to reply "Sure, adding node..."
                response_text = websocket.receive_text()
                assert len(response_text) > 0

                # 3. Receive Graph Update Event (JSON)
                # THIS IS THE MISSING FEATURE we are testing for.
                # It should receive a JSON message with type="graph_update"
                response_json = websocket.receive_json()
                assert response_json["type"] == "graph_update"
                assert "nodes" in response_json["data"]

                print("Received Graph Update Event")

        except WebSocketDisconnect:
            pytest.fail("WebSocket disconnected unexpectedly")
        except Exception as e:
            pytest.fail(f"WebSocket interaction failed: {e}")
