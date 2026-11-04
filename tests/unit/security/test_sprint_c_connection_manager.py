"""
Sprint C: ConnectionManager must use tenant-scoped buckets.

Without tenant scoping, any broadcast (background or triggered) lands on every
WebSocket connection regardless of which tenant owns it — a cross-tenant data leak.

Fix: ConnectionManager stores connections in dict[int, list[WebSocket]] keyed by
tenant_id.  connect() must accept tenant_id.  send_to_all() either disappears or
only broadcasts within a single tenant's bucket.  broadcast_updates() must iterate
per-tenant rather than calling a flat send_to_all().

Two levels of tests:
  1. Source-scan: verify structural fix is present.
  2. Runtime unit tests with fake WebSockets: cross-tenant isolation enforced.

RED phase: all tests fail against the current flat-list implementation.
GREEN phase: all tests pass after the fix.
"""

import re
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest

SRC = Path(__file__).parents[3] / "src"
_FILE = "core/api/monitoring_dashboard_endpoints.py"


def _src() -> str:
    return (SRC / _FILE).read_text(encoding="utf-8")


# ===========================================================================
# 1. Source-scan: ConnectionManager.connect() must accept tenant_id
# ===========================================================================


class TestConnectAcceptsTenantId:
    def test_connect_signature_has_tenant_id(self) -> None:
        """connect() must accept a tenant_id parameter."""
        src = _src()
        # Find the connect method body
        match = re.search(
            r"async def connect\s*\([^)]+\)",
            src,
        )
        assert match is not None, f"{_FILE}: connect() method not found"
        signature = match.group(0)
        assert "tenant_id" in signature, (
            f"{_FILE}: ConnectionManager.connect() must accept tenant_id.\n"
            "Current signature: " + signature
        )


# ===========================================================================
# 2. Source-scan: _connections must be a dict, not a flat list
# ===========================================================================


class TestConnectionsIsDict:
    def test_active_connections_stored_as_dict(self) -> None:
        """Connections must be stored in a dict keyed by tenant_id, not a flat list."""
        src = _src()
        # Look for dict initialisation inside ConnectionManager.__init__
        # Acceptable patterns: {}, dict(), defaultdict
        has_dict_init = bool(
            re.search(r"_connections\s*[=:]\s*\{\}", src)
            or re.search(r"_connections\s*[=:]\s*dict\(\)", src)
            or re.search(r"_connections\s*[=:]\s*defaultdict", src)
            or re.search(r"[Dd]ict\[int", src)  # Dict[int or dict[int
        )
        assert has_dict_init, (
            f"{_FILE}: ConnectionManager._connections must be a dict[int, list[WebSocket]], "
            "not a flat list.  A flat list cannot enforce per-tenant isolation."
        )


# ===========================================================================
# 3. Source-scan: broadcast_updates must not call flat send_to_all()
# ===========================================================================


class TestBroadcastUpdatesTenantScoped:
    def test_broadcast_updates_uses_tenant_scoped_send(self) -> None:
        """broadcast_updates() must not send to all connections regardless of tenant."""
        src = _src()
        lines = src.splitlines()

        # Locate broadcast_updates function body
        start = next(
            (i for i, line in enumerate(lines) if re.search(r"async def broadcast_updates", line)),
            None,
        )
        assert start is not None, f"{_FILE}: broadcast_updates() not found"

        # Collect body until next same-level def
        body_lines = []
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        for line in lines[start + 1 :]:
            if line.strip() and re.match(r"(async )?def |class ", line.lstrip()):
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent:
                    break
            body_lines.append(line)

        body = "\n".join(body_lines)

        # After the fix, broadcast_updates() must NOT call send_to_all()
        # (it should instead iterate per-tenant via send_to_tenant or similar)
        calls_flat_send_to_all = bool(re.search(r"\.send_to_all\(", body))
        assert not calls_flat_send_to_all, (
            f"{_FILE}: broadcast_updates() must not call send_to_all() — "
            "that broadcasts to every tenant.  Use send_to_tenant() per tenant instead."
        )

    def test_send_to_tenant_method_exists(self) -> None:
        """A send_to_tenant(tenant_id, data) method must exist on ConnectionManager."""
        src = _src()
        has_method = bool(re.search(r"def send_to_tenant\s*\(", src))
        assert has_method, (
            f"{_FILE}: ConnectionManager must have a send_to_tenant(tenant_id, data) method "
            "so broadcast_updates() can push per-tenant instead of flat send_to_all()."
        )


# ===========================================================================
# 4. Source-scan: WS endpoints must pass tenant_id to connect()
# ===========================================================================


class TestWebSocketEndpointsPassTenantId:
    def _endpoint_body(self, endpoint_name: str) -> str:
        src = _src()
        lines = src.splitlines()
        start = next(
            (i for i, line in enumerate(lines) if re.search(rf"async def {endpoint_name}\b", line)),
            None,
        )
        assert start is not None, f"{_FILE}: {endpoint_name}() not found"
        body_lines = []
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        for line in lines[start + 1 :]:
            if line.strip() and re.match(r"(async )?def |class ", line.lstrip()):
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent:
                    break
            body_lines.append(line)
        return "\n".join(body_lines)

    def test_dashboard_websocket_passes_tenant_id(self) -> None:
        """dashboard_websocket must pass current_user.tenant_id to connect()."""
        body = self._endpoint_body("dashboard_websocket")
        assert re.search(r"connect\(.*tenant_id", body, re.DOTALL) or re.search(
            r"connect\(websocket.*current_user\.tenant_id", body, re.DOTALL
        ), (
            f"{_FILE}: dashboard_websocket() must pass current_user.tenant_id "
            "to connection_manager.connect()."
        )

    def test_alerts_websocket_passes_tenant_id(self) -> None:
        """alerts_websocket must pass current_user.tenant_id to connect()."""
        body = self._endpoint_body("alerts_websocket")
        assert re.search(r"connect\(.*tenant_id", body, re.DOTALL) or re.search(
            r"connect\(websocket.*current_user\.tenant_id", body, re.DOTALL
        ), (
            f"{_FILE}: alerts_websocket() must pass current_user.tenant_id "
            "to connection_manager.connect()."
        )


# ===========================================================================
# 5. Runtime unit tests — isolated ConnectionManager with fake WebSockets
# ===========================================================================


class _FakeWebSocket:
    """Minimal WebSocket test double."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[Any] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, **_: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_tenant_a_does_not_receive_tenant_b_broadcast() -> None:
    """
    Cross-tenant isolation: broadcasting to tenant 2 must NOT deliver to tenant 1.
    """
    from src.core.api.monitoring_dashboard_endpoints import ConnectionManager

    manager = ConnectionManager()
    ws_t1 = _FakeWebSocket()
    ws_t2 = _FakeWebSocket()

    await manager.connect(ws_t1, tenant_id=1)  # type: ignore[arg-type]
    await manager.connect(ws_t2, tenant_id=2)  # type: ignore[arg-type]

    await manager.send_to_tenant(2, {"msg": "tenant2-only"})

    assert not any(
        m.get("msg") == "tenant2-only" for m in ws_t1.sent
    ), "Tenant 1 connection received a broadcast intended for tenant 2 — cross-tenant leak."
    assert any(
        m.get("msg") == "tenant2-only" for m in ws_t2.sent
    ), "Tenant 2 connection did NOT receive its own broadcast."


@pytest.mark.asyncio
async def test_same_tenant_receives_broadcast() -> None:
    """All connections for the same tenant receive the broadcast."""
    from src.core.api.monitoring_dashboard_endpoints import ConnectionManager

    manager = ConnectionManager()
    ws_a = _FakeWebSocket()
    ws_b = _FakeWebSocket()

    await manager.connect(ws_a, tenant_id=5)  # type: ignore[arg-type]
    await manager.connect(ws_b, tenant_id=5)  # type: ignore[arg-type]

    await manager.send_to_tenant(5, {"msg": "hello-t5"})

    assert any(m.get("msg") == "hello-t5" for m in ws_a.sent), "First connection missed broadcast"
    assert any(m.get("msg") == "hello-t5" for m in ws_b.sent), "Second connection missed broadcast"


@pytest.mark.asyncio
async def test_disconnect_removes_from_correct_tenant_bucket() -> None:
    """disconnect() must remove the connection from the owning tenant's bucket only."""
    from src.core.api.monitoring_dashboard_endpoints import ConnectionManager

    manager = ConnectionManager()
    ws_t1 = _FakeWebSocket()
    ws_t2 = _FakeWebSocket()

    await manager.connect(ws_t1, tenant_id=1)  # type: ignore[arg-type]
    await manager.connect(ws_t2, tenant_id=2)  # type: ignore[arg-type]

    manager.disconnect(ws_t1)  # type: ignore[arg-type]

    # After disconnect, sending to tenant 1 should not error and ws_t1 gets nothing
    await manager.send_to_tenant(1, {"msg": "after-disconnect"})
    assert not any(
        m.get("msg") == "after-disconnect" for m in ws_t1.sent
    ), "Disconnected tenant-1 connection still received a broadcast."
    # Tenant 2 is unaffected
    await manager.send_to_tenant(2, {"msg": "t2-ok"})
    assert any(
        m.get("msg") == "t2-ok" for m in ws_t2.sent
    ), "Tenant 2 connection was incorrectly affected by tenant 1 disconnect."


@pytest.mark.asyncio
async def test_active_connections_count_reflects_all_tenants() -> None:
    """active_connections property must count connections across all tenants."""
    from src.core.api.monitoring_dashboard_endpoints import ConnectionManager

    manager = ConnectionManager()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()
    ws3 = _FakeWebSocket()

    await manager.connect(ws1, tenant_id=1)  # type: ignore[arg-type]
    await manager.connect(ws2, tenant_id=2)  # type: ignore[arg-type]
    await manager.connect(ws3, tenant_id=2)  # type: ignore[arg-type]

    total = len(manager.active_connections)
    assert total == 3, f"Expected 3 active connections across all tenants, got {total}"
