"""Type-contract tests for src.core.auth.jwt_handler."""

from __future__ import annotations

from typing import Any, get_args, get_type_hints

import pytest

from src.core.auth.jwt_handler import JWTHandler
from src.core.auth.token_blacklist import TokenBlacklist
from src.core.auth.types import JWTPayload, VerifiedJWTPayload


@pytest.mark.unit
class TestJWTPayloadTypeContract:
    """Ensure JWTHandler uses the shared JWTPayload / VerifiedJWTPayload types."""

    def test_create_access_token_payload_is_jwt_payload(self) -> None:
        hints = get_type_hints(JWTHandler.create_access_token)
        assert hints["data"] is JWTPayload, (
            f"create_access_token payload expected JWTPayload, got {hints['data']}"
        )

    def test_create_access_token_payload_is_not_any_dict(self) -> None:
        hints = get_type_hints(JWTHandler.create_access_token)
        assert hints["data"] is not Any
        assert Any not in get_args(hints["data"])

    def test_verify_token_returns_verified_payload(self) -> None:
        hints = get_type_hints(JWTHandler.verify_token)
        ret = hints["return"]
        assert VerifiedJWTPayload in get_args(ret), (
            f"verify_token return expected VerifiedJWTPayload | None, got {ret}"
        )

    def test_verify_token_with_blacklist_returns_verified_payload(self) -> None:
        hints = get_type_hints(
            JWTHandler.verify_token_with_blacklist,
            localns={"TokenBlacklist": TokenBlacklist},
        )
        ret = hints["return"]
        assert VerifiedJWTPayload in get_args(ret), (
            f"verify_token_with_blacklist return expected VerifiedJWTPayload | None, got {ret}"
        )

    def test_verify_token_rejects_missing_exp(self) -> None:
        handler = JWTHandler()
        # jose.encode without exp is not possible with our wrapper, so test via decode options
        token = handler.create_access_token({"sub": "test"})
        # Removing the exp claim is hard; instead verify explicit no-exp token is rejected
        from jose import jwt as jose_jwt

        raw = jose_jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])
        del raw["exp"]
        no_exp_token = jose_jwt.encode(raw, handler.secret_key, algorithm=handler.algorithm)
        assert handler.verify_token(no_exp_token) is None

    def test_verify_token_rejects_missing_sub(self) -> None:
        handler = JWTHandler()
        from jose import jwt as jose_jwt

        token = handler.create_access_token({"sub": "test", "tenant_id": 1})
        raw = jose_jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])
        del raw["sub"]
        no_sub_token = jose_jwt.encode(raw, handler.secret_key, algorithm=handler.algorithm)
        assert handler.verify_token(no_sub_token) is None

    def test_verify_token_rejects_missing_tenant_id(self) -> None:
        handler = JWTHandler()
        from jose import jwt as jose_jwt

        token = handler.create_access_token({"sub": "test", "tenant_id": 1})
        raw = jose_jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])
        del raw["tenant_id"]
        no_tenant_token = jose_jwt.encode(raw, handler.secret_key, algorithm=handler.algorithm)
        assert handler.verify_token(no_tenant_token) is None
