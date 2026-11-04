"""
RED tests for Phase 2.2: VIBE endpoint tenant_id hardening.

These tests assert the DESIRED SECURE STATE.
They FAIL before the fix (vulnerabilities in place) and PASS after the fix.

Three vulnerabilities in workflow_generation_endpoints.py:
  V1 - VibeGenerateRequest.tenant_id field accepts client-supplied tenant_id
  V2 - list_available_agents(tenant_id: int = 1) accepts tenant_id as query param
  V3 - websocket_generate reads tenant_id from WS message payload
  V4 - websocket_generate lacks authentication entirely
"""
import inspect

import pytest

import src.core.api.workflow_generation_endpoints as _vibe_module
from src.core.api.workflow_generation_endpoints import (
    VibeGenerateRequest,
    list_available_agents,
    websocket_generate,
)


class TestVibeGenerateRequestModelHardening:
    """VibeGenerateRequest must NOT expose tenant_id as a client-settable field.

    V1: tenant_id: Optional[int] = Field(default=1, ...) allows any caller
    to supply an arbitrary tenant_id in the POST body and access another
    tenant's agents/workflows.
    """

    def test_request_model_has_no_tenant_id_field(self) -> None:
        """tenant_id must be absent from VibeGenerateRequest Pydantic model fields.

        RED: VibeGenerateRequest currently declares tenant_id with default=1.
             assert fails because 'tenant_id' IS in model_fields.
        GREEN: After removing the field, assert passes.
        """
        assert "tenant_id" not in VibeGenerateRequest.model_fields, (
            "Security violation: VibeGenerateRequest.tenant_id is a client-settable "
            "Pydantic field. Any caller can POST {tenant_id: <other_tenant>} and "
            "generate workflows scoped to a different tenant. "
            "Remove the field; obtain tenant_id from the authenticated user only."
        )


class TestListAgentsEndpointHardening:
    """GET /api/v1/vibe/agents must NOT accept tenant_id as a raw query parameter.

    V2: list_available_agents(tenant_id: int = 1) allows any caller to
    pass ?tenant_id=<other_tenant> and enumerate another tenant's agents.
    """

    def test_list_agents_has_no_tenant_id_query_param(self) -> None:
        """list_available_agents signature must not have a tenant_id parameter.

        RED: Currently the function has 'tenant_id: int = 1' in its signature
             so 'tenant_id' IS in sig.parameters, assert fails.
        GREEN: After replacing with Depends(get_current_user_dependency),
               'tenant_id' is gone from the raw signature, assert passes.
        """
        sig = inspect.signature(list_available_agents)
        assert "tenant_id" not in sig.parameters, (
            "Security violation: list_available_agents accepts tenant_id as a plain "
            "query parameter (?tenant_id=N). Any caller can enumerate agents from "
            "any tenant. Replace with "
            "'current_user: UserResponse = Depends(get_current_user_dependency)' "
            "and use current_user.tenant_id."
        )


class TestWebSocketGenerateHardening:
    """ws/generate must NOT read tenant_id from WS message payload and must auth.

    V3: tenant_id = request_data.get('tenant_id', 1) lets any WS client
        send {'tenant_id': <other_tenant>} and access data from that tenant.
    V4: The insecure endpoint has no authentication at all.
    """

    def test_insecure_ws_does_not_read_tenant_id_from_payload(self) -> None:
        """websocket_generate must not call request_data.get('tenant_id', ...).

        RED: Source currently contains request_data.get("tenant_id", 1) so the
             substring IS present, assert fails.
        GREEN: After removing that line (and using user.tenant_id from auth),
               substring is gone, assert passes.
        """
        source = inspect.getsource(websocket_generate)
        assert 'request_data.get("tenant_id"' not in source, (
            "Security violation: websocket_generate reads tenant_id from the "
            "WS message payload. Any client can send {tenant_id: <other>} and "
            "access data from a different tenant. "
            "Authenticate the connection first (websocket_auth.authenticate), "
            "then derive tenant_id from the authenticated user object."
        )

    def test_insecure_ws_authenticates_connection(self) -> None:
        """websocket_generate must authenticate before processing messages.

        RED: Source has no reference to websocket_auth or authenticate,
             so assert fails.
        GREEN: After adding the auth call (mirroring websocket_generate_secure),
               assert passes.
        """
        source = inspect.getsource(websocket_generate)
        has_auth_call = (
            "websocket_auth" in source or "authenticate" in source
        )
        assert has_auth_call, (
            "Security violation: websocket_generate accepts WebSocket connections "
            "without any authentication. Any anonymous client can stream workflow "
            "generation requests. "
            "Add: user = await websocket_auth.authenticate(websocket); "
            "if not user: return"
        )
