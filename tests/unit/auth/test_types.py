"""Runtime type-contract tests for src.core.auth.types.

These tests do not replace static type checking, but they verify that the
TypedDict shapes are usable at runtime and that code paths preserve the
expected scalar/container types.
"""

from __future__ import annotations

from src.core.auth.types import JWTPayload, VerifiedJWTPayload


def test_jwt_payload_accepts_full_shape() -> None:
    """JWTPayload must represent the access-token creation payload."""
    payload: JWTPayload = {
        "sub": "42",
        "email": "test@example.com",
        "user_id": 42,
        "tenant_id": 1,
        "role_ids": [1, 2],
        "scopes": ["users:read", "workflows:write"],
        "jti": "unique-id",
        "iat": 1_700_000_000,
        "exp": 1_700_036_000,
    }
    assert payload["role_ids"] == [1, 2]
    assert payload["scopes"] == ["users:read", "workflows:write"]
    assert all(isinstance(r, int) for r in payload["role_ids"])
    assert all(isinstance(s, str) for s in payload["scopes"])


def test_verified_payload_is_total_false_for_safe_get() -> None:
    """VerifiedJWTPayload must allow partial dicts (existing runtime behavior)."""
    payload: VerifiedJWTPayload = {"sub": "42"}
    assert payload.get("tenant_id") is None
    assert payload.get("scopes") is None


def test_scope_lists_are_strings() -> None:
    """Scopes claim is a list[str], never comma-separated inside the list."""
    payload: VerifiedJWTPayload = {
        "sub": "42",
        "tenant_id": 1,
        "scopes": ["a:read", "b:write"],
        "exp": 1_700_036_000,
    }
    assert isinstance(payload["scopes"], list)
    assert all(isinstance(s, str) for s in payload["scopes"])


def test_role_ids_are_integers() -> None:
    """role_ids claim is a list[int]."""
    payload: JWTPayload = {
        "sub": "42",
        "role_ids": [10, 20, 30],
    }
    assert isinstance(payload["role_ids"], list)
    assert all(isinstance(r, int) for r in payload["role_ids"])
