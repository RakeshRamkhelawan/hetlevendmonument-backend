"""Backward-compatible auth bearer helpers.

This module preserves the historical import path and simplified async API used
by older tests and call sites while delegating to the current auth stack.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.auth as auth_package
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import oauth2_scheme
from src.core.auth.jwt_handler import jwt_handler
from src.core.auth.types import VerifiedJWTPayload


def _get_logger() -> logging.Logger:
    return logging.getLogger(__name__)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_email(payload: VerifiedJWTPayload) -> str | None:
    email = payload.get("email")
    if isinstance(email, str) and email:
        return email

    sub_value = payload.get("sub")
    if isinstance(sub_value, str) and "@" in sub_value:
        return sub_value

    user_id = payload.get("user_id")
    if isinstance(user_id, str):
        if user_id.startswith("user_"):
            return user_id[5:]
        if "@" in user_id:
            return user_id

    return None


async def get_current_user(token: str | None, db: AsyncSession) -> UserResponse:
    """Validate a bearer token and return the authenticated user.

    Historical contract:
    - positional signature is ``(token, db)``
    - invalid credentials always raise the same 401 error payload
    - token payloads may use ``sub`` or ``user_id`` to store the user email
      after canonical JWT verification succeeds
    """

    logger = _get_logger()

    # Short-circuit: token must be present before calling verify_token
    # jwt_handler.verify_token() expects str, not Optional[str]
    if token is None:
        raise _credentials_exception()

    try:
        payload = jwt_handler.verify_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise _credentials_exception() from exc

    if payload is None:
        logger.warning("Token verification returned no payload")
        raise _credentials_exception()

    email = _extract_email(payload)
    if not email:
        logger.warning("Token payload missing user email fields")
        raise _credentials_exception()

    user = await auth_package.auth_service.get_user_by_email(db, email)
    if not user:
        logger.warning("Authenticated user not found: %s", email)
        raise _credentials_exception()

    return user


__all__ = ["get_current_user", "oauth2_scheme"]
