"""
Tenant Context Middleware - FIXED VERSION
Pure ASGI implementation (no BaseHTTPMiddleware - event loop safe)

CRITICAL FIX: Replaced deprecated BaseHTTPMiddleware with pure ASGI pattern
to fix "Future attached to a different loop" errors in Python 3.13+

Design:
- Extract tenant_id from JWT token on every request
- Store in ContextVar (thread-safe, async-safe)
- All database queries automatically filtered by tenant_id
- Impossible to forget tenant filter = zero data leak risk

Integration:
- Works with src.core.middleware.tenant_context for storage
- Integrates with src.core.auth.jwt_handler for token verification
- Must run AFTER authentication middleware
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import cast


from fastapi import Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.shared.public_registry import PublicEndpointRegistry
from src.core.auth.token_extraction import extract_access_token_cookie, extract_http_token
from src.core.auth.types import VerifiedJWTPayload

# Import tenant context management
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.shared.security_events import SecurityEvent, log_security_event
from src.config import DEPLOYMENT_MODE

logger = logging.getLogger(__name__)


class _PublicPassThrough(Exception):
    """Signaal: dit PUBLIEKE verzoek moet anoniem door, ondanks een kapot token.

    Waarom een exceptie en geen directe aanroep van `self.app`: de tokenvalidatie staat in een
    `try` met een vangnet-`except Exception`. Een `await self.app(...)` VANUIT die try betekent
    dat een fout in de route-handler door datzelfde vangnet wordt opgevangen, waarna de handler
    een TWEEDE keer wordt aangeroepen. Een Gate 2-reviewer heeft dat gemeten: een POST naar
    `/api/v1/auth/register` met een verlopen cookie voerde de handler twee keer uit en stuurde
    twee volledige HTTP-antwoorden -- dubbele registratie, dubbele magic-link-mail, dubbele
    rate-limit-consumptie.

    Door hier te SIGNALEREN in plaats van door te laten, gebeurt de doorlaat precies een keer, na
    de `try/except`. `test_the_downstream_app_is_called_exactly_once` legt dat vast.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def get_auth_token_from_request(request: Request) -> str | None:
    """
    Haalt het JWT access token op uit de request.
    Prioriteit:
    1. Authorization-header: Bearer <token>
    2. Cookie: access_token (fallback)
    """
    return extract_http_token(
        authorization=request.headers.get("Authorization"),
        access_token_cookie=request.cookies.get("access_token"),
    )


class TenantMiddleware:
    """
    Pure ASGI middleware for tenant context extraction (event loop safe)

    Flow:
    1. Extract JWT from Authorization header
    2. Decode and verify JWT (including tenant_id claim)
    3. Set ContextVar: current_tenant_id = payload.tenant_id
    4. Store in scope["state"] (becomes request.state in handlers)
    5. All subsequent queries auto-filtered by tenant_id

    Critical:
    - Pure ASGI implementation (no BaseHTTPMiddleware - fixes event loop issues)
    - Must run AFTER authentication middleware
    - Runs BEFORE handlers (so all handlers inherit tenant context)
    - Database event hooks depend on this ContextVar
    """

    # Paths/prefixes that need NO tenant processing at all (health, docs, metrics)
    # NOTE: /api/v1/auth is intentionally NOT here -- auth endpoints are handled
    # by PublicEndpointRegistry so that public ones pass through but authenticated
    # ones (like /api/v1/auth/me) still get tenant context.
    EXCLUDED_PREFIXES = [
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
    ]

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Process request through tenant context middleware (pure ASGI)
        """
        # Process only HTTP requests. Other ASGI protocols pass through unchanged.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request details from ASGI scope
        path = scope["path"]

        # Use Starlette's Headers utility (safe for WS)
        headers = Headers(scope=scope)

        # Generate request ID for tracing
        request_id = headers.get("X-Request-ID") or str(uuid.uuid4())

        # Initialize scope state if not present
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Skip tenant context for OPTIONS requests (CORS preflight)
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Skip tenant context for excluded prefixes (e.g., health endpoints)
        for prefix in self.EXCLUDED_PREFIXES:
            # Segmentgrens: `/docsXYZ` hoort er niet onder (zelfde regel als PublicEndpointRegistry).
            if path == prefix or path.startswith(prefix + "/"):
                logger.debug(f"Skipping tenant context for excluded endpoint: {path}")
                await self.app(scope, receive, send)
                return

        # Check if this is a public endpoint
        is_public = PublicEndpointRegistry.is_public(path)

        token = extract_http_token(
            authorization=headers.get("authorization"),
            access_token_cookie=extract_access_token_cookie(headers.get("cookie")),
        )

        # Public endpoint without token: pass through without tenant context
        if is_public and not token:
            await self.app(scope, receive, send)
            return

        # Gevuld zodra een van de vier token-faalpaden op een PUBLIEK endpoint wordt geraakt. De
        # doorlaat zelf gebeurt NA de try/except -- zie `_PublicPassThrough` voor waarom dat moet.
        public_pass_through_reason: str | None = None

        # From here on: either non-public endpoint, or public endpoint with token
        # Either way, we need to validate the token and set tenant context

        if not token:
            # ADR-036 OP-62 (2026-08-26, Rakesh GO): een verzoek ZONDER token kreeg hier
            # eerder in single_tenant mode alsnog roles=["admin"] en tenant_id=1 -- volledige
            # adminrechten zonder enige verificatie. `single_tenant` mag de TENANT-resolutie
            # vereenvoudigen (zie de tenant_id-default hieronder, na een GEVERIFIEERD token),
            # maar nooit de AUTHENTICATIE overslaan. Elke deployment mode vereist dus een
            # geldig token; het ontbreken ervan is in single_tenant net zo'n 401 als in saas.
            logger.warning(
                f"!!! AUTH FAIL !!! Missing or invalid Authorization header/cookie for {path}"
            )
            response = JSONResponse(
                {"detail": "Missing or invalid authentication"},
                status_code=401,
                headers={"X-Request-ID": request_id},
            )
            await response(scope, receive, send)
            return

        # Token is present - verify and extract tenant context
        try:
            # Import JWT handler here to avoid circular imports
            from src.core.auth.jwt_handler import jwt_handler

            payload = jwt_handler.verify_token(token)

            if payload is None:
                if is_public:
                    raise _PublicPassThrough("invalid or expired token")
                logger.warning(f"Invalid or expired token for {path}")
                response = JSONResponse(
                    {"detail": "Invalid or expired token"},
                    status_code=401,
                    headers={"X-Request-ID": request_id},
                )
                await response(scope, receive, send)
                return

            # CRITICAL: Extract tenant_id from JWT
            # The tenant_id must be added to JWT tokens during login
            tenant_id = payload.get("tenant_id")

            if tenant_id is None:
                if DEPLOYMENT_MODE == "single_tenant":
                    tenant_id = 1
                    logger.debug(f"JWT missing tenant_id, but using default=1 due to single_tenant mode for {path}")
                elif is_public:
                    # Doorlaten EN auditen. Zonder dit event verdween de sterkste detectie van
                    # dit bestand op precies de endpoints die een aanvaller het eerst probeert:
                    # een GELDIG ondertekend token met een kapotte claimset is het signaal van
                    # sleutelcompromittering of tokenvervalsing. Een Gate 2-reviewer mat dat de
                    # eerste versie van deze fix het aantal events op een publiek pad van 1 naar
                    # 0 bracht. Doorlaten en auditen sluiten elkaar niet uit.
                    await log_security_event(
                        event_type=SecurityEvent.TENANT_CONTEXT_FAILED,
                        request_path=str(path),
                        request_method=scope.get("method", "UNKNOWN"),
                        ip_address=scope.get("client", ("unknown", 0))[0],
                        details={
                            "reason": "no_tenant_in_token",
                            "user": payload.get("sub", "unknown"),
                            "public_endpoint_passed_through": True,
                        },
                        threat_level="low",
                    )
                    raise _PublicPassThrough("token without tenant claim")
                else:
                    # AUDIT: Log failed tenant context
                    await log_security_event(
                        event_type=SecurityEvent.TENANT_CONTEXT_FAILED,
                        request_path=str(path),
                        request_method=scope.get("method", "UNKNOWN"),
                        ip_address=scope.get("client", ("unknown", 0))[0],
                        details={
                            "reason": "no_tenant_in_token",
                            "user": payload.get("sub", "unknown"),
                        },
                        threat_level="medium",
                    )

                    logger.error(
                        f"Token missing tenant_id claim for {path}. "
                        f"User: {payload.get('sub', 'unknown')}"
                    )
                    response = JSONResponse(
                        {"detail": "Token missing tenant context"},
                        status_code=401,
                        headers={"X-Request-ID": request_id},
                    )
                    await response(scope, receive, send)
                    return

            # Convert to integer if needed (JWT may serialize as string)
            if isinstance(tenant_id, str):
                try:
                    tenant_id = int(tenant_id)
                except ValueError:
                    if is_public:
                        raise _PublicPassThrough("unparseable tenant id") from None
                    logger.error(f"Invalid tenant_id format: {tenant_id}")
                    response = JSONResponse(
                        {"detail": "Invalid tenant context"},
                        status_code=401,
                        headers={"X-Request-ID": request_id},
                    )
                    await response(scope, receive, send)
                    return

            if isinstance(tenant_id, bool) or not isinstance(tenant_id, int):
                if is_public:
                    raise _PublicPassThrough("unusable tenant id type")
                logger.error("Invalid tenant_id type in token")
                response = JSONResponse(
                    {"detail": "Invalid tenant context"},
                    status_code=401,
                    headers={"X-Request-ID": request_id},
                )
                await response(scope, receive, send)
                return

            # UITGESCHAKELD IS UITGESCHAKELD, voor ELKE route met een token (gemeten 2026-10-12):
            # routes zonder gebruikersafhankelijkheid (zoeken, crag, evaluaties) lazen alleen dit
            # token. Een query per verzoek, bewust zonder cache (OP-254).
            from src.core.auth.account_status import (
                AccountStatus,
                gebruikers_id_uit_sub,
                haal_account_status,
                is_portal_token,
            )

            account_status = await haal_account_status(
                str(payload.get("sub") or ""),
                tenant_id,
                portal=is_portal_token(cast(Mapping[str, object], payload)),
            )
            if account_status is not AccountStatus.ACTIEF:
                if is_public:
                    raise _PublicPassThrough("account disabled or status unknown")
                uitgezet = account_status is AccountStatus.UITGESCHAKELD
                response = JSONResponse(
                    {"detail": "ACCOUNT_DISABLED" if uitgezet else "Authentication unavailable"},
                    status_code=401 if uitgezet else 503,
                    headers={"X-Request-ID": request_id},
                )
                await response(scope, receive, send)
                return

            # Set ContextVar (inherited by all async tasks in request)
            set_tenant_id(tenant_id)

            # Het NUMERIEKE gebruikers-id voor de limietsleutel: `sub` is op het wachtwoordpad een
            # e-mailadres en op de andere paden het id (twee emmers per gebruiker). `None` = niet
            # vast te stellen; een limietroute weigert dan met 401 (fail-closed).
            limiet_gebruiker = await gebruikers_id_uit_sub(
                str(payload.get("sub") or ""),
                tenant_id,
                portal=is_portal_token(cast(Mapping[str, object], payload)),
            )

            # FIX: Extract and store scopes from JWT
            raw_scopes = payload.get("scopes", [])
            if isinstance(raw_scopes, str):
                # Handle old tokens with comma-separated scopes
                scopes: list[str] = [s.strip() for s in raw_scopes.split(",") if s.strip()]
            elif isinstance(raw_scopes, list):
                scopes = raw_scopes
            else:
                scopes = []
            # Store scopes in ContextVar for fast permission checks
            from src.core.middleware.tenant_context import _current_user_scopes

            _current_user_scopes.set(scopes)

            # Store in ASGI scope state (becomes request.state in handlers)
            scope["state"].update(
                {
                    "tenant_id": tenant_id,
                    "user_id": payload.get("sub"),
                    "limiet_gebruiker": limiet_gebruiker,
                    "email": payload.get("email"),
                    "roles": payload.get("roles", []),
                    "scopes": scopes,  # NEW: Add scopes to request state
                }
            )

            logger.debug(
                "Tenant context set for request",
                extra={
                    "request_id": request_id,
                    "tenant_id": tenant_id,
                    "user_id": payload.get("sub"),
                    "path": path,
                },
            )

        except _PublicPassThrough as doorlaat:
            public_pass_through_reason = doorlaat.reason

        except Exception as e:
            # Ook op een publiek pad met exc_info loggen: zonder dat verdwijnt een echte storing
            # (gerouleerde JWT-sleutel, kapotte jwt-bibliotheek) in een INFO-regel zonder
            # stacktrace, terwijl elk publiek verzoek dan stil anoniem wordt. Zie
            # `.claude/rules/backend-patterns.md` regel 10.
            logger.error(
                f"Tenant context extraction failed: {str(e)}",
                extra={"request_id": request_id, "path": path},
                exc_info=True,
            )
            if is_public:
                public_pass_through_reason = f"unexpected error: {type(e).__name__}"
            else:
                response = JSONResponse(
                    {"detail": "Authentication failed"},
                    status_code=401,
                    headers={"X-Request-ID": request_id},
                )
                await response(scope, receive, send)
                return

        if public_pass_through_reason is not None:
            # De doorlaat gebeurt hier, BUITEN de try, zodat een fout in de route-handler niet
            # door het vangnet hierboven wordt opgevangen en de handler een tweede keer draait.
            #
            # Eerst alles wissen wat een half verwerkt token kan hebben achtergelaten. Het
            # vangnet vangt ook fouten die NA `set_tenant_id` optreden, en de `finally` die
            # normaal opruimt hoort bij de try hieronder -- die wordt hier overgeslagen. Zonder
            # deze regels lekt een tenant-id of een rollenlijst naar een handler die juist
            # anoniem hoort te draaien.
            from src.core.middleware.tenant_context import _current_user_scopes

            clear_tenant_context()
            _current_user_scopes.set([])
            for sleutel in ("tenant_id", "user_id", "limiet_gebruiker", "email", "roles", "scopes"):
                scope["state"].pop(sleutel, None)

            logger.info(
                "Public endpoint passed through without tenant context: %s (%s)",
                path,
                public_pass_through_reason,
            )

            # Ook deze doorlaat krijgt het correlatie-id mee. Zonder dit ontbrak `x-request-id`
            # juist op de verzoeken die je het hardst wilt kunnen terugvinden: de inlogpogingen
            # met een verlopen cookie waar de logregel hierboven bij hoort. Gemeten door een
            # Gate 2-reviewer.
            async def anoniem_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    kopteksten = list(message.get("headers", []))
                    kopteksten.append((b"x-request-id", request_id.encode()))
                    message["headers"] = kopteksten
                await send(message)

            await self.app(scope, receive, anoniem_send)
            return

        # Process request with tenant context set
        try:
            # Wrap send to add response headers
            async def send_wrapper(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers_list = list(message.get("headers", []))
                    headers_list.append((b"x-request-id", request_id.encode()))
                    # NOTE: x-tenant-id is intentionally NOT added to responses.
                    # Exposing it in every response is unnecessary information disclosure.
                    message["headers"] = headers_list

                await send(message)

            await self.app(scope, receive, send_wrapper)
        finally:
            # CRITICAL: Clear tenant context after request to prevent leaks
            clear_tenant_context()
