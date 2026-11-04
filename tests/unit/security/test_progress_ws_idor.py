"""
IDOR fix: stream_key ownership check in progress_ws.py.

Two levels of tests:
  1. Source-scan: verify the fix is present in the source.
  2. Unit tests with mocked Redis + authenticator: verify the runtime
     behaviour — cross-tenant keys are rejected with WS close 4003.

RED phase: all tests fail against the current implementation.
GREEN phase: tests pass after the fix is applied.
"""

import re
from pathlib import Path
from typing import Any, Optional, cast
from unittest.mock import AsyncMock, patch

from fastapi import WebSocket

import pytest

SRC = Path(__file__).parents[3] / "src"

_WS_FILE = "core/api/v1/autonomous/progress_ws.py"
_AGENT_FILE = "core/agents/autonomous_agent.py"


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _has(text: str, *patterns: str) -> bool:
    return all(re.search(p, text) for p in patterns)


# ===========================================================================
# 1. Source-scan: progress_ws.py must validate stream_key format
# ===========================================================================


class TestStreamKeyFormatValidation:
    def test_stream_key_format_is_validated(self) -> None:
        """Endpoint must reject stream_keys that don't match the expected format."""
        src = _read(_WS_FILE)
        has_regex = _has(src, r"re\.(match|fullmatch|compile|search)")
        has_validation = _has(src, r"stream_key")
        assert has_regex and has_validation, (
            f"{_WS_FILE}: must validate stream_key with a regex allowlist. "
            "Currently any arbitrary key (including Redis admin keys) can be subscribed to."
        )

    def test_rejects_invalid_format_before_xread(self) -> None:
        """Rejection must happen BEFORE the Redis xread call."""
        src = _read(_WS_FILE)
        lines = src.splitlines()
        # Find line numbers of validation and xread
        val_line = next(
            (
                i
                for i, line in enumerate(lines)
                if re.search(r"re\.(match|fullmatch|compile)", line)
            ),
            None,
        )
        xread_line = next((i for i, line in enumerate(lines) if "xread" in line), None)
        assert val_line is not None, f"{_WS_FILE}: no regex validation found"
        assert xread_line is not None, f"{_WS_FILE}: no xread call found"
        assert val_line < xread_line, (
            f"{_WS_FILE}: regex validation (line {val_line}) must come "
            f"before xread (line {xread_line})"
        )


# ===========================================================================
# 2. Source-scan: progress_ws.py must check tenant ownership
# ===========================================================================


class TestTenantOwnershipCheck:
    def test_reads_tenant_ownership_from_redis(self) -> None:
        """Endpoint must look up the tenant ownership key in Redis before streaming."""
        src = _read(_WS_FILE)
        has_owner_lookup = _has(src, r":tenant|owner|tenant_id.*redis|redis.*tenant")
        assert has_owner_lookup, (
            f"{_WS_FILE}: must read the tenant ownership key from Redis "
            "(e.g. 'workflow:<task_id>:tenant') and reject cross-tenant subscriptions."
        )

    def test_closes_websocket_on_tenant_mismatch(self) -> None:
        """Endpoint must call websocket.close() with code 4003 on tenant mismatch."""
        src = _read(_WS_FILE)
        has_403x = _has(src, r"4003")
        assert has_403x, (
            f"{_WS_FILE}: must close the WebSocket with code 4003 when the "
            "stream_key belongs to a different tenant."
        )

    def test_tenant_check_before_xread(self) -> None:
        """Tenant ownership check must happen BEFORE the blocking xread."""
        src = _read(_WS_FILE)
        lines = src.splitlines()
        tenant_check_line = next(
            (i for i, line in enumerate(lines) if re.search(r":tenant|owner_tenant", line)), None
        )
        xread_line = next((i for i, line in enumerate(lines) if "xread" in line), None)
        assert tenant_check_line is not None, f"{_WS_FILE}: no tenant ownership lookup found"
        assert xread_line is not None, f"{_WS_FILE}: no xread call found"
        assert tenant_check_line < xread_line, (
            f"{_WS_FILE}: tenant check (line {tenant_check_line}) must occur "
            f"before xread (line {xread_line})"
        )


# ===========================================================================
# 3. Source-scan: autonomous_agent.py must write tenant ownership to Redis
# ===========================================================================


class TestAutonomousAgentWritesTenantOwnership:
    def test_publishes_tenant_ownership_key(self) -> None:
        """autonomous_agent must write a tenant ownership key to Redis when publishing streams."""
        src = _read(_AGENT_FILE)
        has_tenant_write = _has(src, r":tenant", r"redis.*set|\.set\(")
        assert has_tenant_write, (
            f"{_AGENT_FILE}: must write the tenant ownership key "
            "(e.g. 'workflow:<task_id>:tenant') to Redis when publishing stream events. "
            "Without this, the WS endpoint has nothing to validate ownership against."
        )


# ===========================================================================
# 4. Runtime unit tests — mock Redis + authenticator
# ===========================================================================


class _FakeUser:
    tenant_id = 1
    user_id = "user_tenant1"


class _FakeWebSocket:
    """Minimal WebSocket test double — passed via cast(WebSocket, ...) to suppress type check."""

    def __init__(self) -> None:
        self.accepted = False
        self.closed_code: Optional[int] = None
        self.sent: list[Any] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, **_: Any) -> None:
        self.closed_code = code

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    async def receive_json(self) -> Any:
        raise Exception("no messages")


@pytest.mark.asyncio
async def test_cross_tenant_stream_key_rejected() -> None:
    """A user from tenant 1 must not be able to subscribe to a tenant-2 stream."""
    from src.core.api.v1.autonomous.progress_ws import workflow_progress_ws

    ws = _FakeWebSocket()

    # Authenticator returns tenant-1 user
    with patch(
        "src.core.api.v1.autonomous.progress_ws._auth.authenticate",
        new=AsyncMock(return_value=_FakeUser()),
    ):
        # Redis ownership key says stream belongs to tenant 2
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"2")  # owner = tenant 2

        with patch(
            "src.core.api.v1.autonomous.progress_ws.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            await workflow_progress_ws(cast(WebSocket, ws), "workflow:task_abc123:progress")

    # WS must be closed with 4003 (policy violation)
    assert ws.closed_code == 4003, (
        f"Expected close code 4003 (cross-tenant), got {ws.closed_code}. "
        "User from tenant 1 subscribed to a tenant-2 stream and was NOT rejected."
    )


@pytest.mark.asyncio
async def test_malformed_stream_key_rejected() -> None:
    """A stream_key not matching the expected format must be rejected immediately."""
    from src.core.api.v1.autonomous.progress_ws import workflow_progress_ws

    ws = _FakeWebSocket()

    with patch(
        "src.core.api.v1.autonomous.progress_ws._auth.authenticate",
        new=AsyncMock(return_value=_FakeUser()),
    ):
        mock_redis = AsyncMock()
        with patch(
            "src.core.api.v1.autonomous.progress_ws.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            # Arbitrary key — should be rejected as invalid format
            await workflow_progress_ws(cast(WebSocket, ws), "../../redis-keys/admin")

    assert (
        ws.closed_code == 4003
    ), f"Expected close code 4003 for malformed stream_key, got {ws.closed_code}."
    # xread must NOT have been called (the reject happened before any Redis read)
    mock_redis.xread.assert_not_called()


@pytest.mark.asyncio
async def test_same_tenant_stream_key_allowed() -> None:
    """A user subscribing to their own tenant's stream must be allowed through."""
    from src.core.api.v1.autonomous.progress_ws import workflow_progress_ws

    ws = _FakeWebSocket()

    with patch(
        "src.core.api.v1.autonomous.progress_ws._auth.authenticate",
        new=AsyncMock(return_value=_FakeUser()),  # tenant_id = 1
    ):
        mock_redis = AsyncMock()
        # Ownership key says stream belongs to tenant 1 (same as user)
        mock_redis.get = AsyncMock(return_value=b"1")
        # xread returns no messages immediately (simulate empty stream / disconnect)
        call_count = 0

        async def xread_then_disconnect(*_: Any, **_kw: Any) -> list:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                from fastapi import WebSocketDisconnect

                raise WebSocketDisconnect()
            return []

        mock_redis.xread = xread_then_disconnect

        with patch(
            "src.core.api.v1.autonomous.progress_ws.get_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            await workflow_progress_ws(cast(WebSocket, ws), "workflow:task_abc123:progress")

    # Should NOT have been closed with 4003 (it was allowed)
    assert ws.closed_code != 4003, (
        f"User from tenant 1 was rejected from their own tenant's stream (code {ws.closed_code}). "
        "Same-tenant subscriptions must be allowed."
    )
