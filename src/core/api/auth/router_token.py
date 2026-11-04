# orphan:exempt reason: sub-router samengesteld door auth/router.py (ADR-033 Laag 1)
"""Token introspection, refresh, revoke, and logout endpoints."""

import os
from collections.abc import Mapping
from typing import Annotated, Literal, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.schemas import (
    ErrorResponse,
    LogoutRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RevokeTokenRequest,
    RevokeTokenResponse,
    TokenValidationResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
    UserResponse,
)
from src.core.auth.api_deps import (
    jwt_handler,
    get_current_user,
    is_admin,
    VerifiedJWTPayload,
    weiger_portaaltoken,
)
from src.core.auth.account_status import is_portal_token
from src.core.auth.oauth2_service import oauth2_service
from src.core.auth.token_kind import TokenKind
from src.core.models.rbac_models import User
from .auth_config import auth_limiter
from .dependencies import (
    adopt_tenant,
    get_db,
    log_security_event,
    pre_auth_lookup,
    validate_csrf_token,
)

router = APIRouter(tags=["Authentication"])


def _houder_id(payload: VerifiedJWTPayload) -> int | None:
    """Het gebruikersnummer uit `sub`, of None als dat geen geheel getal is."""
    sub = str(payload.get("sub"))
    return int(sub) if sub.isascii() and sub.isdigit() else None


def _mag_token_intrekken(aanvrager: UserResponse, payload: VerifiedJWTPayload) -> bool:
    """Een token trek je in als het van JOU is, of als beheerder van DEZELFDE tenant.

    Tot 2026-10-14 mocht iedereen met een geldig token elk ander geldig token intrekken, ook dat
    van een collega of van een andere tenant (gemeten in
    `tests/integration/test_beveiligingsnazorg_tokens.py`). De tenant komt uit de getekende claim
    van het te weigeren token en wordt vergeleken met de tenant van de aanvrager uit zijn eigen
    sessie, nooit uit het verzoek.

    Ook de EIGENAAR moet in dezelfde tenant staan, en een portaaltoken is nooit van een medewerker:
    `sub` is dan een `portal_users`-nummer dat in dezelfde reeks ligt als `users.id` (Gate 2,
    security-reviewer 2026-10-15). Een `sub` die geen getal is, wordt geweigerd in plaats van een
    uitzondering te geven.
    """
    houder = _houder_id(payload)
    if houder is None or is_portal_token(cast(Mapping[str, object], payload)):
        return False
    if payload.get("tenant_id") != aanvrager.tenant_id:
        return False
    return houder == aanvrager.id or is_admin(aanvrager)


def _is_eigen_refresh_token(refresh_token: str, gebruiker: UserResponse) -> bool:
    """Is dit een geldig refresh-token van DEZE gebruiker? Een ander zijn token raak je niet aan."""
    try:
        payload = jwt_handler.verify_token(refresh_token, expected_kind=TokenKind.REFRESH)
    except (TypeError, ValueError):
        return False
    return payload is not None and str(payload.get("sub")) == str(gebruiker.id)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid refresh token"},
    },
    description="Refresh access token using refresh token",
)
@auth_limiter.limit("10/minute")
async def refresh_token(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RefreshTokenResponse:
    """
    Refresh an expired access token using a valid refresh token.

    The refresh token must be valid and not blacklisted.
    Sets a new access_token cookie and returns the token in the body.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        # Prefer refresh token from cookie when body is empty (browser session flow)
        refresh_token = data.refresh_token or request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token required",
            )

        # Use the oauth2_service to refresh the token
        result = await oauth2_service.refresh_access_token(refresh_token, db)

        if result is None:
            await log_security_event(
                event_type="TOKEN_REFRESH_FAILED",
                ip_address=client_ip,
                details={"reason": "invalid_or_expired_refresh_token"},
                threat_level="medium",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        # Log successful refresh
        await log_security_event(
            event_type="TOKEN_REFRESH_SUCCESS",
            ip_address=client_ip,
            details={"expires_in": result["expires_in"]},
            threat_level="low",
            db=db,
        )

        # Rotate access_token cookie
        is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        secure_flag = is_production or request.url.scheme == "https"
        samesite: Literal["lax", "strict"] = "strict" if is_production else "lax"

        response.set_cookie(
            key="access_token",
            value=result["access_token"],
            httponly=True,
            secure=secure_flag,
            samesite=samesite,
            max_age=int(result["expires_in"]),
            path="/",
        )

        return RefreshTokenResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            expires_in=int(result["expires_in"]),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token refresh error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh",
        )


@router.post(
    "/revoke",
    response_model=RevokeTokenResponse,
    responses={
        200: {
            "model": RevokeTokenResponse,
            "description": "Token revoked successfully",
        },
        401: {"model": ErrorResponse, "description": "Invalid token"},
    },
    description="Revoke a JWT token (logout)",
)
@auth_limiter.limit("10/minute")
async def revoke_token_endpoint(
    data: RevokeTokenRequest,
    request: Request,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> RevokeTokenResponse:
    """
    Revoke a JWT token by adding it to the blacklist.

    This endpoint allows users to logout by revoking their token.
    Once revoked, the token cannot be used for authentication.
    The token will be automatically removed from the blacklist when it expires.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        # Verify the token to be revoked is valid
        payload: VerifiedJWTPayload | None = jwt_handler.verify_token(data.token)
        if payload is None:
            await log_security_event(
                event_type="TOKEN_REVOCATION_FAILED",
                user_id=current_user.id,
                ip_address=client_ip,
                details={"reason": "invalid_token"},
                threat_level="medium",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        if not _mag_token_intrekken(current_user, payload):
            await log_security_event(
                event_type="TOKEN_REVOCATION_DENIED",
                user_id=current_user.id,
                ip_address=client_ip,
                details={"reason": "not_owner_or_tenant_admin"},
                threat_level="medium",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to revoke this token",
            )
        houder_id = _houder_id(payload)
        if houder_id is None:  # onbereikbaar na `_mag_token_intrekken`, maar typeert het resultaat
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        # Revoke the token using oauth2_service; de rij is van de houder, de intrekker staat apart.
        success = await oauth2_service.revoke_token(
            token=data.token,
            user_id=houder_id,
            db=db,
            reason="logout" if houder_id == current_user.id else "revoked_by_admin",
            revoked_by=current_user.id,
        )

        if not success:
            await log_security_event(
                event_type="TOKEN_REVOCATION_FAILED",
                user_id=current_user.id,
                ip_address=client_ip,
                details={"reason": "revocation_failed"},
                threat_level="medium",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to revoke token",
            )

        # Log successful revocation
        await log_security_event(
            event_type="TOKEN_REVOKED",
            user_id=current_user.id,
            ip_address=client_ip,
            details={"reason": "logout"},
            threat_level="low",
            db=db,
        )

        return RevokeTokenResponse(revoked=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token revocation error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token revocation",
        )


@router.get(
    "/validate",
    response_model=TokenValidationResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid token"},
    },
)
async def validate_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> TokenValidationResponse:
    """
    Validate a token and return its claims (token introspection).
    """
    try:
        # Verify token signature and expiration
        payload: VerifiedJWTPayload | None = jwt_handler.verify_token(token)
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        # Een portaaltoken is geen medewerker: `sub` is een portal_users-nummer (gemeten 2026-10-14).
        weiger_portaaltoken(payload)

        # Check if token is blacklisted (revoked)
        is_valid = await oauth2_service.is_token_valid(token, db)
        if not is_valid:
            logger.warning("Attempt to use revoked token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

        # Get user info
        user_id_val = payload.get("sub")
        if user_id_val is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )
        user_id = int(user_id_val)
        # Opzoeken via de aparte verbinding, daarna de klant AANNEMEN (OP-154 stap 2b).
        #
        # Hier stond `TenantFilterBypass`, met als onderbouwing dat `/api/v1/auth` in
        # `EXCLUDED_PREFIXES` van de tenant-middleware staat. **Die onderbouwing is onjuist
        # en is nagemeten**: er zijn twee zulke lijsten in de codebase en in geen van beide
        # staat een auth-pad. De UITKOMST klopte wel -- dit endpoint is publiek, en een
        # publiek verzoek zonder geldig token komt zonder klantcontext binnen
        # (`tenant_middleware.py:152-155`) -- maar het mechanisme was een ander.
        #
        # De omzeiling zelf hielp bovendien alleen zolang de applicatie als tabeleigenaar
        # verbindt: zij zet de ORM-hook uit, en PostgreSQL trekt zich daar niets van aan.
        # Onder `sanskritisetu_app` zou elk geldig token als "User not found" worden
        # afgewezen -- tokenvalidatie valt dan volledig stil.
        #
        # Er wordt alleen `id` en `tenant_id` gelezen; daarna wordt de klant aangenomen en
        # gebeurt de rest op de gewone sessie. De klant komt zo uit de DATABASE en niet uit
        # het token, ook al is dat token geverifieerd.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(
                    select(User.id, User.tenant_id).where(User.id == user_id)
                )
            ).one_or_none()

        if not gevonden:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        async with adopt_tenant(db, gevonden.tenant_id):
            user = (
                await db.execute(select(User).where(User.id == gevonden.id))
            ).scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Uitgeschakeld is uitgeschakeld: een uitgezet account is ook voor de sync-server en
        # voor introspectie geen geldige sessie.
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="ACCOUNT_DISABLED"
            )

        logger.info("Token validated for user %s", user_id)

        return TokenValidationResponse(
            active=True,
            scope=" ".join(payload.get("scopes", [])),
            username=user.email,
            token_type="Bearer",  # nosec B106 - OAuth2 standard token_type, not a credential
            exp=int(payload.get("exp", 0)),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token validation error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/verify-token",
    response_model=TokenVerifyResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid token"},
    },
)
@auth_limiter.limit("100/minute")
async def verify_token_endpoint(
    data: TokenVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenVerifyResponse:
    """
    Verify a token for sync-server authentication.

    Returns tenant_id and user_id for document isolation.
    This endpoint is specifically designed for the Hocuspocus sync-server.
    """
    try:
        # Verify token signature and expiration
        payload: VerifiedJWTPayload | None = jwt_handler.verify_token(data.token)
        if payload is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        # Een portaaltoken is geen medewerker: `sub` is een portal_users-nummer (gemeten 2026-10-14).
        weiger_portaaltoken(payload)

        # Check if token is blacklisted (revoked)
        is_valid = await oauth2_service.is_token_valid(data.token, db)
        if not is_valid:
            logger.warning("Attempt to use revoked token in verify-token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

        # Get user info
        user_id_val = payload.get("sub")
        if user_id_val is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )
        user_id = int(user_id_val)

        # Zelfde omzetting als bij `validate_token` hierboven (OP-154 stap 2b), inclusief
        # dezelfde correctie: de oude onderbouwing verwees naar `EXCLUDED_PREFIXES`, en
        # daarin staat geen enkel auth-pad. Zie daar voor de volledige redenering.
        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(
                    select(User.id, User.tenant_id).where(User.id == user_id)
                )
            ).one_or_none()

        if not gevonden:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        async with adopt_tenant(db, gevonden.tenant_id):
            user = (
                await db.execute(select(User).where(User.id == gevonden.id))
            ).scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Uitgeschakeld is uitgeschakeld: een uitgezet account is ook voor de sync-server en
        # voor introspectie geen geldige sessie.
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="ACCOUNT_DISABLED"
            )

        # Get tenant_id from user's roles or directly from user
        tenant_id = user.tenant_id if hasattr(user, "tenant_id") else None
        if tenant_id is None:
            # Try to get from payload as fallback
            tenant_id = payload.get("tenant_id")

        # SECURITY: Reject tokens without valid tenant_id
        if tenant_id is None or str(tenant_id) == "unknown":
            logger.warning("Token rejected: missing or invalid tenant_id for user %s", user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain valid tenant_id",
            )

        logger.info("Token verified for sync-server: user=%s, tenant=%s", user_id, tenant_id)

        return TokenVerifyResponse(
            valid=True,
            tenantId=str(tenant_id),
            userId=str(user_id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token verification error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Logged out successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Missing or invalid CSRF token"},
        500: {"description": "The session could not be closed; try again"},
    },
)
@auth_limiter.limit("20/minute")
async def logout_endpoint(
    request: Request,
    response: Response,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    data: LogoutRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, str]:
    """
    Logout endpoint for frontend compatibility.

    Revokes the access token AND the refresh token of the current session. Requires a valid CSRF
    token when cookie auth is active. Clears cookies on success.

    Mislukt het intrekken, dan volgt een 500 en blijven de cookies staan: de sessie is dan NIET
    gesloten, en dat mag de klant niet als "gelukt" lezen (beveiligingsnazorg 2026-10-14; hier
    stond een `return {"message": "Logged out successfully"}` na elke fout). Een herhaling is veilig:
    een al ingetrokken token telt als gelukt.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        # Get token from Authorization header or cookie
        token: str | None = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.cookies.get("access_token")

        # Het refresh-token eerst: faalt het intrekken daarna van het access-token, dan werkt
        # dat nog en kan de klant opnieuw uitloggen. Andersom is die herhaling een 401.
        refresh_token = (data.refresh_token if data else None) or request.cookies.get(
            "refresh_token"
        )
        if refresh_token and _is_eigen_refresh_token(refresh_token, current_user):
            if not await oauth2_service.revoke_token(
                refresh_token, current_user.id, db, expected_kind=TokenKind.REFRESH
            ):
                _meld_uitloggen_mislukt(current_user.id, "refresh")

        if token:
            # revoke_token() schrijft naar de PostgreSQL-tabel TokenBlacklist,
            # die is_jti_revoked() leest. De eerdere Redis-schrijfactie is
            # vervangen: twee stores gesynchroniseerd houden is hoe OP-188 is
            # ontstaan (gemeten 2026-09-30, commit 4baee486).
            if not await oauth2_service.revoke_token(token, current_user.id, db):
                _meld_uitloggen_mislukt(current_user.id, "access")

        logger.info("User %s logged out from %s", current_user.id, client_ip)

        # Clear any cookies -- must use same path/secure/samesite as set_cookie
        is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        secure_flag = is_production or request.url.scheme == "https"
        samesite: Literal["strict", "lax"] = "strict" if is_production else "lax"

        response.delete_cookie("access_token", path="/", secure=secure_flag, samesite=samesite)
        # Het huidige pad en het oude (voor 2026-10-14) pad: een sessie die eerder is gestart heeft
        # de cookie nog onder het oude pad staan.
        for refresh_pad in ("/api/v1/auth", "/api/v1/auth/refresh"):
            response.delete_cookie(
                "refresh_token", path=refresh_pad, secure=secure_flag, samesite=samesite
            )

        return {"message": "Logged out successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Logout error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed; the session was not closed. Try again.",
        ) from e


def _meld_uitloggen_mislukt(gebruiker_id: int, soort: str) -> NoReturn:
    logger.error(
        "token intrekking mislukt bij uitloggen voor gebruiker %s (%s-token)", gebruiker_id, soort
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Logout failed; the session was not closed. Try again.",
    )
