"""Type-contract tests for src.core.auth.websocket_auth."""

from __future__ import annotations

from typing import Any, get_type_hints

import pytest

from src.core.auth.types import VerifiedJWTPayload
from src.core.auth.websocket_auth import AuthenticatedUser, WebSocketAuthenticator


@pytest.mark.unit
class TestWebSocketAuthTypeContract:
    """Ensure WebSocketAuthenticator uses VerifiedJWTPayload and list[str]."""

    def test_payload_to_user_accepts_verified_payload(self) -> None:
        hints = get_type_hints(WebSocketAuthenticator._payload_to_user)
        assert hints["payload"] is VerifiedJWTPayload, (
            f"_payload_to_user payload expected VerifiedJWTPayload, got {hints['payload']}"
        )

    def test_payload_to_user_payload_is_not_any_dict(self) -> None:
        hints = get_type_hints(WebSocketAuthenticator._payload_to_user)
        assert hints["payload"] is not Any

    def test_payload_to_user_interprets_roles_as_list_str(self) -> None:
        authenticator = WebSocketAuthenticator()
        payload = VerifiedJWTPayload(
            sub="user_1",
            tenant_id=7,
            roles=["read", "write"],
        )
        user = authenticator._payload_to_user(payload)
        assert user is not None
        assert isinstance(user.roles, list)
        assert user.roles == ["read", "write"]

    def test_authenticated_user_roles_typed_as_list_str(self) -> None:
        user = AuthenticatedUser(user_id="u1", tenant_id=1, roles=["admin"])
        assert user.roles == ["admin"]
