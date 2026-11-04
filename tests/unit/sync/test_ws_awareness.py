"""
Unit tests for WebSocket awareness handler (src/core/api/v1/sync/ws_handler.py).

Covers:
- Happy path: cursor/selection/presence updates
- Invalid workflow_id rejected
- Invalid message format returns error
- WebSocketDisconnect triggers HDEL cleanup
- Subprotocol negotiation
- Auth failure handling
- Server-side heartbeat

ASCII-only, no emojis (CLAUDE.md Section 10).
"""

import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from src.core.api.v1.sync.ws_handler import (
    _AWARENESS_TTL_SECONDS,
    _HEARTBEAT_INTERVAL_SECONDS,
    _AwarenessMessageValidator,
    awareness_websocket,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeUser:
    tenant_id = 1
    user_id = "user_001"
    email = "user@example.com"
    roles: list[str] = []


class _FakeWebSocket:
    """Minimal WebSocket test double."""

    def __init__(
        self,
        messages: Optional[list[Any]] = None,
        hang_after: bool = False,
    ) -> None:
        self.accepted = False
        self.closed_code: Optional[int] = None
        self.closed_reason: Optional[str] = None
        self.sent: list[Any] = []
        self._messages = messages or []
        self._index = 0
        self._hang_after = hang_after
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
            if self._hang_after:
                # Hang until cancelled (gives asyncio.wait_for time to timeout)
                await asyncio.sleep(3600)
            raise WebSocketDisconnect()
        msg = self._messages[self._index]
        self._index += 1
        return msg


class _FakeRedis:
    """Minimal Redis test double with pipeline support."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}
        self.hdel_calls: list[tuple[str, str]] = []
        self.pipeline_calls: list[list[Any]] = []

    async def hset(self, key: str, field: str, value: str) -> int:
        if key not in self.data:
            self.data[key] = {}
        self.data[key][field] = value
        return 1

    async def expire(self, key: str, seconds: int) -> int:
        self.ttls[key] = seconds
        return 1

    async def hdel(self, key: str, field: str) -> int:
        self.hdel_calls.append((key, field))
        # NOTE: Intentionally do NOT delete from self.data so that post-handler
        # assertions can still inspect the written state.  Tests that verify
        # cleanup behaviour use ``hdel_calls`` instead.
        return 1

    async def hgetall(self, key: str) -> dict[str, str]:
        return self.data.get(key, {})

    async def aclose(self) -> None:
        pass

    def pipeline(self) -> "_FakeRedisPipeline":
        return _FakeRedisPipeline(self)


class _FakeRedisPipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._commands: list[tuple[str, tuple[Any, ...]]] = []

    def hset(self, key: str, field: str, value: str) -> None:
        self._commands.append(("hset", (key, field, value)))

    def expire(self, key: str, seconds: int) -> None:
        self._commands.append(("expire", (key, seconds)))

    async def execute(self) -> list[Any]:
        results = []
        for cmd, args in self._commands:
            if cmd == "hset":
                results.append(await self._redis.hset(*args))
            elif cmd == "expire":
                results.append(await self._redis.expire(*args))
        self._redis.pipeline_calls.append(self._commands)
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _patch_redis(redis: _FakeRedis) -> Any:
    return patch(
        "src.core.api.v1.sync.ws_handler.get_redis_client",
        new=AsyncMock(return_value=redis),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAwarenessMessageValidator:
    """Tests for the awareness message validator."""

    def test_valid_cursor_message(self) -> None:
        data = {"type": "cursor", "payload": {"x": 100, "y": 200, "color": "#ff0000"}}
        msg_type, payload = _AwarenessMessageValidator.validate(data)
        assert msg_type == "cursor"
        assert payload["x"] == 100

    def test_valid_selection_message(self) -> None:
        data = {"type": "selection", "payload": {"node_ids": ["a", "b"]}}
        msg_type, payload = _AwarenessMessageValidator.validate(data)
        assert msg_type == "selection"
        assert payload["node_ids"] == ["a", "b"]

    def test_valid_presence_message(self) -> None:
        data = {"type": "presence", "payload": {"status": "active"}}
        msg_type, payload = _AwarenessMessageValidator.validate(data)
        assert msg_type == "presence"

    def test_rejects_invalid_type(self) -> None:
        data = {"type": "hacked", "payload": {"x": 1}}
        with pytest.raises(ValueError, match="Invalid type"):
            _AwarenessMessageValidator.validate(data)

    def test_rejects_missing_type(self) -> None:
        data = {"payload": {"x": 1}}
        with pytest.raises(ValueError, match="Invalid type"):
            _AwarenessMessageValidator.validate(data)

    def test_rejects_non_dict_payload(self) -> None:
        data = {"type": "cursor", "payload": "bad"}
        with pytest.raises(ValueError, match="payload.*must be an object"):
            _AwarenessMessageValidator.validate(data)

    def test_rejects_non_dict_message(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            _AwarenessMessageValidator.validate("not a dict")


class TestAwarenessWebSocketHappyPath:
    """Happy path tests for the awareness websocket handler."""

    @pytest.mark.asyncio
    async def test_cursor_update_writes_to_redis(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor", "payload": {"x": 10, "y": 20}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Should have written to Redis
        key = "awareness:1:workflow-abc"
        assert key in redis.data
        assert "user_001" in redis.data[key]

        # Parse stored JSON
        entry = __import__("json").loads(redis.data[key]["user_001"])
        assert entry["user_id"] == "user_001"
        assert entry["type"] == "cursor"
        assert entry["payload"]["x"] == 10

    @pytest.mark.asyncio
    async def test_ack_response_sent(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor", "payload": {"x": 1}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "ack"
        assert "ts" in ws.sent[0]

    @pytest.mark.asyncio
    async def test_redis_ttl_set(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor", "payload": {"x": 1}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        assert redis.ttls.get("awareness:1:workflow-abc") == _AWARENESS_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_subprotocol_json_selected(self) -> None:
        ws = _FakeWebSocket()
        ws.scope["subprotocols"] = ["json"]
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        assert ws.accepted is True
        assert getattr(ws, "accepted_subprotocol", None) == "json"

    @pytest.mark.asyncio
    async def test_multiple_messages_processed(self) -> None:
        ws = _FakeWebSocket(
            messages=[
                {"type": "cursor", "payload": {"x": 1}},
                {"type": "selection", "payload": {"node_ids": ["n1"]}},
            ]
        )
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Two acks
        assert len(ws.sent) == 2
        assert ws.sent[0]["type"] == "ack"
        assert ws.sent[1]["type"] == "ack"

        # Latest payload is selection
        key = "awareness:1:workflow-abc"
        entry = __import__("json").loads(redis.data[key]["user_001"])
        assert entry["type"] == "selection"


class TestAwarenessWebSocketValidation:
    """Unhappy path: validation failures."""

    @pytest.mark.asyncio
    async def test_invalid_workflow_id_rejected(self) -> None:
        ws = _FakeWebSocket()
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "../../etc/passwd")  # type: ignore[arg-type]

        assert ws.closed_code == 4003
        assert "Invalid workflow_id" in (ws.closed_reason or "")

    @pytest.mark.asyncio
    async def test_invalid_message_type_returns_error(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "evil", "payload": {}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Should receive error, not crash
        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "error"
        assert "Invalid type" in ws.sent[0]["message"]

    @pytest.mark.asyncio
    async def test_missing_payload_returns_error(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor"}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "error"

    @pytest.mark.asyncio
    async def test_auth_failure_closes_connection(self) -> None:
        ws = _FakeWebSocket()
        redis = _FakeRedis()

        with _patch_auth(None), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Auth layer closes the connection; ws should not be accepted
        assert ws.accepted is False


class TestAwarenessWebSocketCleanup:
    """Disconnect and cleanup behaviour."""

    @pytest.mark.asyncio
    async def test_disconnect_triggers_hdel(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor", "payload": {"x": 1}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        assert ("awareness:1:workflow-abc", "user_001") in redis.hdel_calls

    @pytest.mark.asyncio
    async def test_disconnect_without_prior_write(self) -> None:
        """Disconnect immediately (no messages) still calls HDEL gracefully."""
        ws = _FakeWebSocket(messages=[])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # HDEL is attempted even if no HSET happened
        assert ("awareness:1:workflow-abc", "user_001") in redis.hdel_calls

    @pytest.mark.asyncio
    async def test_pipeline_used_for_atomic_write(self) -> None:
        ws = _FakeWebSocket(messages=[{"type": "cursor", "payload": {"x": 1}}])
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Pipeline should have been executed
        assert len(redis.pipeline_calls) == 1
        commands = redis.pipeline_calls[0]
        assert any(c[0] == "hset" for c in commands)
        assert any(c[0] == "expire" for c in commands)


class TestAwarenessWebSocketHeartbeat:
    """Server-side heartbeat behaviour."""

    @pytest.mark.asyncio
    async def test_heartbeat_sent_when_no_message_received(self) -> None:
        """After heartbeat interval without client message, server sends heartbeat."""
        ws = _FakeWebSocket(messages=[], hang_after=True)
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            with patch(
                "src.core.api.v1.sync.ws_handler._HEARTBEAT_INTERVAL_SECONDS",
                0.05,
            ):
                task = asyncio.create_task(
                    awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]
                )
                # Give handler time to timeout and send heartbeat
                await asyncio.sleep(0.15)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        # Should have sent at least one heartbeat
        heartbeats = [s for s in ws.sent if s.get("type") == "heartbeat"]
        assert len(heartbeats) >= 1

    @pytest.mark.asyncio
    async def test_no_heartbeat_while_messages_flow(self) -> None:
        """When messages arrive within interval, no heartbeat is sent."""
        ws = _FakeWebSocket(
            messages=[
                {"type": "cursor", "payload": {"x": 1}},
                {"type": "cursor", "payload": {"x": 2}},
            ],
        )
        redis = _FakeRedis()

        with _patch_auth(_FakeUser()), _patch_redis(redis):
            with patch(
                "src.core.api.v1.sync.ws_handler._HEARTBEAT_INTERVAL_SECONDS",
                3600,  # Long interval — messages arrive before timeout
            ):
                await awareness_websocket(ws, "workflow-abc")  # type: ignore[arg-type]

        # Only acks, no heartbeats
        assert all(s["type"] == "ack" for s in ws.sent)
        assert not any(s.get("type") == "heartbeat" for s in ws.sent)
