"""Auth API dependencies (ADR-033 Laag 1) -- re-exports for auth/router.py."""

import hmac

from fastapi import HTTPException, Request, status
from loguru import logger

from src.core.database.database import get_async_session as get_async_session, get_db as get_db  # noqa: F401
from src.core.database.redis import get_redis_client as get_redis_client  # noqa: F401
from src.core.database.tenant_query_filter import TenantFilterBypass as TenantFilterBypass  # noqa: F401

# ADR-036 OP-154 stap 2. Via deze facade en niet rechtstreeks uit `src.core.database`:
# ADR-033 verbiedt een router een directe database-import, en `TenantFilterBypass` gaat
# hier al zo. `pre_auth_lookup` vervangt op termijn elk kaal `TenantFilterBypass`-blok op
# het authenticatiepad; `adopt_tenant` is wat daarna de tenant vaststelt.
from src.core.database.bypass_session import adopt_tenant as adopt_tenant  # noqa: F401
from src.core.database.bypass_session import pre_auth_lookup as pre_auth_lookup  # noqa: F401
from src.core.governance.services.audit_service import (
    SecurityEvent as SecurityEvent,
    log_security_event as log_security_event,
)  # noqa: F401
from src.core.services.email import (  # noqa: F401
    bouw_uitnodiging as bouw_uitnodiging,
    get_email_service as get_email_service,
    send_password_reset_email as send_password_reset_email,
)
from src.core.services.rbac_service import RBACService as RBACService  # noqa: F401

CSRF_TOKEN_EXPIRY = 3600
CSRF_TOKEN_PREFIX = "csrf:"


async def validate_csrf_token(request: Request) -> None:
    """Validate the X-CSRF-Token header against the Redis-backed store.

    Raises HTTPException 403 if the token is missing, malformed, or invalid.
    """
    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF token",
        )

    # NOTE: the token is bound to client_ip + User-Agent (not the session id). A
    # client whose egress IP changes mid-session (mobile roaming, NAT, VPN) will get
    # a 403 and must re-fetch the token via GET /api/v1/auth/csrf-token. This fails
    # closed (availability/UX cost, not a bypass) and is an accepted trade-off
    # alongside the Redis-availability coupling.
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")[:50]
    prefix = csrf_token[:16]
    session_key = f"{CSRF_TOKEN_PREFIX}{client_ip}:{user_agent}:{prefix}"

    try:
        redis_client = await get_redis_client()
        stored_token = await redis_client.get(session_key)
    except Exception as e:
        logger.error("csrf_validation_redis_error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CSRF validation temporarily unavailable",
        )

    # Constant-time compare to avoid a token-timing side-channel.
    if not stored_token or not hmac.compare_digest(str(stored_token), csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired CSRF token",
        )
