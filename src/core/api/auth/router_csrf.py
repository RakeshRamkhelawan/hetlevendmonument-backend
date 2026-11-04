# orphan:exempt reason: sub-router samengesteld door auth/router.py (ADR-033 Laag 1)
"""CSRF token endpoint."""

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger

from .dependencies import CSRF_TOKEN_EXPIRY, CSRF_TOKEN_PREFIX, get_redis_client

router = APIRouter(tags=["Authentication"])


@router.get("/csrf-token", status_code=status.HTTP_200_OK)
async def get_csrf_token(
    request: Request,
) -> dict[str, str | int]:
    """
    Generate a CSRF token for state-changing operations.

    SECURITY FIX (SEC-010): CSRF token handling for frontend API calls.
    Token is stored in Redis with expiry and must be included in request headers
    for state-changing operations (POST, PUT, PATCH, DELETE).
    """
    try:
        # Generate cryptographically secure CSRF token
        csrf_token = secrets.token_urlsafe(32)

        # Store in Redis with expiry
        redis_client = await get_redis_client()

        # Use IP + User-Agent as key component for additional binding
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")[:50]
        session_key = f"{CSRF_TOKEN_PREFIX}{client_ip}:{user_agent}:{csrf_token[:16]}"

        await redis_client.setex(session_key, CSRF_TOKEN_EXPIRY, csrf_token)

        logger.debug("CSRF token generated for %s", client_ip)
        return {"csrf_token": csrf_token, "expires_in": CSRF_TOKEN_EXPIRY}

    except Exception as e:
        logger.error("Error generating CSRF token: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSRF token",
        )
