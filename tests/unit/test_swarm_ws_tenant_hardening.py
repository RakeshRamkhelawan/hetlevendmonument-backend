"""RED tests for Phase 2.3: Swarm WebSocket endpoint tenant_id hardening.

Security assertions:
- REST endpoints (start_swarm, submit_feedback, list_sessions) must not accept
  tenant_id as a client-controlled query parameter.
- swarm_stream WebSocket must not accept anonymous (unauthenticated) connections.
"""

import inspect
import pytest

from src.core.api.swarm_websocket_endpoints import (
    list_sessions,
    start_swarm,
    submit_feedback,
    swarm_stream,
)


class TestRestEndpointTenantQueryParamRemoved:
    """REST endpoints must source tenant_id from JWT, not from query params."""

    def test_start_swarm_has_no_tenant_id_query_param(self) -> None:
        """start_swarm must not expose tenant_id as a query parameter.

        An attacker can POST /api/v1/swarm/start?tenant_id=<any> and start a
        swarm session scoped to an arbitrary tenant. Replace with
        'current_user: UserResponse = Depends(get_current_user_dependency)'
        and use current_user.tenant_id.
        """
        sig = inspect.signature(start_swarm)
        assert "tenant_id" not in sig.parameters, (
            "Security violation: start_swarm accepts tenant_id as a plain query parameter. "
            "Any caller can POST ?tenant_id=N and start a swarm for a different tenant. "
            "Replace with 'current_user: UserResponse = Depends(get_current_user_dependency)' "
            "and use current_user.tenant_id."
        )

    def test_submit_feedback_has_no_tenant_id_query_param(self) -> None:
        """submit_feedback must not expose tenant_id as a query parameter.

        An attacker can POST /api/v1/swarm/feedback?tenant_id=<any> and inject
        feedback into another tenant's swarm session.
        """
        sig = inspect.signature(submit_feedback)
        assert "tenant_id" not in sig.parameters, (
            "Security violation: submit_feedback accepts tenant_id as a plain query parameter. "
            "Any caller can POST ?tenant_id=N and submit feedback to another tenant's swarm. "
            "Replace with 'current_user: UserResponse = Depends(get_current_user_dependency)' "
            "and use current_user.tenant_id."
        )

    def test_list_sessions_has_no_tenant_id_query_param(self) -> None:
        """list_sessions must not expose tenant_id as a query parameter.

        An attacker can GET /api/v1/swarm/sessions?tenant_id=<any> and enumerate
        another tenant's active swarm sessions.
        """
        sig = inspect.signature(list_sessions)
        assert "tenant_id" not in sig.parameters, (
            "Security violation: list_sessions accepts tenant_id as a plain query parameter. "
            "Any caller can GET ?tenant_id=N and enumerate another tenant's sessions. "
            "Replace with 'current_user: UserResponse = Depends(get_current_user_dependency)' "
            "and use current_user.tenant_id."
        )


class TestSwarmStreamWebSocketAuth:
    """swarm_stream WebSocket must authenticate before accepting connections."""

    def test_swarm_stream_does_not_accept_without_auth(self) -> None:
        """swarm_stream must authenticate the WebSocket connection before accepting.

        Currently swarm_stream calls manager.connect() (which calls
        websocket.accept()) before any auth check. Any anonymous client can
        connect and receive live swarm events from any session.

        The endpoint must call auth.authenticate(websocket) (or equivalent)
        and return immediately when authentication fails, BEFORE manager.connect().
        """
        source = inspect.getsource(swarm_stream)
        has_auth = (
            "auth.authenticate" in source
            or "websocket_auth.authenticate" in source
            or "authenticate(websocket)" in source
        )
        assert has_auth, (
            "Security violation: swarm_stream accepts WebSocket connections without "
            "authentication. Any anonymous client can connect and receive live swarm "
            "events. Add: user = await auth.authenticate(websocket); if not user: return "
            "BEFORE calling manager.connect()."
        )

    def test_swarm_stream_uses_authenticated_tenant_id(self) -> None:
        """swarm_stream must use tenant_id from authenticated user, not from payload.

        After adding auth, the service lookup (manager.get_service) must use
        user.tenant_id, not a hardcoded default or message payload.
        """
        source = inspect.getsource(swarm_stream)
        # Must not use hardcoded tenant_id=1 anywhere in the function body
        assert "tenant_id=1" not in source, (
            "Security violation: swarm_stream contains a hardcoded 'tenant_id=1'. "
            "After auth, use user.tenant_id for all service lookups."
        )
