import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.websockets import WebSocketState
from src.core.api.workflow_builder_ws import router, workflow_builder_stream


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/builder/stream" in paths


@pytest.mark.asyncio
async def test_workflow_builder_stream_unauthenticated() -> None:
    ws = AsyncMock()
    with patch("src.core.api.workflow_builder_ws._auth.authenticate", new_callable=AsyncMock, return_value=None):
        await workflow_builder_stream(websocket=ws)
        # Should return immediately without connecting to manager
        ws.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_builder_stream_keywords() -> None:
    ws = AsyncMock()
    ws.client_state = WebSocketState.CONNECTING
    ws.receive_json.side_effect = [
        {"type": "keywords", "text": "create customer support flow"},
        Exception("disconnect"),
    ]

    mock_user = MagicMock()
    with patch("src.core.api.workflow_builder_ws._auth.authenticate", new_callable=AsyncMock, return_value=mock_user):
        with patch("src.core.api.workflow_builder_ws.extract_keywords", return_value=["customer", "support"]):
            await workflow_builder_stream(websocket=ws)
            # Verify ws was accepted and keywords were sent back
            ws.accept.assert_awaited()
            ws.send_json.assert_awaited()
            sent_msg = ws.send_json.await_args[0][0]
            assert sent_msg["type"] == "keyword"
            assert sent_msg["data"]["keywords"] == ["customer", "support"]
