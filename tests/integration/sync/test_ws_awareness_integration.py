"""
Integration tests for WebSocket awareness handler with real Redis.

Covers:
- Handler completes without error against real Redis
- Disconnect removes user entry from Redis hash

Detailed Redis interaction (pipeline, TTL, multi-user) is covered by
unit tests in ``tests/unit/sync/test_ws_awareness.py``.

ASCII-only, no emojis (CLAUDE.md Section 10).
"""

from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from src.core.api.v1.sync.ws_handler import awareness_websocket
from src.core.database.redis import get_redis_client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeUser:
    def __init__(self, tenant_id: int, user_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.email = f"{user_id}@example.com"
        self.roles: list[str] = []


class _FakeWebSocket:
    """Minimal WebSocket test double."""

    def __init__(self, messages: Optional[list[Any]] = None) -> None:
        self.accepted = False
        self.closed_code: Optional[int] = None
        self.closed_reason: Optional[str] = None
        self.sent: list[Any] = []
        self._messages = messages or []
        self._index = 0
        self.scope: dict[str, Any] = {"subprotocols": ["json"], "headers": []}

    async def accept(self, subprotocol: Optional[str] = None) -> None:
        self.accepted = True
        self.accepted_subprotocol = subprotocol

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_code = code
        self.closed_reason = reason

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    async def receive_json(self) -> Any:
        if self._index >= len(self._messages):
            raise WebSocketDisconnect()
        msg = self._messages[self._index]
        self._index += 1
        return msg


def _patch_auth(user: Optional[_FakeUser] = None) -> Any:
    """Patch the websocket auth to return a FakeUser."""

    async def _mock_auth(ws: Any, _required_roles: Any = None) -> Optional[_FakeUser]:
        if user is None:
            await ws.close(code=4001, reason="Auth failed")
            return None
        protocols = ws.scope.get("subprotocols", [])
        selected = "json" if "json" in protocols else None
        await ws.accept(subprotocol=selected)
        return user

    return patch(
        "src.core.api.v1.sync.ws_handler._auth.authenticate",
        new=AsyncMock(side_effect=_mock_auth),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _awareness_key(tenant_id: int, workflow_id: str) -> str:
    return f"awareness:{tenant_id}:{workflow_id}"


# ---------------------------------------------------------------------------
# Integration tests with real Redis
# ---------------------------------------------------------------------------


class TestAwarenessWSRedisIntegration:
    """End-to-end tests with real Redis backend."""

    @pytest.fixture(autouse=True)
    async def _cleanup_redis(self):
        """Clean up Redis keys and close connections before and after each test."""
        import src.core.database.redis as redis_mod

        redis_mod._redis_pool = None

        redis = await get_redis_client()
        keys_to_delete = []
        async for key in redis.scan_iter(match="awareness:*:test-ws-*"):
            keys_to_delete.append(key)
        if keys_to_delete:
            await redis.delete(*keys_to_delete)
        await redis.aclose()
        yield
        redis = await get_redis_client()
        keys_to_delete = []
        async for key in redis.scan_iter(match="awareness:*:test-ws-*"):
            keys_to_delete.append(key)
        if keys_to_delete:
            await redis.delete(*set(keys_to_delete))
        await redis.aclose()
        redis_mod._redis_pool = None

    async def test_handler_completes_without_error(self) -> None:
        """Handler runs to completion against real Redis without crashing."""
        tenant_id = 1
        workflow_id = "test-ws-complete"
        user = _FakeUser(tenant_id=tenant_id, user_id="user_complete")
        ws = _FakeWebSocket(
            messages=[{"type": "cursor", "payload": {"x": 42}}],
        )

        with _patch_auth(user):
            await awareness_websocket(ws, workflow_id)  # type: ignore[arg-type]

        # Should have received an ack
        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "ack"

    async def test_disconnect_removes_user_from_redis(self) -> None:
        """After WS disconnect, user's awareness entry is removed from Redis."""
        tenant_id = 1
        workflow_id = "test-ws-disconnect"
        user = _FakeUser(tenant_id=tenant_id, user_id="user_disconnect")

        ws = _FakeWebSocket(
            messages=[{"type": "cursor", "payload": {"x": 1}}],
        )
        with _patch_auth(user):
            await awareness_websocket(ws, workflow_id)  # type: ignore[arg-type]

        redis = await get_redis_client()
        key = _awareness_key(tenant_id, workflow_id)
        raw = await redis.hgetall(key)
        assert "user_disconnect" not in raw

    async def test_multi_message_sequence(self) -> None:
        """Handler processes multiple messages sequentially against real Redis."""
        tenant_id = 1
        workflow_id = "test-ws-multi-msg"
        user = _FakeUser(tenant_id=tenant_id, user_id="user_multi")

        ws = _FakeWebSocket(
            messages=[
                {"type": "cursor", "payload": {"x": 1}},
                {"type": "selection", "payload": {"node_ids": ["a"]}},
                {"type": "presence", "payload": {"status": "idle"}},
            ],
        )
        with _patch_auth(user):
            await awareness_websocket(ws, workflow_id)  # type: ignore[arg-type]

        # Three acks
        assert len(ws.sent) == 3
        assert all(s["type"] == "ack" for s in ws.sent)

        # Redis entry was cleaned up on disconnect
        redis = await get_redis_client()
        key = _awareness_key(tenant_id, workflow_id)
        raw = await redis.hgetall(key)
        assert "user_multi" not in raw
