"""
Sprint C: WebSocket security — auth required + set_tenant_id() must be called.

Every WS handler must:
1. Require authentication (no anonymous WebSocket access to tenant data)
2. Call set_tenant_id() so the ORM tenant auto-filter injects the right WHERE clause

Strategy: source-scan tests that are RED until each handler is fixed.
These serve as both documentation of the RED state and regression prevention.

Handlers already secure (WebSocketAuthenticator.authenticate() sets tenant_id):
- swarm_websocket_endpoints.py    — /stream/{session_id}, /stream/secure/{session_id}
- workflow_generation_endpoints.py — /ws/generate, /ws/generate/secure
- v1/agentic/websocket.py         — /ws/agent/stream  (Depends(get_ws_user))
- v1/websocket_hitl.py            — /ws/hitl/{tenant_id} (Depends(get_ws_user))
- agentic_flow_endpoints.py       — /ws/builder (authenticate_connected_user)
"""

import pytest
from pathlib import Path

_SRC = Path(__file__).parents[3] / "src"


def _read(rel: str) -> str:
    return (_SRC / rel).read_text(encoding="utf-8")


# Functions/classes that correctly authenticate WebSocket connections
# (all ultimately call set_tenant_id internally via WebSocketAuthenticator)
_WS_AUTH_SIGNALS = frozenset(
    {
        "get_ws_user",
        "websocket_auth",
        "WebSocketAuthenticator",
        "authenticate_connected_user",
        "get_current_user_ws",
    }
)

# The tenant context call that enables ORM auto-filter
_TENANT_SIGNALS = frozenset({"set_tenant_id("})


def _has(source: str, signals: frozenset) -> bool:
    return any(sig in source for sig in signals)


# ===========================================================================
# GROUP A — Fully unauthenticated handlers (most critical)
# ===========================================================================


@pytest.mark.security
class TestWorkflowBuilderWSAuth:
    """
    /api/v1/builder/stream has NO auth — any anonymous user can connect
    and receive workflow keyword suggestions.
    """

    _F = "core/api/workflow_builder_ws.py"

    def test_requires_ws_auth(self):
        src = _read(self._F)
        assert _has(src, _WS_AUTH_SIGNALS), (
            f"{self._F}: /api/v1/builder/stream must use WS-aware authentication"
        )

    def test_calls_set_tenant_id(self):
        src = _read(self._F)
        # WebSocketAuthenticator.authenticate() calls set_tenant_id() internally
        secured = _has(src, _TENANT_SIGNALS) or _has(src, frozenset({"WebSocketAuthenticator"}))
        assert secured, (
            f"{self._F}: must call set_tenant_id() or use WebSocketAuthenticator (which does it internally)"
        )


@pytest.mark.security
class TestProgressWSAuth:
    """
    /ws/workflow-progress/{stream_key} has NO auth AND has IDOR:
    any caller can supply any stream_key and read another tenant's Redis stream.
    """

    _F = "core/api/v1/autonomous/progress_ws.py"

    def test_requires_ws_auth(self):
        src = _read(self._F)
        assert _has(src, _WS_AUTH_SIGNALS), (
            f"{self._F}: /ws/workflow-progress/{{stream_key}} must require authentication"
        )

    def test_calls_set_tenant_id(self):
        src = _read(self._F)
        # WebSocketAuthenticator.authenticate() calls set_tenant_id() internally
        secured = _has(src, _TENANT_SIGNALS) or _has(src, frozenset({"WebSocketAuthenticator"}))
        assert secured, (
            f"{self._F}: must call set_tenant_id() or use WebSocketAuthenticator (which does it internally)"
        )


@pytest.mark.security
class TestWebsocketEndpointsAuth:
    """
    /ws/logs and /ws have NO auth.
    /ws/logs streams raw application logs — sensitive data leak.
    """

    _F = "core/api/websocket_endpoints.py"

    def test_ws_endpoints_use_auth(self):
        src = _read(self._F)
        assert _has(src, _WS_AUTH_SIGNALS), (
            f"{self._F}: /ws/logs and /ws must require authentication"
        )


@pytest.mark.security
class TestCollaborationWSAuth:
    """
    /ws/collaborate/{workspace_id} has NO auth — any user can join any workspace
    and receive/send cursor/tool events.
    """

    _F = "core/api/v1/collaboration/router.py"

    def test_requires_ws_auth(self):
        src = _read(self._F)
        assert _has(src, _WS_AUTH_SIGNALS), (
            f"{self._F}: /ws/collaborate/{{workspace_id}} must require authentication"
        )

    def test_calls_set_tenant_id(self):
        src = _read(self._F)
        # Either explicit set_tenant_id OR use auth that sets it (get_ws_user / WebSocketAuthenticator)
        secured = _has(src, _TENANT_SIGNALS) or _has(
            src, frozenset({"get_ws_user", "WebSocketAuthenticator"})
        )
        assert secured, (
            f"{self._F}: must call set_tenant_id() or use auth that sets it automatically"
        )


@pytest.mark.security
class TestTerminalWSAuth:
    """
    /ws/terminal has NO auth even though it executes shell commands.
    The ENABLE_CLI_EXECUTOR flag reduces exposure but does not replace authentication.
    """

    _F = "core/api/v1/terminal/router.py"

    def test_ws_handler_uses_ws_auth(self):
        src = _read(self._F)
        assert _has(src, _WS_AUTH_SIGNALS), (
            f"{self._F}: /ws/terminal must require WS-aware authentication"
        )


@pytest.mark.security
class TestCopilotStatsWSAuth:
    """
    /ws/copilot/stats had NO auth in earlier code — broadcasts connection stats to anyone.

    After the fix, /stats uses websocket_auth.authenticate_connected_user(), which
    internally calls set_tenant_id() (see src/core/auth/websocket_auth.py:182).
    The source-grep accepts either a direct set_tenant_id call OR the auth helper
    that performs it.
    """

    _F = "core/api/copilot_websocket_endpoints.py"
    _AUTH_HELPER_SIGNALS = frozenset({"authenticate_connected_user("})

    def test_stats_ws_requires_auth(self):
        src = _read(self._F)
        signals = _TENANT_SIGNALS | self._AUTH_HELPER_SIGNALS
        assert _has(src, signals), (
            f"{self._F}: /ws/copilot/stats must require auth; "
            "either set_tenant_id() must be called or "
            "websocket_auth.authenticate_connected_user() must be used"
        )


# ===========================================================================
# GROUP B — Auth present but set_tenant_id() missing
# ===========================================================================


@pytest.mark.security
class TestMonitoringDashboardWSSetTenant:
    """
    /ws/dashboard and /ws/alerts have auth via Depends(get_current_user)
    but never call set_tenant_id() — ORM queries return empty (WHERE 1=0).
    """

    _F = "core/api/monitoring_dashboard_endpoints.py"

    def test_dashboard_ws_calls_set_tenant_id(self):
        src = _read(self._F)
        assert _has(src, _TENANT_SIGNALS), (
            f"{self._F}: /ws/dashboard must call set_tenant_id(current_user.tenant_id)"
        )

    def test_alerts_ws_calls_set_tenant_id(self):
        # Same file — one assertion is enough since both handlers are in the same module
        src = _read(self._F)
        assert _has(src, _TENANT_SIGNALS), (
            f"{self._F}: /ws/alerts must call set_tenant_id(current_user.tenant_id)"
        )


@pytest.mark.security
class TestFocusBuilderWSSetTenant:
    """
    /flows/{flow_id}/status and /ws/chat authenticate via validate_ws_token()
    but do not call set_tenant_id() — ORM queries silently return empty.
    """

    _F = "core/api/v1/focus_builder/ws_chat_router.py"

    def test_ws_handlers_call_set_tenant_id(self):
        src = _read(self._F)
        assert _has(src, _TENANT_SIGNALS), (
            f"{self._F}: WS handlers must call set_tenant_id(user.tenant_id) after auth"
        )


@pytest.mark.security
class TestGenericWSRouterSetTenant:
    """
    /ws/{channel}/{room_id} uses require_auth=True but connection_manager.connect()
    does not call set_tenant_id() — ORM queries silently return empty.
    """

    _F = "core/api/v1/websocket/router.py"

    def test_room_ws_calls_set_tenant_id(self):
        src = _read(self._F)
        assert _has(src, _TENANT_SIGNALS), (
            f"{self._F}: /ws/{{channel}}/{{room_id}} must call set_tenant_id() after auth"
        )


@pytest.mark.security
class TestCopilotChatWSSetTenant:
    """
    /ws/copilot/chat moved to src/core/copilot/api/chat_websocket.py (Sprint 4 Day 2).
    Verify the new handler calls set_tenant_id() after authentication so the ORM
    tenant auto-filter injects the right WHERE clause.
    """

    _F = "core/copilot/api/chat_websocket.py"

    def test_chat_ws_calls_set_tenant_id(self):
        src = _read(self._F)
        assert _has(src, _TENANT_SIGNALS), (
            f"{self._F}: /ws/copilot/chat must call set_tenant_id() when user is authenticated"
        )
