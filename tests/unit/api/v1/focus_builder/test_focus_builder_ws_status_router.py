"""Unit tests for FocusBuilder WebSocket status router (src/core/api/v1/focus_builder/ws_status_router.py).

Covers:
- WS /flows/{flow_id}/status
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.routing import WebSocketRoute

from src.core.api.v1.focus_builder.shared import WSUser
from src.core.api.v1.focus_builder.ws_status_router import (
    flow_status_websocket,
    ws_status_router,
)


def test_routes_registered() -> None:
    routes = [r for r in ws_status_router.routes if isinstance(r, WebSocketRoute)]
    paths = {r.path for r in routes}
    assert "/flows/{flow_id}/status" in paths


@pytest.mark.asyncio
async def test_flow_status_websocket_missing_cookie_rejected() -> None:
    ws = AsyncMock()
    ws.cookies = {}

    await flow_status_websocket(
        websocket=ws,
        flow_id=1,
        db=AsyncMock(),
        manager=MagicMock(),
        auth_handler=AsyncMock(),
        flow_verifier=AsyncMock(),
    )
    ws.close.assert_awaited_once_with(code=4001, reason="Missing token")


@pytest.mark.asyncio
async def test_flow_status_websocket_flow_not_found_rejected() -> None:
    ws = AsyncMock()
    ws.cookies = {"access_token": "valid.token"}

    user = WSUser(user_id=1, tenant_id=42)
    auth_handler = AsyncMock()
    auth_handler.validate_token.return_value = user

    flow_verifier = AsyncMock()
    flow_verifier.flow_exists.return_value = False

    await flow_status_websocket(
        websocket=ws,
        flow_id=99,
        db=AsyncMock(),
        manager=MagicMock(),
        auth_handler=auth_handler,
        flow_verifier=flow_verifier,
    )
    ws.close.assert_awaited_once_with(code=4004, reason="Flow not found")
