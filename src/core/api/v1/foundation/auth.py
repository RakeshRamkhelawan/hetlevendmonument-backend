"""Foundation Portal magic-link authentication endpoints."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.datetime_utils import utc_now


from src.core.api.v1.foundation.dependencies import (
    AuditService,
    brevo_email_service,
    get_db,
    notification_service,
    public_tenant_scope,
    require_portal_auth_rate_limit,
    require_portal_magic_link_email_rate_limit,
)
from src.core.api.v1.foundation.schemas import (
    MagicLinkRequest,
    MagicLinkResponse,
    MagicLinkVerifyRequest,
    PasswordLoginRequest,
    QuickLoginRequest,
    TokenResponse,
)
from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import MagicLinkToken, PortalRole, PortalUser
from src.core.security.hcaptcha import require_hcaptcha
from src.core.shared.config import get_settings
from src.core.utils.best_effort import best_effort

router = APIRouter(prefix="/auth", tags=["foundation-auth"])


# Token expiry: 15 minutes
_MAGIC_LINK_EXPIRY_MINUTES = 15

# BE-SEC-055: quick-login is alleen toegestaan in expliciete dev/test-
# omgevingen. Blue/green-deploys zetten ENVIRONMENT=blue|green en staging
# zet ENVIRONMENT=staging; een exacte match op "production" was daar
# fail-open. Alles buiten deze allowlist -> 403.
_QUICK_LOGIN_ALLOWED_ENVIRONMENTS = frozenset(
    {"development", "dev", "local", "test", "testing"}
)


# BE-EP-056: alleen een adres dat op een e-mailadres lijkt, krijgt een account.
# Geen volledige RFC-controle: wie de link ontvangt, bewijst het adres.
_EMAIL_VORM = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _lijkt_op_email(email: str) -> bool:
    return bool(_EMAIL_VORM.match(email))


def _hash_token(token: str) -> str:
    """Hash a raw token with SHA-256 for secure storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_magic_token() -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(32)


@router.post(
    "/magic-link",
    response_model=MagicLinkResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request magic link",
)
async def request_magic_link(
    tenantSlug: str,
    request: Request,
    data: MagicLinkRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    _check_ip: None = Depends(require_portal_auth_rate_limit),
) -> dict[str, object]:
    """Request a magic link via email.

    - Generates cryptographically secure token
    - Stores SHA-256 hash in DB with 15-min expiry
    - Sends email via NotificationService (best_effort)
    - Rate limit: 5 per IP per minute, 3 per email per hour
    - Returns ALWAYS generic message (no email enumeration)

    SECURITY NOTE: The magic link token is placed in the URL query parameter
    so the email link is clickable. This exposes the token to browser history,
    server access logs, and referrer headers (OWASP, CWE-598). Mitigations:
    - 15-minute TTL (short window)
    - SHA-256 hash storage (raw token never persisted)
    - Atomic one-time use (UPDATE WHERE used_at IS NULL)
    - Frontend MUST strip the token from URL immediately after reading it
      (history.replaceState) to minimise browser-history exposure.
    Future improvement: encrypted token in URL + frontend POST flow.
    """
    # Store parsed email for rate limiter key_func
    request.state.parsed_email = data.email

    # Verify hCaptcha bot protection (ADR-029 P1-3)
    client_ip = request.client.host if request.client else None
    await require_hcaptcha(data.hcaptcha_token, remote_ip=client_ip)

    # Email-based rate limit (inline because parsed_email is only available here)
    await require_portal_magic_link_email_rate_limit(request)

    email = data.email.strip().lower()

    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Check if user exists (but don't reveal this)
        stmt = select(PortalUser).where(
            PortalUser.tenant_id == tenant.id,
            func.lower(PortalUser.email) == email,
        )
        result = await session.execute(stmt)
        user: PortalUser | None = result.scalar_one_or_none()

        # BE-EP-056: aanmelden via de inloglink (ADR-029 eis 4: lage drempel
        # voor uploaders, geen wachtwoord). Alleen voor een ONBEKEND adres en
        # altijd met de laagste rol; een bestaand account houdt zijn rol.
        # Het account is pas geverifieerd als de link is gebruikt (verify).
        # hCaptcha en de rate limits hierboven gelden ook voor deze route.
        if user is None and data.aanmelden and _lijkt_op_email(email):
            nieuw = PortalUser(
                tenant_id=tenant.id,
                email=email,
                role=PortalRole.VISITOR,
                is_verified=False,
                email_verified=False,
            )
            try:
                async with session.begin_nested():
                    session.add(nieuw)
                    await session.flush()
                user = nieuw
            except IntegrityError:
                # Gelijktijdige aanvraag voor hetzelfde adres: dat account bestaat nu.
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()

        if user is not None:
            # Generate token
            raw_token = _generate_magic_token()
            token_hash = _hash_token(raw_token)
            expires_at = utc_now() + timedelta(minutes=_MAGIC_LINK_EXPIRY_MINUTES)

            # Create magic link token for existing user
            magic_link = MagicLinkToken(
                tenant_id=tenant.id,
                portal_user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            session.add(magic_link)
            await session.flush()

            # Send email via NotificationService (best_effort)
            settings = get_settings()
            base_url = settings.foundation_portal_base_url.rstrip("/")
            # SECURITY: token in URL is necessary for clickable email links.
            # See docstring for mitigations. Token is 32 bytes URL-safe random,
            # 15-minute TTL, one-time use. Frontend must strip from URL.
            magic_link_url = (
                f"{base_url}/inloggen?token={raw_token}&tenant={tenantSlug}"
            )
            async with best_effort("magic_link_email"):
                await brevo_email_service.send_magic_link(
                    to_email=data.email,
                    magic_link_url=magic_link_url,
                    expires_in_minutes=_MAGIC_LINK_EXPIRY_MINUTES,
                    tenant_name=getattr(tenant, "name", None),
                )
                await notification_service.notify_user(
                    user_id=str(user.id),
                    title="Je magische login-link",
                    message=f"Klik hier om in te loggen: {magic_link_url}",
                )
        # else: user doesn't exist - return generic message without storing token

        # In development: return dev magic link for easy local testing
        env = os.getenv("ENVIRONMENT", "").lower()
        is_dev = env in ("development", "dev", "local")
        if is_dev and user is not None:
            logger.info("=== DEV MAGIC LINK FOR %s ===\n%s\n========================================", data.email, magic_link_url)
            return {
                "message": "If the email exists, a login link has been sent.",
                "dev_magic_link_url": magic_link_url,
                "dev_token": raw_token,
            }

        # Always return generic message
        return {"message": "If the email exists, a login link has been sent."}


@router.get(
    "/magic-link/verify",
    summary="Verify magic link redirect (browser fallback)",
)
async def verify_magic_link_redirect(
    tenantSlug: str,
    token: str = Query(..., min_length=16, max_length=128),
) -> RedirectResponse:
    """Redirect browser GET requests on magic link to frontend login page."""
    settings = get_settings()
    base_url = settings.foundation_portal_base_url.rstrip("/")
    redirect_url = f"{base_url}/inloggen?token={token}&tenant={tenantSlug}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post(
    "/magic-link/verify",
    response_model=TokenResponse,
    summary="Verify magic link",
)
async def verify_magic_link(
    tenantSlug: str,
    request: Request,
    data: MagicLinkVerifyRequest | None = Body(default=None),
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _check_ip: None = Depends(require_portal_auth_rate_limit),
) -> dict[str, object]:
    """Verify a magic link token and return a JWT.

    - Validates token hash against DB
    - Checks expiry (token.expires_at > NOW())
    - Checks replay via atomic UPDATE WHERE used_at IS NULL
    - Updates user in same transaction as JWT creation
    - Returns JWT access token with aud='portal' + scope='portal_uploader'
    """
    raw_token = data.token if (data and data.token) else token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Token is required",
        )

    async with public_tenant_scope(tenantSlug, session) as tenant:
        token_hash = _hash_token(raw_token)

        # Find token (with FOR UPDATE to prevent race conditions)
        stmt = (
            select(MagicLinkToken)
            .where(
                MagicLinkToken.tenant_id == tenant.id,
                MagicLinkToken.token_hash == token_hash,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        magic_link: MagicLinkToken | None = result.scalar_one_or_none()

        if magic_link is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        # Check expiry
        now = utc_now()
        if magic_link.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        # Atomic replay protection: UPDATE only if used_at IS NULL
        update_result = await session.execute(
            update(MagicLinkToken)
            .where(
                MagicLinkToken.id == magic_link.id,
                MagicLinkToken.used_at.is_(None),
            )
            .values(used_at=now)
            .returning(MagicLinkToken.id)
        )
        updated_id = update_result.scalar_one_or_none()
        if updated_id is None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token already used",
            )

        # Load user
        stmt_user = select(PortalUser).where(
            PortalUser.id == magic_link.portal_user_id,
            PortalUser.tenant_id == tenant.id,
        )
        result_user = await session.execute(stmt_user)
        user: PortalUser | None = result_user.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if user.is_blocked:
            # Audit log for blocked user attempting login (best-effort, never blocks response)
            async with best_effort("audit_blocked_user_login_attempt", db_session=session):
                await AuditService.log_event(
                    db=session,
                    event_type="portal_login_blocked",
                    severity="medium",
                    source_ip=request.client.host if request.client else "unknown",
                    endpoint=f"/{tenantSlug}/foundation/auth/magic-link/verify",
                    description="Blocked user attempted magic link login",
                    user_id=None,
                    tenant_id=tenant.id,
                    action="magic_link_verify_blocked",
                    resource=f"portal_user:{user.id}",
                    metadata={
                        "method": "magic_link",
                        "email": user.email,
                        "portal_user_id": user.id,
                        "reason": "user_is_blocked",
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is blocked",
            )

        # Update user (same transaction)
        user.last_login_at = now
        user.email_verified = True
        # BE-EP-056: wie de link gebruikt, heeft het adres bewezen.
        user.is_verified = True

        await session.flush()

        role_val = user.role.value if hasattr(user.role, "value") else str(user.role).lower()
        sec_level = "admin" if role_val == "admin" else ("authorized" if role_val == "curator" else "authenticated")
        jwt_data: dict[str, object] = {
            "sub": str(user.id),
            "user_id": user.id,
            "email": user.email,
            "tenant_id": tenant.id,
            "aud": "portal",
            "scope": "portal_uploader",
            "role": role_val,
            "security_level": sec_level,
        }
        access_token = jwt_handler.create_access_token(data=jwt_data)

        # Audit log (best-effort, never blocks login)
        async with best_effort("audit_magic_link_verify", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="portal_login",
                severity="low",
                source_ip=request.client.host if request.client else "unknown",
                endpoint=f"/{tenantSlug}/foundation/auth/magic-link/verify",
                description="Magic link login successful",
                user_id=None,
                tenant_id=tenant.id,
                action="magic_link_verify",
                resource=f"portal_user:{user.id}",
                metadata={"method": "magic_link", "email": user.email, "portal_user_id": user.id},
            )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"email": user.email, "role": user.role.value},
        }


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Password-based login for staff with a core account",
)
async def login_with_password(
    tenantSlug: str,
    request: Request,
    data: PasswordLoginRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    _check_ip: None = Depends(require_portal_auth_rate_limit),
) -> dict[str, object]:
    """Authenticate with email and password against a core User account.

    BE-SEC-054 (markt-review 2026-09-24, HIGH): twee privilege-escalatie-
    deuren verwijderd:
    - geen hardcoded fallback meer die username "admin" (of elke string zonder
      "@") mapt op admin@levendmonument.nl; de username wordt letterlijk als
      email opgezocht.
    - auto-provisioning van een PortalUser bij eerste login gebeurt met de
      LAAGSTE rol (PortalRole.VISITOR), nooit ADMIN. Admin/curator-rollen
      worden uitsluitend toegekend via expliciete seeding
      (scripts/seed_portal_users.py) of de curator-flow, conform OWASP
      Authorization Cheat Sheet (least privilege, deny by default).
    """
    raw_user = data.username.strip()

    async with public_tenant_scope(tenantSlug, session) as tenant:
        from src.core.models.rbac_models import User
        user_stmt = select(User).where(
            User.tenant_id == tenant.id,
            User.email == raw_user,
        )
        user_res = await session.execute(user_stmt)
        core_user = user_res.scalars().first()

        if not core_user or not core_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ongeldige gebruikersnaam of wachtwoord.",
            )

        is_valid = await jwt_handler.verify_password(data.password, core_user.hashed_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ongeldige gebruikersnaam of wachtwoord.",
            )

        pu_stmt = select(PortalUser).where(
            PortalUser.tenant_id == tenant.id,
            PortalUser.email == core_user.email,
        )
        pu_res = await session.execute(pu_stmt)
        portal_user = pu_res.scalars().first()

        if not portal_user:
            portal_user = PortalUser(
                tenant_id=tenant.id,
                email=core_user.email,
                display_name=raw_user,
                role=PortalRole.VISITOR,
                is_verified=True,
                email_verified=True,
                consent_given=True,
                consent_given_at=utc_now(),
            )
            session.add(portal_user)
            await session.flush()

        role_val = (
            portal_user.role.value
            if hasattr(portal_user.role, "value")
            else str(portal_user.role).lower()
        )
        sec_level = "admin" if role_val == "admin" else ("authorized" if role_val == "curator" else "authenticated")
        jwt_data = {
            "sub": str(portal_user.id),
            "user_id": portal_user.id,
            "email": portal_user.email,
            "tenant_id": tenant.id,
            "aud": "portal",
            "scope": "portal_uploader",
            "role": role_val,
            "security_level": sec_level,
        }
        access_token = jwt_handler.create_access_token(data=jwt_data)

        async with best_effort("audit_password_login", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="portal_password_login",
                severity="low",
                source_ip=request.client.host if request.client else "unknown",
                endpoint=f"/{tenantSlug}/foundation/auth/login",
                description="Password login successful",
                user_id=None,
                tenant_id=tenant.id,
                action="password_login",
                resource=f"portal_user:{portal_user.id}",
                metadata={"method": "password", "email": portal_user.email, "portal_user_id": portal_user.id},
            )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"email": portal_user.email, "role": role_val},
        }


@router.post(
    "/quick-login",
    response_model=TokenResponse,
    summary="Development quick login for testing (bypasses email delivery)",
)
async def quick_login(
    tenantSlug: str,
    request: Request,
    data: QuickLoginRequest = Body(...),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Instant login endpoint for automated tests and development UI.

    Only enabled in explicit dev/test environments (allowlist); every other
    ENVIRONMENT value -- including blue/green/staging -- returns 403.
    Directly returns a valid JWT access token for the requested role.

    BE-SEC-054: een BESTAANDE PortalUser wordt nooit van rol veranderd --
    quick-login is geen promotie-pad naar admin. De gevraagde rol geldt
    alleen bij eerste aanmaak van het vaste dev-account.
    """
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment not in _QUICK_LOGIN_ALLOWED_ENVIRONMENTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quick login is only available in development/test environments.",
        )

    # BE-SEC-056: default is visitor (least privilege); alleen een expliciete
    # rol "admin"/"curator" mint die rol, en alleen binnen de omgevingsallowlist.
    role_str = (data.role or "visitor").lower()
    if role_str == "admin":
        email = "admin@levendmonument.nl"
        portal_role = PortalRole.ADMIN
    elif role_str == "curator":
        email = "curator@levendmonument.nl"
        portal_role = PortalRole.CURATOR
    else:
        role_str = "visitor"
        email = "bezoeker@levendmonument.nl"
        portal_role = PortalRole.VISITOR

    async with public_tenant_scope(tenantSlug, session) as tenant:
        pu_stmt = select(PortalUser).where(
            PortalUser.tenant_id == tenant.id,
            PortalUser.email == email,
        )
        pu_res = await session.execute(pu_stmt)
        portal_user = pu_res.scalars().first()

        if not portal_user:
            portal_user = PortalUser(
                tenant_id=tenant.id,
                email=email,
                display_name=role_str.capitalize(),
                role=portal_role,
                is_verified=True,
                email_verified=True,
                consent_given=True,
                consent_given_at=utc_now(),
            )
            session.add(portal_user)
            await session.flush()
        # BE-SEC-054: geen else-tak die de rol van een bestaande gebruiker
        # overschrijft. De rol in het token is altijd de opgeslagen rol.

        role_val = (
            portal_user.role.value
            if hasattr(portal_user.role, "value")
            else str(portal_user.role).lower()
        )
        sec_level = "admin" if role_val == "admin" else ("authorized" if role_val == "curator" else "authenticated")
        jwt_data = {
            "sub": str(portal_user.id),
            "user_id": portal_user.id,
            "email": portal_user.email,
            "tenant_id": tenant.id,
            "aud": "portal",
            "scope": "portal_uploader",
            "role": role_val,
            "security_level": sec_level,
        }
        access_token = jwt_handler.create_access_token(
            data=jwt_data,
            expires_delta=timedelta(hours=24),
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"email": portal_user.email, "role": role_val},
        }


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout",
)
async def logout() -> None:
    """Logout portal user.

    JWT is stateless; client-side deletion is sufficient.
    Server-side has no session to invalidate.
    """
    logger.debug("Portal user logout acknowledged (204 No Content)")
    return None
