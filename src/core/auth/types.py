"""Shared type definitions for the auth layer.

These TypedDicts describe the JWT payload contract without introducing
runtime dependencies or circular imports. They can be imported freely by
both auth internals and consumers.
"""

from __future__ import annotations

from typing import TypedDict


class JWTPayload(TypedDict, total=False):
    """Payload used to create a JWT access token.

    All fields are optional because different callers may set different
    subsets during token creation. Use VerifiedJWTPayload for the stricter
    shape returned by token verification.
    """

    sub: str
    email: str
    user_id: int | str
    tenant_id: int
    role_ids: list[int]
    scopes: list[str]
    roles: list[str]
    role: str
    username: str
    fresh: bool
    type: str
    token_type: str
    jti: str
    iat: int
    exp: int


class VerifiedJWTPayload(JWTPayload, total=False):
    """Payload shape after successful token verification.

    This is intentionally still ``total=False`` so that call sites can use
    ``.get()`` and explicit runtime checks, matching the existing behavior.
    Type checkers will at least know the expected keys.

    Note: do not re-declare inherited keys. ``exp`` and ``tenant_id`` are
    already part of ``JWTPayload``.
    """
