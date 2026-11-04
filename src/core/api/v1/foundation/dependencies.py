"""Foundation Portal auth dependencies."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import NoReturn, cast

from loguru import logger
from src.core.typing import AsyncRedisClient

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.database import get_db
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.rate_limiter import (
    portal_public_read_limit,
    portal_public_write_limit,
    require_portal_auth_rate_limit,
    require_portal_magic_link_email_rate_limit,
    require_portal_newsletter_rate_limit,
    require_portal_takedown_rate_limit,
)
from src.core.governance.services.audit_service import AuditService
from src.core.models.foundation_content import (
    EducationalAccess,
    FoundationArchiveExport,
    PortalRole,
    PortalUser,
)
from src.core.models.rbac_models import Tenant
from src.core.services.edu_session_service import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    EduSessionData,
    EduSessionService,
    EduSessionStore,
    EduSessionStoreUnavailableError,
    InMemoryEduSessionStore,
    RedisEduSessionStore,
    hash_edu_code,
)
from src.core.exceptions.foundation import FoundationTenantDomainNotFoundError
from src.core.services.foundation_storage import (
    _MIME_TO_EXT,
    BestandOnleesbaarError,
    FoundationStorageNotConfiguredError,
    FoundationStorageService,
    detect_allowed_mime,
    secure_filename,
    verwijder_metadata,
)
from src.core.services.foundation_tenant_resolver import (
    invalidate_tenant_host_cache,
    normalize_host,
    public_tenant_scope,
    public_tenant_scope_by_host,
    resolve_tenant_by_domain,
    resolve_tenant_by_host,
    resolve_tenant_by_slug,
    zet_tenant_in_lopende_transactie,
)
from src.core.services.brevo_email_service import (
    BrevoEmailService,
    brevo_email_service,
)
from src.core.services.notification_service import notification_service
from src.core.services.stripe_service import (
    StripeNotConfiguredError,
    StripeService,
    StripeWebhookSecretMissingError,
    stripe_service,
)
from src.core.services.oai_pmh_service import (
    PAGE_SIZE,
    OaiPmhError,
    OaiPmhErrorCode,
    OaiPmhService,
    OaiRecord,
    OaiResumptionToken,
    validate_oai_parameters,
)
from src.core.services.foundation_archive_service import (
    TRIGGER_HANDMATIG,
    ArchiveExportError,
    ExportTenant,
    FoundationArchiveService,
)
from src.core.shared.datetime_utils import to_utc, utc_now
from src.core.utils.best_effort import best_effort

# JWT settings from the handler instance (lazy proxy, safe at import time)
_SECRET_KEY: str = jwt_handler.secret_key
_ALGORITHM: str = jwt_handler.algorithm

# Re-exported for content.py/admin/curatie.py/auth.py/newsletter.py/settings.py/takedown.py
# (ADR-033: router-laag mag niet direct database/governance/services importeren, alleen via
# deze Laag-2-facade -- backend-patterns.md #8).
from src.core.services.foundation_klas import klas_van_toegang, toegestane_les_ids
from src.core.services.foundation_leerlingantwoorden import (
    OngeldigAntwoord,
    hash_leerlingtoken,
    schoon_antwoorden,
    schoon_naam,
    verwijder_verlopen_antwoorden,
)
from src.core.services.foundation_lespdf import maak_les_pdf

__all__ = [
    "klas_van_toegang",
    "toegestane_les_ids",
    "OngeldigAntwoord",
    "hash_leerlingtoken",
    "schoon_antwoorden",
    "schoon_naam",
    "verwijder_verlopen_antwoorden",
    "maak_les_pdf",
    "zet_tenant_in_lopende_transactie",
    "get_db",
    "public_tenant_scope",
    "require_portal_user",
    "get_optional_portal_user",
    "require_curator",
    "require_admin",
    "portal_public_read_limit",
    "portal_public_write_limit",
    "require_portal_auth_rate_limit",
    "require_portal_magic_link_email_rate_limit",
    "require_portal_newsletter_rate_limit",
    "require_portal_takedown_rate_limit",
    "AuditService",
    # Archiefexport (BE-EP-054)
    "TRIGGER_HANDMATIG",
    "ArchiveExportError",
    "ExportTenant",
    "FoundationArchiveService",
    "utc_now",
    "best_effort",
    "FoundationArchiveExport",
    "PortalUser",
    "notification_service",
    "get_foundation_storage",
    "FoundationStorageService",
    "FoundationStorageNotConfiguredError",
    "detect_allowed_mime",
    "verwijder_metadata",
    "BestandOnleesbaarError",
    "secure_filename",
    "_MIME_TO_EXT",
    # Edu sessions (BE-EP-039)
    "EduSessionContext",
    "get_edu_session_service",
    "require_edu_session",
    "EduSessionService",
    "EduSessionData",
    "EduSessionStore",
    "InMemoryEduSessionStore",
    "RedisEduSessionStore",
    "EduSessionStoreUnavailableError",
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS",
    "hash_edu_code",
    # Tenant resolution (BE-EP-042)
    "Tenant",
    "get_public_tenant",
    "resolve_tenant_by_domain",
    "resolve_tenant_by_host",
    "normalize_host",
    "public_tenant_scope_by_host",
    "invalidate_tenant_host_cache",
    # Email service (ADR-033)
    "BrevoEmailService",
    "brevo_email_service",
    # Stripe service (ADR-033 / BE-SEC-058)
    "StripeNotConfiguredError",
    "StripeService",
    "StripeWebhookSecretMissingError",
    "stripe_service",
    # OAI-PMH service (ADR-033)
    "PAGE_SIZE",
    "OaiPmhError",
    "OaiPmhErrorCode",
    "OaiPmhService",
    "OaiRecord",
    "OaiResumptionToken",
    "validate_oai_parameters",
]


# ============================================================================
# JWT extraction (reusable)
# ============================================================================


async def _extract_authorization_token(authorization: str) -> str:
    """Extract Bearer token from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
        )
    return authorization[7:]


# ============================================================================
# Portal user dependency
# ============================================================================


async def require_portal_user(
    request: Request,
    authorization: str | None = Header(None, description="Bearer JWT token"),
    session: AsyncSession = Depends(get_db),
) -> PortalUser:
    """Validate JWT and return PortalUser.

    The JWT MUST contain an 'aud' claim with value 'portal'.
    The JWT 'scope' claim MUST be 'portal_uploader'.
    The JWT 'tenant_id' claim MUST match the request's resolved tenant.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    token = await _extract_authorization_token(authorization)

    try:
        # Cryptographic audience validation: only accept tokens with aud="portal"
        payload = jwt.decode(
            token,
            _SECRET_KEY,
            algorithms=[_ALGORITHM],
            audience="portal",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    # Scope validation (ADR-029: portal tokens must have scope="portal_uploader")
    token_scope = payload.get("scope")
    if token_scope != "portal_uploader":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token scope",
        )

    # Tenant isolation check
    token_tenant_id_raw = payload.get("tenant_id")
    if token_tenant_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing tenant claim",
        )
    try:
        token_tenant_id: int = int(token_tenant_id_raw)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant claim",
        )

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )
    try:
        user_id: int = int(user_id_raw)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject claim",
        )

    # Load user from DB with TenantFilterBypass because we explicitly filter
    # on tenant_id in the WHERE clause. Without bypass, the auto-filter hook
    # would inject WHERE FALSE when no tenant ContextVar is set (fail-secure).
    with TenantFilterBypass():
        result = await session.execute(
            select(PortalUser).where(
                PortalUser.id == user_id,
                PortalUser.tenant_id == token_tenant_id,
            )
        )
    user: PortalUser | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked",
        )

    # Store tenant_id on request state for downstream use
    request.state.tenant_id = token_tenant_id

    return user


# ============================================================================
# Optional portal user (public endpoints with optional auth)
# ============================================================================


async def get_optional_portal_user(
    request: Request,
    authorization: str | None = Header(None, description="Bearer JWT token"),
    session: AsyncSession = Depends(get_db),
) -> PortalUser | None:
    """Validate JWT if present, return None otherwise.

    Used by public endpoints that show different data based on auth status
    (e.g., community content visible only to authenticated users).
    """
    if not authorization:
        return None

    try:
        token = await _extract_authorization_token(authorization)
    except HTTPException:
        return None

    try:
        # Cryptographic audience validation: only accept tokens with aud="portal"
        payload = jwt.decode(
            token,
            _SECRET_KEY,
            algorithms=[_ALGORITHM],
            audience="portal",
        )
    except JWTError:
        return None

    # Scope validation (ADR-029: portal tokens must have scope="portal_uploader")
    token_scope = payload.get("scope")
    if token_scope != "portal_uploader":
        return None

    token_tenant_id_raw = payload.get("tenant_id")
    if token_tenant_id_raw is None:
        return None
    try:
        token_tenant_id = int(token_tenant_id_raw)
    except (ValueError, TypeError):
        return None

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        return None
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return None

    # Load user from DB with TenantFilterBypass because we explicitly filter
    # on tenant_id in the WHERE clause. Without bypass, the auto-filter hook
    # would inject WHERE FALSE when no tenant ContextVar is set (fail-secure).
    with TenantFilterBypass():
        result = await session.execute(
            select(PortalUser).where(
                PortalUser.id == user_id,
                PortalUser.tenant_id == token_tenant_id,
            )
        )
    user: PortalUser | None = result.scalar_one_or_none()
    if user is None or user.is_blocked:
        return None

    # Store tenant_id on request state for downstream use
    request.state.tenant_id = token_tenant_id
    return user


# ============================================================================
# Role-based dependencies
# ============================================================================


async def require_curator(
    user: PortalUser = Depends(require_portal_user),
) -> PortalUser:
    """Require admin or curator role."""
    if user.role not in (PortalRole.ADMIN, PortalRole.CURATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Curator or admin privileges required",
        )
    return user


async def require_admin(
    user: PortalUser = Depends(require_portal_user),
) -> PortalUser:
    """Require admin role."""
    if user.role != PortalRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


# ============================================================================
# Foundation storage dependency (BE-EP-036)
# ============================================================================

_foundation_storage: FoundationStorageService | None = None


def get_foundation_storage() -> FoundationStorageService:
    """FastAPI dependency: cached FoundationStorageService instance.

    Backend (local/azure) and upload cap come from get_settings() at first
    use (O4). Tests override this dependency to point storage at tmp_path.
    """
    global _foundation_storage
    if _foundation_storage is None:
        _foundation_storage = FoundationStorageService()
    return _foundation_storage


# ============================================================================
# Edu session dependencies (BE-EP-039)
# ============================================================================

# Uniform 401 detail for every edu-session failure (no reason leakage).
_EDU_SESSION_401_DETAIL = "Invalid or expired edu session"

# Expire-cookie header for 401 responses: when a session is unknown or fails
# DB revalidation, the client cookie is wiped in the same response (spec
# API-flow step 2/3). HTTPException(headers=...) is used because cookies set
# on the injected Response are dropped when an exception handler builds the
# response.
_EDU_COOKIE_EXPIRE_HEADER = {
    "set-cookie": (
        f"{SESSION_COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"
    )
}


@dataclass(frozen=True)
class EduSessionContext:
    """Validated edu session: opaque ID + freshly DB-revalidated access row.

    Role and validity come from the EducationalAccess row loaded during THIS
    request (spec O2) -- never from the session payload or cookie.
    """

    session_id: str
    access: EducationalAccess
    tenant: Tenant


async def _fail_edu_session(
    edu_sessions: EduSessionService, session_id: str
) -> NoReturn:
    """Invalidate the session server-side and raise a uniform 401.

    Best-effort delete: a store outage must not turn this 401 into a 500.
    """
    try:
        await edu_sessions.delete_session(session_id)
    except EduSessionStoreUnavailableError:
        pass
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_EDU_SESSION_401_DETAIL,
        headers=_EDU_COOKIE_EXPIRE_HEADER,
    )


_fallback_edu_store = InMemoryEduSessionStore()
_redis_offline_until: float = 0.0


async def get_edu_session_service() -> EduSessionService:
    """FastAPI dependency: Redis-backed EduSessionService with in-memory dev fallback.

    Uses Redis in production (fails with 503 if unreachable); falls back to
    InMemoryEduSessionStore in development and test environments when Redis is offline.
    """
    global _redis_offline_until
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    if not is_production:
        now = time.time()
        if now < _redis_offline_until:
            return EduSessionService(_fallback_edu_store)

    try:
        from src.core.database.redis import get_redis_client

        timeout = 2.0 if is_production else 0.25
        client = await asyncio.wait_for(get_redis_client(), timeout=timeout)
        if client is not None:
            await asyncio.wait_for(client.ping(), timeout=timeout)
            return EduSessionService(RedisEduSessionStore(cast(AsyncRedisClient, client)))
    except Exception as exc:
        if is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Edu session store unavailable",
            ) from exc
        logger.info(
            "Using InMemoryEduSessionStore fallback (Redis offline in %s mode)",
            os.getenv("ENVIRONMENT"),
        )
        _redis_offline_until = time.time() + 60.0
        return EduSessionService(_fallback_edu_store)

    if not is_production:
        return EduSessionService(_fallback_edu_store)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Edu session store unavailable",
    )


async def require_edu_session(
    request: Request,
    tenantSlug: str,
    session: AsyncSession = Depends(get_db),
    edu_sessions: EduSessionService = Depends(get_edu_session_service),
) -> EduSessionContext:
    """Validate the edu_session cookie and return a revalidated context.

    Steps (spec API-flow):
    1. Cookie present -> else uniform 401.
    2. Store lookup -> unknown/expired -> 401 + cookie wiped.
    3. DB revalidation of EducationalAccess (is_active, expires_at, tenant
       match) -> fail -> session deleted + 401 + cookie wiped.

    The store holds only {access_id, tenant_id} as a pointer; role and
    validity are read from the database on every request (audit P0-5).
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_EDU_SESSION_401_DETAIL,
        )

    try:
        data = await edu_sessions.get_session(session_id)
    except EduSessionStoreUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Edu session store unavailable",
        ) from exc

    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_EDU_SESSION_401_DETAIL,
            headers=_EDU_COOKIE_EXPIRE_HEADER,
        )

    tenant = await resolve_tenant_by_slug(tenantSlug, session)
    # RLS (ADR-036 OP-151): de opzoekquery hierboven opende de transactie zonder tenant, dus
    # onder de applicatierol zag de toegangsregel-query hieronder nul rijen en was ELKE
    # edu-sessie ongeldig. Alleen de transactie-instelling; de ContextVar blijft ongemoeid
    # (een dependency heeft geen opruimmoment), de endpoints zetten die via hun eigen scope.
    await zet_tenant_in_lopende_transactie(session, tenant.id)

    # Load the access row with TenantFilterBypass: we filter explicitly on
    # id + tenant_id; without bypass the auto-filter hook would inject
    # WHERE FALSE when no tenant ContextVar is set (fail-secure).
    with TenantFilterBypass():
        result = await session.execute(
            select(EducationalAccess).where(
                EducationalAccess.id == data.access_id,
                EducationalAccess.tenant_id == data.tenant_id,
            )
        )
    access: EducationalAccess | None = result.scalar_one_or_none()

    if access is None:
        await _fail_edu_session(edu_sessions, session_id)

    # Deactivation/expiry takes effect immediately, even within the 4-hour
    # TTL (spec O2).
    now = utc_now()
    expires_at = to_utc(access.expires_at)
    if (
        not access.is_active
        or data.tenant_id != tenant.id
        or (expires_at is not None and expires_at <= now)
    ):
        await _fail_edu_session(edu_sessions, session_id)

    return EduSessionContext(session_id=session_id, access=access, tenant=tenant)


# ============================================================================
# Tenant resolution dependency (BE-EP-042)
# ============================================================================


async def get_public_tenant(
    request: Request,
    slug: str | None = None,
    domain: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> Tenant:
    """Resolve active tenant from query params or HTTP Host / X-Forwarded-Host headers.

    Precedence:
    1. Query param ?slug=
    2. Query param ?domain=
    3. HTTP X-Forwarded-Host or Host header

    Raises:
        FoundationTenantSlugNotFoundError: If slug not found or inactive.
        FoundationTenantDomainNotFoundError: If domain/host not found or inactive.
    """
    redis_client: AsyncRedisClient | None = None
    try:
        from src.core.database.redis import get_redis_client

        redis_client = cast(AsyncRedisClient, await get_redis_client())
    except Exception:
        redis_client = None

    # Query param ?slug= takes highest precedence if provided
    slug_val = slug or request.query_params.get("slug")
    if slug_val:
        return await resolve_tenant_by_slug(slug_val, session, redis_client=redis_client)

    # Query param ?domain= takes second precedence
    domain_val = domain or request.query_params.get("domain")
    if domain_val:
        return await resolve_tenant_by_domain(domain_val, session, redis_client=redis_client)

    # Resolve by X-Tenant-Domain, Host, or X-Forwarded-Host header
    raw_host = (
        request.headers.get("x-tenant-domain")
        or request.headers.get("x-forwarded-host")
        or request.headers.get("host")
    )
    if not raw_host:
        raise FoundationTenantDomainNotFoundError("unknown")

    return await resolve_tenant_by_host(raw_host, session, redis_client=redis_client)
