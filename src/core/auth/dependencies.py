import logging
from typing import Annotated, Optional, cast
from collections.abc import Awaitable, Callable, Mapping

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.account_status import is_portal_token
from src.core.auth.auth_service import UserResponse, auth_service
from src.core.auth.jwt_handler import jwt_handler
from src.core.auth.rbac import Permission
from src.core.auth.types import VerifiedJWTPayload
from src.core.auth.token_extraction import extract_bearer_token, extract_http_token
from src.core.database.database import get_db
from src.core.database.database import get_db as get_db_session
from src.core.middleware.tenant_context import get_tenant_id, require_tenant_id
from src.core.models.rbac_models import User
from src.core.services.rbac_service import RBACService
from src.core.shared.production_logging import SafeLogger

__all__ = [
    "UserResponse",
    "get_db",
    "get_token_from_request",
    "get_token_from_header_or_cookie",
    "get_current_user",
    "get_current_user_ws",
    "get_current_user_dependency",
    "get_optional_user_dependency",
    "get_current_user_id",
    "require_permission",
    "require_permission_with_tenant_bypass",
    "ADMIN_ROLE_NAMES",
    "is_admin",
    "is_tenant_admin",
    "require_admin",
    "CurrentUser",
    "RequireAdmin",
]

logger = SafeLogger(__name__)
security_scheme = HTTPBearer(auto_error=False)
security = security_scheme  # Alias for backward compatibility
# OAuth2PasswordBearer scheme for extraction from form data (legacy support)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
# NOTE: get_async_session is imported from database module and is deprecated.
# Use get_db() for all new FastAPI dependency injection.


def _credentials_exception() -> HTTPException:
    """Return the legacy 401 used across older auth tests and endpoints."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    """
    Canonical HTTP token extraction:
    1. Authorization header (Bearer token)
    2. Cookie (access_token)
    """
    token = extract_http_token(
        authorization=request.headers.get("authorization"),
        access_token_cookie=request.cookies.get("access_token"),
        credentials_token=credentials.credentials if credentials else None,
    )
    if token:
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Backward compatibility alias
get_token_from_header_or_cookie = get_token_from_request


async def _http_dependency_token() -> str | None:
    """Prevent FastAPI from binding HTTP query parameters into auth dependencies."""
    sentinel_token: str | None = None
    return sentinel_token


async def _weiger_als_ingetrokken(payload: VerifiedJWTPayload, db: AsyncSession) -> None:
    """Weiger een token zonder jti, of met een jti die op de blacklist staat (OP-188/OP-260).

    Tot 2026-09-15 werd de blacklist op het verzoekpad NOOIT gelezen. Uitloggen maakte een
    access-token niet ongeldig, en tijdens een incident was er geen knop om een
    gecompromitteerd token te doden -- het bleef geldig tot het verliep (default 60
    minuten). Het mechanisme LEEK te bestaan, want de refresh-flow controleert de blacklist
    wel (`oauth2_service.py:210`), en dat is precies waarom dit zo lang onopgemerkt bleef.

    **Waarom dit een eigen functie is en geen stuk code in `_get_user_from_token` (OP-260).**
    Die functie was tot 2026-09-19 de ENIGE plek met deze controle, en de toelichting daar
    beweerde dat het ook het enige knooppunt was "waar authenticatie wordt beslist EN waar
    zowel het token als een databasesessie beschikbaar is". Dat was onwaar:
    `get_current_user_id` voldoet aan diezelfde beschrijving en hing onder twaalf
    rbac-endpoints -- juist die waarmee rollen en rechten worden uitgedeeld. Gemeten
    end-to-end tegen een echte app en database: een INGETROKKEN token gaf daar nog gewoon
    200. Een gekopieerde controle zou hetzelfde opnieuw laten gebeuren bij de volgende
    ingang; een gedeelde functie is een deur die je maar op een plek hoeft te bewaken.

    Bewust NIET in `tenant_middleware`: die draait ook op paden zonder databasesessie en
    leidt alleen de tenant af.
    """
    jti = payload.get("jti")
    if not jti:
        # Fail-secure. `create_access_token` (`jwt_handler.py:148-149`) zet altijd een jti
        # en elke uitgifteplek loopt via die functie, dus een token zonder jti kan uit deze
        # codebase niet ontstaan. Wel doorlaten zou een tokensoort opleveren die per
        # definitie onintrekbaar is.
        logger.warning("Token zonder jti geweigerd: intrekken zou onmogelijk zijn")
        raise _credentials_exception()

    from src.core.auth.oauth2_service import oauth2_service

    if await oauth2_service.is_jti_revoked(str(jti), db):
        logger.info("Ingetrokken token geweigerd (jti=%s)", str(jti)[:8])
        raise _credentials_exception()

    # Een token van voor een "alle sessies"-intrekking (nieuw wachtwoord, reset of wijziging) geldt niet meer.
    # Deze ene functie dekt HTTP en WebSocket; een tweede plek zou hetzelfde gat opnieuw openen.
    sub = payload.get("sub")
    if isinstance(sub, str) and sub.isdigit():
        if await oauth2_service.is_uitgegeven_voor_intrekking(int(sub), payload.get("iat"), db):
            logger.info("Token van voor een intrekking van alle sessies geweigerd (user=%s)", sub)
            raise _credentials_exception()


def _weiger_portaaltoken(payload: VerifiedJWTPayload) -> None:
    """Een portaaltoken (`aud == "portal"`) is geen medewerker: weiger het met 401.

    Gemeten 2026-10-13 (Gate 2, security-reviewer): een portaaltoken werd hier opgezocht in `users`,
    via de e-mailclaim of via `sub` als gebruikersnummer (`get_user_by_id` haalt de tenant uit de
    GEVONDEN rij, niet uit het token). Daarmee werd een portaalgebruiker een medewerker, ook van
    een andere tenant, op elke route met `get_current_user`, `get_current_user_ws` en
    `get_current_user_id`. Portaalroutes gebruiken `require_portal_user` (Foundation) en komen hier niet.
    """
    if is_portal_token(cast(Mapping[str, object], payload)):
        logger.info("Portaaltoken geweigerd op een medewerkersingang")
        raise _credentials_exception()


def _weiger_als_uitgeschakeld(is_active: bool, user_id: int) -> None:
    """UITGESCHAKELD IS UITGESCHAKELD: weiger een uitgezet account met 401 `ACCOUNT_DISABLED`.

    Een token blijft cryptografisch geldig tot het verliep en zegt niets over de toestand van
    het account. Gemeten 2026-10-12: zonder deze controle las, schreef en ververste een
    uitgezette gebruiker gewoon door. Gedeeld door `_get_user_from_token` en door
    `get_current_user_id` (waar alle rechtencontroles aan hangen), zodat een nieuwe ingang
    deze deur niet opnieuw hoeft uit te vinden.
    """
    if is_active:
        return
    logger.info("Uitgeschakeld account geweigerd (user_id=%s)", user_id)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ACCOUNT_DISABLED",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_user_from_token(token: str, db: AsyncSession) -> UserResponse:
    """Core logic to validate token and return UserResponse."""
    try:
        payload: VerifiedJWTPayload | None = jwt_handler.verify_token(token)
    except (TypeError, ValueError):
        raise _credentials_exception()

    # If verify_token returned None (invalid token or missing required claims)
    if payload is None:
        raise _credentials_exception()

    # INGETROKKEN? (ADR-036 OP-188/OP-260) -- zie `_weiger_als_ingetrokken`.
    await _weiger_als_ingetrokken(payload, db)
    _weiger_portaaltoken(payload)

    # Extract user identifier (try user_id first, then email, then sub)
    email: str | None = payload.get("email")
    if not email:
        sub_value = payload.get("sub")
        if sub_value and isinstance(sub_value, str) and "@" in sub_value:
            email = sub_value

    if not email:
        user_id_val = payload.get("user_id")
        if isinstance(user_id_val, str) and user_id_val.startswith("user_"):
            email = user_id_val[5:]

    if not email:
        # Check if sub is user_id (int or string digit)
        sub_val = payload.get("sub")
        if sub_val and (
            isinstance(sub_val, int) or (isinstance(sub_val, str) and sub_val.isdigit())
        ):
            user = await auth_service.get_user_by_id(db, user_id=int(sub_val))
        else:
            raise _credentials_exception()
    else:
        user = await auth_service.get_user_by_email(db, email=email)

    if not user:
        raise _credentials_exception()

    _weiger_als_uitgeschakeld(user.is_active, user.id)

    return user


async def get_current_user(
    request: Request = None,  # type: ignore[assignment]  # FastAPI injects Request; None signals token-only path
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(_http_dependency_token),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> UserResponse:
    """
    CANONICAL get_current_user implementation.
    All endpoints should use THIS dependency.

    Features:
    - Auth via Authorization-header, access_token-cookie of HTTPBearer-credentials.
      NB: geen query-parameter -- zie get_token_from_request. De eerdere tekst
      "Triple-Lock auth (header/cookie/query)" was verouderd en beschreef geen
      werkend pad (nagetrokken 2026-07-31, SEC-AGT-004-vervolg).
    - Case-insensitive Bearer check
    - Database validation (handles deleted/locked users)
    - Returns consistent UserResponse model
    """
    auth_token = token
    if auth_token is None:
        if request is None:
            raise _credentials_exception()
        auth_token = await get_token_from_request(request, credentials)

    return await _get_user_from_token(auth_token, db)


async def get_current_user_ws(
    websocket: WebSocket, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    WebSocket version of get_current_user.
    Extracts the token from the access_token cookie (canonical) or the
    Authorization header.

    SEC-AGT-004: het ``?token=``-pad is hier verwijderd (2026-07-31). Het stond nog
    open als "transitional compatibility" terwijl WebSocketAuthenticator het al
    weigerde -- daarmee was de hardening omzeilbaar via deze dependency. OWASP ASVS V7
    verbiedt sessie-identifiers in query strings: ze lekken in access logs,
    browsergeschiedenis, proxy logs en de Referer-header. Afgedwongen door
    tests/architecture/test_websocket_no_query_param_token.py.
    """
    # Method 1: Cookie (canonical for Phase 6)
    token = websocket.cookies.get("access_token")

    # Method 2: Authorization header
    if not token:
        token = extract_bearer_token(websocket.headers.get("authorization"))

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return await _get_user_from_token(token, db)


async def get_current_user_dependency(
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(_http_dependency_token),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> UserResponse:
    """FastAPI Dependency wrapper for get_current_user."""
    return await get_current_user(
        request=request,
        db=db,
        token=token,
        credentials=credentials,
    )


async def get_optional_user_dependency(
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(_http_dependency_token),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> UserResponse | None:
    """
    Optional user dependency - returns None instead of 401 if no valid token.
    Useful for endpoints that can work both authenticated and anonymously.
    """
    try:
        return await get_current_user(
            db=db,
            token=token,
            request=request,
            credentials=credentials,
        )
    except HTTPException:
        return None
    except Exception:
        return None


async def get_current_user_id(
    token: str = Depends(get_token_from_request),
    session: AsyncSession = Depends(get_db_session),
) -> int:
    """
    Validate JWT token and return user ID.

    Validates:
    1. Handtekening en algoritme, via `jwt_handler.verify_token()` (HS256;
       `config.jwt_secret_key` wordt hier NIET
       gelezen -- die bewering stond hier tot 2026-09-18 en klopte niet meer)
    2. Verlooptijd (`exp`), plus de verplichte claims `sub` en `tenant_id`
    3. Bestaan van de gebruiker in de database

    4. Intrekking: een token waarvan de `jti` op de blacklist staat wordt geweigerd,
       net als op het `get_current_user`-pad (ADR-036 OP-260, gesloten 2026-09-19).

    Returns:
        int: The authenticated user's ID
    """
    payload: VerifiedJWTPayload | None = jwt_handler.verify_token(token)

    try:
        if not payload:
            # verify_token handles logging internally
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        # INGETROKKEN? (ADR-036 OP-260) Deze ingang miste de controle tot 2026-09-19,
        # terwijl er twaalf rbac-endpoints aan hangen.
        await _weiger_als_ingetrokken(payload, session)
        _weiger_portaaltoken(payload)

        user_identifier = payload.get("user_id")

        if user_identifier:
            # If it's an integer, it's a direct ID (from login endpoint)
            if isinstance(user_identifier, int):
                # Validate user exists
                from sqlalchemy import select

                from src.core.models.rbac_models import User

                result = await session.execute(select(User).where(User.id == user_identifier))
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(f"User not found for ID: {user_identifier}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token or user not found",
                    )

                _weiger_als_uitgeschakeld(bool(user.is_active), user.id)
                return user.id

            # String user_id or email format
            user_email = user_identifier
            # Remove "user_" prefix if present
            if user_email.startswith("user_"):
                user_email = user_email[5:]  # Remove "user_" prefix

        else:
            # Fallback to legacy format (sub from jwt_handler)
            sub_value = payload.get("sub")

            # FIX: Check if 'sub' contains email or user ID
            if sub_value is None:
                logger.warning("JWT token missing both 'user_id' and 'sub' claims")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                )

            # If sub looks like an email, use it as email
            if isinstance(sub_value, str) and "@" in sub_value:
                user_email = sub_value
            # If sub is numeric string or int, treat it as user ID
            elif isinstance(sub_value, (int, str)) and str(sub_value).isdigit():
                # Direct user ID - validate and return
                from sqlalchemy import select

                from src.core.models.rbac_models import User

                user_id_from_sub = int(sub_value)
                result = await session.execute(select(User).where(User.id == user_id_from_sub))
                user = result.scalar_one_or_none()

                if not user:
                    logger.warning(f"User not found for ID from sub: {user_id_from_sub}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token or user not found",
                    )

                _weiger_als_uitgeschakeld(bool(user.is_active), user.id)
                logger.debug("User resolved via numeric sub claim")
                return user.id
            else:
                # Unknown format
                logger.warning(f"JWT token 'sub' has unexpected format: {sub_value}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                )

            user_email = sub_value

        # Lookup user by email to get integer ID
        from sqlalchemy import select

        from src.core.models.rbac_models import User

        result = await session.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning("User not found for provided email")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token or user not found",
            )

        _weiger_als_uitgeschakeld(bool(user.is_active), user.id)
        return user.id

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected JWT validation error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        )


def require_permission(permission: Permission) -> Callable[..., Awaitable[int]]:
    """RBAC permission checker dependency with multi-tenant isolation.

    Args:
        permission: Permission enum from core.auth.rbac

    Returns:
        FastAPI dependency that validates permission and returns user_id

    Raises:
        HTTPException 401: Invalid/expired token
        HTTPException 403: Permission denied or tenant mismatch

    MULTI-TENANT: Validates tenant_id matches between request context and user
    """

    async def permission_checker(
        user_id: int = Depends(get_current_user_id),
        session: AsyncSession = Depends(get_db),
    ) -> int:
        # Get tenant from context (set by TenantMiddleware)
        request_tenant_id = require_tenant_id()  # Fails if no tenant context

        # Verify user belongs to the request tenant
        # Use rbac_models.User which has tenant_id column
        from sqlalchemy import select

        result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == request_tenant_id,  # Tenant filter
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(
                f"Tenant mismatch or user not found: user_id={user_id}, "
                f"request_tenant_id={request_tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not found in tenant context. Possible tenant mismatch.",
            )

        # Existing RBAC check
        rbac = RBACService(session)
        # Permission enum values map to actions on wildcard resource
        has_permission = await rbac.has_permission(user_id, "*", permission.value)

        if not has_permission:
            logger.warning(
                f"Permission denied: user_id={user_id}, "
                f"tenant_id={request_tenant_id}, "
                f"permission={permission.value}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission.value}",
            )

        logger.debug(
            f"Permission granted: user_id={user_id}, "
            f"tenant_id={request_tenant_id}, permission={permission.value}"
        )
        return user_id

    return permission_checker


#: De weigering van een recht in gewone taal, voor de rechten die een medewerker op een scherm tegenkomt. Een recht dat
#: hier niet staat houdt de technische melding; die wordt per recht toegevoegd als er een scherm voor bestaat.
RECHT_MELDINGEN: dict[str, str] = {
    "receivables:read": (
        "U mag de debiteuren niet bekijken. Vraag de beheerder om u de rol 'debiteuren' te geven."
    ),
    "receivables:write": (
        "U mag debiteuren niet invoeren of wijzigen. Vraag de beheerder om u de rol "
        "'debiteuren' te geven."
    ),
    "receivables:propose": (
        "U mag geen herinneringen of aanmaningen voorstellen. Vraag de beheerder om u de rol "
        "'debiteuren' te geven."
    ),
    "payables:read": (
        "U mag de inkoopfacturen niet bekijken. Vraag de beheerder om u de rol 'crediteuren' te geven."
    ),
    "payables:write": (
        "U mag inkoopfacturen en leveranciers niet invoeren of wijzigen. Vraag de beheerder om u de rol "
        "'crediteuren' te geven."
    ),
}


async def controleer_resource_recht(
    session: AsyncSession, user_id: int, tenant_id: int, resource: str, action: str
) -> None:
    """De rolcontrole van `require_resource_permission`, los aan te roepen.

    Voor ingangen zonder FastAPI-dependency op het verzoek, zoals een websocketbericht
    (focus-builder `ws/chat`, `accept_proposal`). De gebruiker moet in `tenant_id` staan en
    `resource:action` hebben; anders 403 (HTTPException) met dezelfde melding als de dependency.
    """
    from sqlalchemy import select

    gevraagd = f"{resource}:{action}"
    user = (
        await session.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not user:
        logger.warning(
            "Tenant mismatch or user not found: user_id=%s, request_tenant_id=%s",
            user_id,
            tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found in tenant context. Possible tenant mismatch.",
        )

    if not await RBACService(session).has_permission(user_id, resource, action):
        logger.warning(
            "Permission denied: user_id=%s, tenant_id=%s, permission=%s",
            user_id,
            tenant_id,
            gevraagd,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=RECHT_MELDINGEN.get(gevraagd, f"Missing permission: {gevraagd}"),
        )


def require_resource_permission(resource: str, action: str) -> Callable[..., Awaitable[int]]:
    """RBAC-controle op EEN resource, bijvoorbeeld `receivables:write` (rolmodel debiteuren).

    `require_permission` vraagt altijd de resource-wildcard (`*:write`); dat recht heeft van de
    standaardrollen alleen `admin`. Deze variant vraagt `has_permission(user_id, resource,
    action)`, dus een rol met `receivables:write` slaagt, en `admin` (`*:*`) ook via de
    wildcard. `require_permission` zelf is bewust NIET gewijzigd: ongeveer 306 endpoints leunen
    erop.

    Dezelfde tenantcontrole als `require_permission`: de gebruiker moet in de tenant van het
    verzoek staan. Een weigering geeft 403 met `Missing permission: <resource>:<action>`.
    De controle zelf staat in `controleer_resource_recht` (ook gebruikt door de websocket).
    """

    # Zelfde binnennaam als in `require_permission`: tests vervangen de rolcontrole op
    # `__name__ == "permission_checker"` (tests/unit/debiteuren/test_api_verloop.py e.a.).
    async def permission_checker(
        user_id: int = Depends(get_current_user_id),
        session: AsyncSession = Depends(get_db),
    ) -> int:
        await controleer_resource_recht(session, user_id, require_tenant_id(), resource, action)
        logger.debug(
            "Permission granted: user_id=%s, permission=%s:%s", user_id, resource, action
        )
        return user_id

    return permission_checker


def require_permission_with_tenant_bypass(
    permission: Permission, allow_super_admin: bool = False
) -> Callable[..., Awaitable[int]]:
    """RBAC permission checker with optional super admin tenant bypass.

    Args:
        permission: Required permission
        allow_super_admin: If True, super admins can access all tenants

    Returns:
        FastAPI dependency that validates permission and returns user_id

    Use Case: Support operations, cross-tenant reporting, platform administration

    WARNING: Only use for endpoints that genuinely need cross-tenant access
    """

    async def permission_checker_with_bypass(
        user_id: int = Depends(get_current_user_id),
        session: AsyncSession = Depends(get_db),
    ) -> int:
        # Check if user is super admin
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Super admin bypass logic
        if allow_super_admin and is_platform_superuser(user):
            # Log super admin bypass for audit
            from src.core.governance.services.audit_service import SecurityEvent, log_security_event

            await log_security_event(
                event_type=SecurityEvent.SUPERUSER_BYPASS,
                user_id=user_id,
                tenant_id=get_tenant_id(),  # May be None for cross-tenant
                request_path="unknown",  # Would need request context
                request_method="unknown",
                details={"permission": permission.value},
                threat_level="low",  # Normal operation for super admins
            )

            logger.info(
                f"Super admin tenant bypass: user_id={user_id}, permission={permission.value}"
            )
            return user_id

        # Normal tenant-aware permission check
        return await require_permission(permission)(user_id=user_id, session=session)

    return permission_checker_with_bypass


#: De admin-definitie voor beheer BINNEN een tenant (ADR-036 OP-40). Een verzameling en geen
#: literal in een functie, zodat geen enkel aanroeppunt er zijn eigen kopie van kan houden.
#:
#: Dit is de UNIE van de drie vocabulaires die hier tot 2026-09-01 naast elkaar bestonden, op
#: expliciet besluit van Rakesh: een foute afwijzing van een legitieme beheerder tijdens een
#: incident is duurder dan een iets ruimere toegang, en de superuser-bypass stond toch al overal
#: los verspreid. De afweging tegen least privilege (OWASP ASVS 5.0 V8.2.1) staat in
#: `docs/backend/features/BE-SEC-050-centrale-admin-definitie.md`.
#:
#: NIET voor checks die de TENANT-GRENS poorten. Die zijn bewust smaller (`system_admin`-only) en
#: staan met reden en datum in `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` in
#: `tests/architecture/test_admin_checks_use_the_central_definition.py`.
ADMIN_ROLE_NAMES: frozenset[str] = frozenset({"admin", "system_admin", "tenantadmin"})


def is_admin(user: object) -> bool:
    """Is deze gebruiker beheerder BINNEN zijn tenant? De definitie voor de zeven dependencies
    uit ADR-036 OP-40 -- en niet, laat dat duidelijk zijn, voor de hele codebase.

    **De inventaris is zeven, niet alles.** Een blinde review op deze wijziging vond nog minstens
    zes andere plekken die zelf een beheerdersrol bepalen, waaronder een vierde spelling
    (`tenant_admin` MET underscore in `api/domain_packs.py`) en twee inline checks die de
    tenant-grens poorten. Ze staan met datum en reden in `KNOWN_UNCONSOLIDATED_ADMIN_CHECKS` in
    `tests/architecture/test_admin_checks_use_the_central_definition.py`, met een staleness-test
    ernaast. Consolideer daar niets heen zonder de reden in die lijst te lezen.

    **Waarom dit er is.** Tot 2026-09-01 beslisten zeven plekken dit zelf, in drie onverenigbare
    vocabulaires, en de meting stond in vier faalprofielen van
    `tests/unit/auth/test_admin_definition_is_consistent.py`: een `system_admin` mocht bij vier
    van de zeven wel en werd op de HITL-goedkeuringspoort geweigerd, een `tenantadmin` mocht bij
    twee, een superuser zonder benoemde rol werd door vier geweigerd, en de destijds door
    `RoleSeeder` aangemaakte standaardrol `"Admin"` (met hoofdletter) telde alleen mee
    bij de twee checks die de naam omzetten naar kleine letters.

    **Twee bewuste keuzes, allebei van Rakesh en niet hier te heropenen.**

    1. De verzameling is de UNIE van de drie vocabulaires. Dat verbreedt op vijf van de zeven
       plekken; zie het feature-doc voor welke rol waar toegang wint.
    2. De vergelijking is hoofdletter-ONgevoelig. Dat is geen verbreding maar het gedrag van de
       twee checks die dat al deden -- en zonder dat zou de geseede standaardrol op vijf plekken
       geen beheerder zijn.

    **Wat deze functie NIET doet.** Hij weegt geen tenant-scope mee: hij kijkt alleen naar
    rolnamen op het gebruikersobject. Wat de tenant-grens dan WEL afdwingt, is nagemeten -- en
    het is niet wat hier eerst stond. Een eerdere versie van deze docstring schreef de grens toe
    aan ADR-004 (`do_orm_execute`); dat is onjuist:

    - `auth_service.py:398` en `:431` -- de twee queries die `UserResponse.roles` vullen, draaien
      allebei in `with TenantFilterBypass():`. Op precies deze leesroute staat de ADR-004-hook dus
      UIT (met reden: bij tokenverificatie is de tenant nog niet bekend).
    - `user_roles` heeft geen `tenant_id`-kolom, dus er is geen schema-constraint. Sinds de
      migratie `20261004_user_roles_rls` heeft de tabel wel een policy op gebruiker EN rol;
      die beschermt alleen een verbinding die onder RLS valt (OP-151).

    De grens komt van het SCHRIJFpad: rollen worden alleen tenant-eigen toegekend
    (`api/v1/user_management/crud_router.py:518` filtert `Role.tenant_id == user.tenant_id`, en
    `services/rbac_service.assign_role` neemt een `tenant_id`-parameter). Een gebruiker kan dus
    geen rol van een andere tenant in zijn lijst krijgen. Dat is een zwakkere garantie dan een
    hook of een constraint -- ze hangt aan de zorgvuldigheid van elk toekenningspad -- en dat
    hoort hier te staan in plaats van een mechanisme dat er niet is.

    **Kanttekening (2026-09-09, gevonden bij de OP-40-review):** het aangehaalde bestand
    (`user_management/crud_router.py`) is vandaag zelf dode code (ADR-036 OP-224) -- de garantie
    hierboven geldt dus voor een pad dat niet live is. Het LEVENDE aanmaakpad heeft een eigen,
    al geregistreerd en NOG NIET gefixt gat: `assign_user_roles`/`create_user` filteren op de
    tenant van het SLACHTOFFER, niet van de AANVRAGER (ADR-036 OP-183, bewust omheind cluster,
    wacht op Rakesh). Deze functie zelf blijft correct -- hij kijkt alleen naar de rollijst die de
    gebruiker AL heeft -- maar het schrijfpad dat die lijst vult is dus zwakker dan hierboven
    klinkt.

    **Deze functie beantwoordt de vraag "mag deze gebruiker beheren BINNEN zijn tenant".** Zij
    beantwoordt NIET "mag deze gebruiker de tenant-grens over". Die tweede vraag heeft eigen,
    bewust SMALLERE checks (`system_admin`-only); zie de uitzonderingslijst in
    `tests/architecture/test_admin_checks_use_the_central_definition.py`. Consolideer die niet
    hierheen -- dat zou elke `tenantadmin` cross-tenant toegang geven.

    Geen dependency maar een pure functie: zo kan een endpoint hem in zijn eigen body aanroepen
    naast een bestaande `get_current_user`-dependency, en kan een unittest hem los bevragen.
    """
    if getattr(user, "is_superuser", False):
        # Deny-by-default kent hier een uitzondering, dus die uitzondering hoort zichtbaar te
        # zijn (OWASP ASVS 5.0 V8.3.1). Alleen loggen als de bypass de ENIGE reden is.
        if not _has_admin_role_name(user):
            logger.info(
                "Superuser bypass verleent beheerdersrechten zonder beheerdersrol: user_id=%s",
                getattr(user, "id", None),
            )
        return True
    return _has_admin_role_name(user)


def is_platform_superuser(user: object) -> bool:
    """Mag deze gebruiker de TENANT-GRENS over? De centrale definitie (ADR-036 OP-189).

    Dit is de tweede privilege-as van dit systeem, naast `is_admin`. De twee beantwoorden
    verschillende vragen en mogen niet door elkaar lopen:

        `is_admin`               -- mag deze gebruiker beheren BINNEN zijn eigen tenant?
        `is_platform_superuser`  -- mag deze gebruiker BUITEN zijn tenant kijken en handelen?

    **Waarom dit er is.** Tot 2026-09-18 stond `user.is_superuser` op 17 beslissende plekken
    in 9 bestanden los uitgeschreven. Elke consolidatie van de ROLchecks (OP-40) liet die as
    ongemoeid, en dat levert een nette ordening met een deur ernaast: wie hier later een
    voorwaarde aan toevoegt -- een auditregel, een tweede factor, een uitschakelaar -- zet hem
    op de plek die hij toevallig openhad. Dat is exact het patroon uit OP-254, waar een
    verplichte stap op een van de zes schrijfplekken stond.

    **Wat gemeten is op 2026-09-18, en waarom deze vlag geen escalatiepad is.**

    - `is_superuser` wordt NERGENS via een API gezet. Geen enkel request-schema in `src/`
      bevat het veld; de twee schrijfplekken zijn `database/seed.py:276` (de gezaaide
      beheerder) en `ensure_demo_user.py:115` (een script). Een tenantbeheerder kan zichzelf
      of iemand anders dus niet tot superuser maken.
    - De vlag is NIET hetzelfde als de ROL met de naam `superuser`. Die naam komt voor in
      `services/rbac_service.py` (de `Permission.SUPERUSER`-waarde) en in twee checks in
      `api/v1/system/`, maar die rol wordt nergens aangemaakt of geseed -- gemeten: nul
      treffers in `database/` en in de rolseeder. Wie "superuser" leest, moet dus weten
      WELKE van de twee bedoeld is; daarom heet deze functie `is_platform_superuser` en niet
      `is_superuser`.
    - `RBACService._user_is_superuser` bevroeg die nooit-bestaande ROL en had nul aanroepers.
      Die is op 2026-09-18 verwijderd in plaats van gerepareerd: een tweede, stil altijd-false
      antwoord op deze vraag is gevaarlijker dan geen antwoord.

    **Wat deze functie bewust NIET doet.** Hij logt niet. `is_admin` logt wel, omdat de
    superuservlag daar een UITZONDERING op de rolcontrole is; hier is hij de vraag zelf, en
    een logregel per tenant-overschrijdende leesactie zou het auditspoor vullen zonder iets
    te onderscheiden. De plek die de bypass wel als uitzondering gebruikt
    (`require_permission_with_tenant_bypass`) logt hem daarom zelf, bewaakt door
    `tests/unit/auth/test_de_superuser_bypass_wordt_gelogd.py`.

    Een pure functie en geen dependency, om dezelfde reden als `is_admin`: zo kan een
    endpoint hem in zijn eigen body aanroepen en een unittest hem los bevragen.
    """
    return bool(getattr(user, "is_superuser", False))


def _has_admin_role_name(user: object) -> bool:
    """De rolnaam-helft van `is_admin`, zonder de superuser-bypass."""
    role_names = {
        r.strip().lower() for r in (getattr(user, "roles", None) or []) if isinstance(r, str) and r
    }
    return bool(role_names & ADMIN_ROLE_NAMES)


def is_tenant_admin(user: UserResponse) -> bool:
    """Legacy naam voor `is_admin`; delegeert en heeft GEEN eigen logica (ADR-036 OP-40).

    De naam is sinds de consolidatie te smal -- deze check accepteert nu ook `system_admin` -- maar
    hij staat op dertien aanroeppunten in vier bestanden en in de architecture-guard
    `tests/architecture/test_hitl_audit_is_admin_only.py`. Hernoemen zou die allemaal raken zonder
    dat er gedrag verandert. Hij blijft dus staan als doorgeefluik; nieuwe code gebruikt `is_admin`.
    """
    return is_admin(user)


async def require_admin(user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Require admin privileges for endpoint access.

    Delegeert naar `is_admin` (ADR-036 OP-40). Tot 2026-08-04 inlinede deze dependency dezelfde
    rollogica vier regels lager, met EEN verschil: hij accepteerde daarnaast `role_id == 1`.

    **De legacy-tak `role_id == 1` blijft staan, maar de reden die hier eerder stond is NIET
    aangetoond.** Die reden luidde: "een via die weg ingerichte beheerder zonder benoemde rol zou
    anders zijn toegang verliezen". Nagemeten 2026-09-01 en dat pad is niet gevonden:
    `require_admin` krijgt zijn gebruiker uitsluitend via `Depends(get_current_user)`, en de twee
    functies die `UserResponse` vullen (`auth_service.get_user_by_id` / `get_user_by_email`)
    zetten `role_id` niet -- het Pydantic-default `None` blijft staan. In het request-pad lijkt de
    tak dus onbereikbaar; alleen code die zelf een `UserResponse` construeert kan hem raken.

    Hij is hier NIET verwijderd, omdat verwijderen een gedragswijziging is die buiten OP-40 valt
    en een eigen rode test verdient. Wat er wel is gedaan: de onbewezen oorzaak is vervangen door
    deze meting. Merk op dat `role_id == 1` "de eerste rij in de roles-tabel" betekent -- een
    adminrecht dat aan een databasevolgorde hangt. Zie het feature-doc BE-SEC-050 sectie K.
    """
    if is_admin(user):
        return user

    if user.role_id == 1:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin privileges required",
    )


# ============================================================================
# Type Aliases for Modern Dependency Injection Pattern (Phase 4.3)
# ============================================================================
# Modern pattern: Replace legacy `current_user: UserResponse = Depends(get_current_user)`
# with `current_user: CurrentUser` in endpoint signatures.
# This enables better IDE support and automatic OpenAPI documentation.

CurrentUser = Annotated[UserResponse, Depends(get_current_user)]
RequireAdmin = Annotated[UserResponse, Depends(require_admin)]
