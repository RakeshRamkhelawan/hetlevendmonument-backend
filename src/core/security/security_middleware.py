#!/usr/bin/env python3
"""
Security Middleware for FastAPI
Integrates production security manager with FastAPI requests

ASGI3 Compliant Implementation:
- Enforces keyword-only parameters for proper middleware instantiation
- Provides complete type annotations for ASGI callable signatures
- Implements fail-closed security model for production environments
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING, cast
from collections.abc import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.routing import Match

from src.core.shared.limiet_sleutel import afzender_adres
from src.core.shared.public_registry import PublicEndpointRegistry

from .ip_reputation import IpReputation, get_ip_reputation
from .security_manager import SecurityLevel, ThreatLevel, get_security_manager

# CG-007: canonical JWT verification -- same claims (sub, tenant_id, exp, HS256) as TenantMiddleware
from src.core.auth.jwt_handler import jwt_handler as _jwt_handler

# ASGI3 type definitions for proper type checking
if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


#: Routesjablonen waarvan de beheerdersrol per route wordt gecontroleerd (zie `_is_beheerroute`).
BEHEER_PREFIXEN: tuple[str, ...] = ("/api/v1/system/", "/api/v1/autonomous/")


class SecurityMiddleware:
    """
    ASGI3-compliant FastAPI middleware for production security

    Handles authentication, rate limiting, and threat detection with proper
    ASGI callable signature and keyword-only parameter enforcement.

    Args:
        app: The ASGI application instance
        enable_security: Keyword-only parameter to enable/disable security checks
                        MUST be passed as keyword argument (enable_security=True)

    Example:
        # CORRECT (keyword argument):
        app.add_middleware(SecurityMiddleware, enable_security=True)

        # INCORRECT (positional argument):
        app.add_middleware(SecurityMiddleware, True)  # Will raise TypeError

    Security Model:
        - Fail-closed: Rejects requests on security check failures
        - Fail-open: Continues on middleware errors (availability over security)
        - Development mode: Relaxed IP allowlist, accepts dev tokens
        - Production mode: Strict IP allowlist, requires valid JWT tokens
    """

    def __init__(
        self,
        app: "ASGIApp",
        *,
        enable_security: bool = True,
        ip_reputation: IpReputation | None = None,
    ) -> None:
        """
        Initialize security middleware with ASGI3-compliant signature.

        The asterisk (*) enforces that enable_security MUST be passed as a
        keyword argument, preventing silent failures from positional arguments.

        Args:
            app: The ASGI application to wrap
            enable_security: Keyword-only flag to enable security checks
            ip_reputation: de IP-reputatie (score en blokkade in Redis); standaard de gedeelde
                instantie van dit proces. Tests geven er een eigen mee.
        """
        self.app = app
        self.enable_security = enable_security
        self.security_manager = get_security_manager()
        self._ip_reputation = ip_reputation
        logger.info(f"Security middleware initialized (enabled: {enable_security})")

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        # Pass through non-HTTP/WebSocket events (e.g., lifespan) without processing.
        # Creating a Request(scope) for lifespan events triggers:
        #   AssertionError: assert scope["type"] in ("http", "websocket")
        # which silently crashes the ASGI lifespan protocol and prevents DB init.
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # WebSocket upgrades don't have a `method` in the ASGI scope -- pass through
        # so the router's own token-based auth handles authentication.
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # CRITICAL FIX: Allow OPTIONS (CORS preflight) requests through WITHOUT security checks
        # CORS preflight requests must be handled by CORSMiddleware, not blocked by security
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # If security is explicitly disabled, skip all checks
        if not self.enable_security:
            await self.app(scope, receive, send)
            return

        # Get client IP
        client_ip = afzender_adres(request)

        response_started = False

        # Security checks
        try:
            # 1. IP allowlist check (in production)
            if not self._is_development_mode() and not self.security_manager.is_ip_allowed(
                client_ip
            ):
                logger.warning(f"Access denied for IP: {client_ip}")
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "Access denied",
                        "message": "Your IP address is not allowed",
                    },
                )
                await response(scope, receive, send)
                return

            # 2. Tijdelijke IP-blokkade (Redis, gedeeld over workers en replica's). Een adres uit
            # de allowlist en een beheerder met een geldig token worden nooit geblokkeerd. Valt
            # Redis uit, dan gaat het verkeer door (fail-open, met een waarschuwing in de log).
            #
            # De beheerderscontrole kost een databaseopzoeking en draait daarom ALLEEN als het
            # adres echt geblokkeerd is (of hieronder een SQL-signaal geeft), niet bij elk
            # verzoek. Het resultaat wordt per verzoek een keer bepaald.
            beheerder: list[bool] = []

            async def _vrijgesteld() -> bool:
                if self.ip_reputation.is_exempt(client_ip):
                    return True
                if not beheerder:
                    beheerder.append(await self._is_admin_token(request))
                return beheerder[0]

            seconden = await self.ip_reputation.block_seconds_left(client_ip)
            if seconden is not None and not await _vrijgesteld():
                if self._is_inlogpad(scope):
                    # Inloggen vanaf een geblokkeerd adres mag door tot de wachtwoordcontrole;
                    # de loginroute geeft daarna ALLEEN een beheerder een token en weigert
                    # iedereen anders met dezelfde 403 (acceptant ronde 3, N3).
                    scope.setdefault("state", {})["ip_blokkade_seconden"] = seconden
                else:
                    logger.warning("Blocked IP attempted access: %s", client_ip)
                    await self._blokkade_response(seconden)(scope, receive, send)
                    return

            # 3. Rate limiting
            # ADR-036 OP-202: scope["path"] (niet request.url.path) -- dezelfde bron als
            # tenant_middleware.py:119 en als wat de ASGI-router daadwerkelijk gebruikt.
            # request.url.path wordt door Starlette gereconstrueerd uit de Host-header;
            # zie GHSA-86qp-5c8j-p5mr (CVE-2026-48710, "BadHost") voor de klasse fout die
            # dat opent als twee handhavingspunten een verschillende padbron lezen.
            endpoint = scope["path"]
            security_level = self._determine_security_level(endpoint, request)

            if not self.security_manager.check_rate_limit(client_ip, endpoint, security_level):
                logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}")
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "message": "Too many requests. Please try again later.",
                        "retry_after": 60,
                    },
                )
                await response(scope, receive, send)
                return

            # 4. Threat detection
            user_id = self._extract_user_id(request)
            door_gebruiker = self._door_gebruiker_geleverd(request)

            # Een SQL-patroon in een queryparameter of padparameter is een SIGNAAL: het telt
            # mee in de score van dit IP. Pas boven de drempel volgt een blokkade, en dan krijgt
            # ook deze aanvraag zelf 403 (plan nazorg, deel I punten a en b).
            if (
                self.security_manager.sql_injection_signal(
                    client_ip, user_id, endpoint, door_gebruiker
                )
                and not await _vrijgesteld()
            ):
                punten = self.ip_reputation.settings.sql_signal_points
                if await self.ip_reputation.record(client_ip, punten, "sql_injection_signal"):
                    seconden = await self.ip_reputation.block_seconds_left(client_ip)
                    await self._blokkade_response(
                        seconden or self.ip_reputation.settings.block_base_seconds
                    )(scope, receive, send)
                    return

            threat_level = self.security_manager.detect_suspicious_activity(
                client_ip, user_id, endpoint, user_values=door_gebruiker
            )

            if threat_level == ThreatLevel.CRITICAL:
                logger.critical(f"Critical threat detected from {client_ip} on {endpoint}")
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": "Security violation",
                        "message": "Request blocked due to security policy",
                    },
                )
                await response(scope, receive, send)
                return

            # 5. Authentication check for protected endpoints
            if security_level != SecurityLevel.PUBLIC:
                auth_result = self._check_authentication(request, security_level)
                if not auth_result["valid"]:
                    response = JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Authentication required",
                            "message": auth_result["message"],
                        },
                    )
                    await response(scope, receive, send)
                    return

            # Continue with request processing
            start_time = time.time()

            async def send_wrapper(
                message: Message,
            ) -> None:
                nonlocal response_started
                try:
                    if message["type"] == "http.response.start":
                        response_started = True
                        # Add security headers
                        headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                        security_headers = self.security_manager.get_security_headers()

                        for key, value in security_headers.items():
                            headers.append((key.encode(), value.encode()))

                        message["headers"] = headers

                except Exception as header_err:
                    logger.warning(f"Security headers injection failed: {header_err}")
                    # Continue without security headers rather than crash the response

                await send(message)

            await self.app(scope, receive, send_wrapper)

        except Exception as e:
            # Alleen de logger (met traceback via exc_info). Tot 2026-10-08 schreef dit blok ook
            # bij elke fout een traceback naar een tijdelijk bestand: onbegrensd en buiten de
            # logpijplijn (plan nazorg, overige punten).
            logger.error(
                "Security middleware error: %s: %s", type(e).__name__, e, exc_info=True
            )
            # Log security error
            self.security_manager._log_security_event(
                "middleware_error",
                ThreatLevel.HIGH,
                client_ip,
                None,
                request.url.path,
                f"Security middleware error: {type(e).__name__}: {str(e)}",
            )

            # Only send error response if response hasn't started yet
            if not response_started:
                try:
                    # Send a proper error response instead of hanging
                    response = JSONResponse(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={
                            "error": "Internal server error",
                            "message": "An unexpected error occurred",
                        },
                    )
                    await response(scope, receive, send)
                except Exception:
                    pass  # Last resort: nothing we can do

    @property
    def ip_reputation(self) -> IpReputation:
        """De meegegeven IP-reputatie, anders de gedeelde van dit proces (per aanvraag
        opgezocht, zodat een vervangen instantie meteen geldt)."""
        return self._ip_reputation or get_ip_reputation()

    @staticmethod
    def _blokkade_response(seconden: int) -> JSONResponse:
        """403 met Retry-After: een blokkade is geen rate limit, dus geen 429."""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "IP blocked",
                "message": "Your IP has been temporarily blocked due to suspicious activity",
                "retry_after": seconden,
            },
            headers={"Retry-After": str(seconden)},
        )

    @staticmethod
    def _token_uit_verzoek(request: Request) -> str | None:
        """Het RUWE token uit de Authorization-header of het cookie, anders None."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:] or None
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            return cookie_token.strip().strip('"') or None
        return None

    #: Routes die een geblokkeerd adres WEL bereikt: het CSRF-token en de twee loginroutes.
    #: Zonder deze kon een beheerder op een geblokkeerd adres nooit een token krijgen en dus
    #: nooit deblokkeren. De loginroute zelf geeft daar alleen een beheerder een token
    #: (`router_login.py`, `ip_blokkade_seconden`); voor de rest blijft het een 403. Raden van
    #: wachtwoorden blijft begrensd door de lockout (5 pogingen) en de rate limit (5/min).
    INLOGPADEN: frozenset[tuple[str, str]] = frozenset(
        {
            ("GET", "/api/v1/auth/csrf-token"),
            ("POST", "/api/v1/auth/login"),
            ("POST", "/api/v1/auth/token"),
        }
    )

    @classmethod
    def _is_inlogpad(cls, scope: "Scope") -> bool:
        return (str(scope.get("method", "")).upper(), str(scope.get("path", ""))) in cls.INLOGPADEN

    async def _is_admin_token(self, request: Request) -> bool:
        """Draagt dit verzoek een geldig token van een ACTIEVE beheerder? Dan geen IP-blokkade.

        Eerder las deze functie de claims `roles`, `role` en `is_superuser`. Het token dat de
        login echt uitgeeft bevat die niet (wel `sub`, `email`, `tenant_id`, `role_ids`,
        `scopes`, `jti`), dus de vrijstelling werkte nooit (acceptant ronde 3, N3). En `scopes`
        draagt bewust geen `admin:all` meer (ADR-036 OP-186).

        Daarom dezelfde weg als elke route: `_get_user_from_token` -- handtekening en verloop,
        ingetrokken token (`jti`), de gebruiker uit de database met zijn rollen -- en dan
        `is_admin`. Een vervalst, verlopen of ingetrokken token, of een rol die na uitgifte is
        afgenomen, geeft dus GEEN vrijstelling. Elke fout geeft `False` (fail-closed: geblokkeerd
        blijft geblokkeerd).
        """
        token = self._token_uit_verzoek(request)
        if not token:
            return False
        from fastapi import HTTPException

        from src.core.auth.dependencies import _get_user_from_token, is_admin
        from src.core.database.database import db_manager

        try:
            async with db_manager.get_session() as db:
                gebruiker = await _get_user_from_token(token, db)
        except HTTPException:
            return False
        except Exception as exc:  # noqa: BLE001 - fail-closed, met reden in de log
            logger.warning(
                "Beheerderscontrole voor de IP-blokkade mislukt: %s: %s", type(exc).__name__, exc
            )
            return False
        return bool(getattr(gebruiker, "is_active", True)) and bool(is_admin(gebruiker))

    def _is_development_mode(self) -> bool:
        """Check if running in development mode (or test mode)."""
        return os.getenv("ENVIRONMENT", "development").lower() in [
            "development",
            "dev",
            "local",
            "test",  # CI sets ENVIRONMENT=test; IP allowlist must not run in test mode
        ]

    @staticmethod
    def _gematcht_routesjabloon(request: Request) -> str | None:
        """Het sjabloon van de route die dit verzoek matcht (FULL voor PARTIAL), anders None."""
        app = request.scope.get("app")
        routes = getattr(app, "routes", None)
        if not routes:
            return None
        scope = dict(request.scope)
        partial_path: str | None = None
        for route in routes:
            match, _child = route.matches(scope)
            if match == Match.FULL:
                return str(getattr(route, "path", ""))
            if match == Match.PARTIAL and partial_path is None:
                partial_path = str(getattr(route, "path", ""))
        return partial_path

    @staticmethod
    def _door_gebruiker_geleverd(request: Request) -> list[str]:
        """Queryparameters (naam en waarde) en padparameterwaarden van dit verzoek.

        Dit is wat de dreigingsdetectie op SQL-injectie scant. Het vaste deel van het
        routesjabloon hoort er niet bij: `/agents/create` of `/{id}/delete` is geen invoer.
        """
        waarden: list[str] = []
        for naam, waarde in request.query_params.multi_items():
            waarden.extend((naam, waarde))
        app = request.scope.get("app")
        routes = getattr(app, "routes", None) or []
        scope = dict(request.scope)
        for route in routes:
            match, kind_scope = route.matches(scope)
            if match == Match.FULL:
                padparameters = kind_scope.get("path_params", {}) or {}
                waarden.extend(str(w) for w in padparameters.values())
                break
        return waarden

    @staticmethod
    def _is_admin_route(endpoint: str, request: Request) -> bool:
        """True als het ROUTESJABLOON (niet het verzoekpad) `admin` als segment bevat.

        Een padparameter die de waarde `admin` krijgt mag het niveau niet veranderen: dan zou
        een gewone gebruiker de ADMIN-takken van /system en /autonomous omzeilen. De substring
        is alleen een snelle voorfilter; de beslissing komt van de gematchte route. Een pad dat
        op geen route matcht (404) geldt niet als admin-pad.
        """
        if "/admin" not in endpoint:
            return False
        sjabloon = SecurityMiddleware._gematcht_routesjabloon(request)
        return sjabloon is not None and "admin" in sjabloon.split("/")

    @staticmethod
    def _is_beheerroute(endpoint: str, request: Request) -> bool:
        """True als het ROUTESJABLOON onder `/api/v1/system/` of `/api/v1/autonomous/` valt.

        Zelfde mechaniek als `_is_admin_route`: een padparameter met de waarde `system` of
        `autonomous` op een gewone route mag niets veranderen. Tokens uit jwt_handler dragen geen
        security_level-claim; ADMIN eisen weigerde daarom elke gebruiker met 401. De middleware
        vraagt dus alleen authenticatie; de beheerdersrol wordt per route gecontroleerd (403),
        bewaakt door tests/architecture/test_admin_routes_hebben_een_rolcontrole.py.
        """
        if "/system" not in endpoint and "/autonomous" not in endpoint:
            return False
        sjabloon = SecurityMiddleware._gematcht_routesjabloon(request)
        return sjabloon is not None and sjabloon.startswith(BEHEER_PREFIXEN)

    def _determine_security_level(self, endpoint: str, request: Request) -> SecurityLevel:
        """Determine required security level for endpoint"""
        # Public endpoints (Check central registry)
        if PublicEndpointRegistry.is_public(endpoint):
            logger.debug(f"[SECURITY] Public endpoint access: {endpoint}")
            return SecurityLevel.PUBLIC

        # Tot 2026-10-08 stond hier: elk pad met "/orchestrator" erin is PUBLIC ("for
        # development", ingevoerd 2025-10-28 zonder ADR). De routes zelf vragen allang een
        # gebruiker, en de substring maakte ook een padparameter met de waarde "orchestrator"
        # publiek. Nu de standaard: authenticatie.

        # /admin: alleen authenticatie hier. Tokens uit jwt_handler dragen geen security_level-claim
        # en zijn dus altijd AUTHENTICATED; ADMIN eisen weigerde elke gebruiker met 401. De rol
        # wordt per route gecontroleerd (403); bewaakt door
        # tests/architecture/test_admin_routes_hebben_een_rolcontrole.py.
        if self._is_admin_route(endpoint, request):
            return SecurityLevel.AUTHENTICATED

        # /api/v1/system en /api/v1/autonomous: net als /admin alleen authenticatie hier; de rol
        # wordt per route gecontroleerd (403). De oude substringtest op "/system", "/config" en
        # "/autonomous" is vervallen: hij gaf ADMIN en weigerde dus iedereen met 401.
        if self._is_beheerroute(endpoint, request):
            return SecurityLevel.AUTHENTICATED

        # Phase 2-3 AI operations - authorized access (collaboration, phase2)
        # NOTE: /workflows removed - uses standard AUTHENTICATED level like /agents
        if any(pattern in endpoint for pattern in ["/phase2", "/collaboration"]):
            return SecurityLevel.AUTHORIZED

        # Default: require authentication
        return SecurityLevel.AUTHENTICATED

    def _extract_user_id(self, request: Request) -> str | None:
        """Extract user ID from request"""
        token = None
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

        # Phase 5: Fallback to cookie-backed auth
        if not token:
            cookie_token = request.cookies.get("access_token")
            if cookie_token:
                token = cookie_token.strip().strip('"')

        if token:
            try:
                payload = _jwt_handler.verify_token(token)
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "JWT input validation failed in _extract_user_id: %s", type(exc).__name__
                )
                payload = None
            if payload:
                return cast(str | None, payload.get("sub"))

        # Check for API key or other auth methods
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # In production, validate API key and return associated user
            return f"api_user_{api_key[:8]}"

        return None

    def _check_authentication(
        self, request: Request, required_level: SecurityLevel
    ) -> dict[str, bool | str]:
        """Check if request is properly authenticated for required level"""
        auth_header = request.headers.get("Authorization")
        # Phase 5: Cookie-backed auth -- also check access_token cookie
        access_token_cookie = request.cookies.get("access_token")

        if not auth_header and not access_token_cookie:
            return {
                "valid": False,
                "message": "SECURITY_MIDDLEWARE_ACTIVE: Missing Authorization header",
            }

        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif access_token_cookie:
            token = access_token_cookie.strip().strip('"')

        if not token:
            return {"valid": False, "message": "Invalid Authorization header format"}

        # Development mode: Allow special development token but still require authentication
        if self._is_development_mode() and token == "dev-token-safe-development":
            if required_level == SecurityLevel.ADMIN:
                return {
                    "valid": False,
                    "message": "Admin access requires real authentication even in development",
                }
            return {
                "valid": True,
                "message": "Development token accepted",
                "user_id": "dev_user",
                "security_level": SecurityLevel.AUTHENTICATED.value,
            }

        # Production authentication: Verify JWT token via canonical jwt_handler (CG-007)
        try:
            payload = _jwt_handler.verify_token(token)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "JWT input validation failed in _check_authentication: %s", type(exc).__name__
            )
            return {"valid": False, "message": "Invalid token format"}

        if not payload:
            return {"valid": False, "message": "Invalid or expired token"}

        # Check security level
        raw_level = payload.get("security_level")
        if raw_level is None:
            role = str(payload.get("role", "")).lower()
            roles = [str(r).lower() for r in payload.get("roles", [])]
            is_superuser = bool(payload.get("is_superuser", False))
            if role == "admin" or "admin" in roles or is_superuser:
                token_level = SecurityLevel.ADMIN
            elif role == "curator" or "curator" in roles:
                token_level = SecurityLevel.AUTHORIZED
            else:
                token_level = SecurityLevel.AUTHENTICATED
        else:
            try:
                token_level = SecurityLevel(raw_level)
            except ValueError:
                logger.warning("Unknown security_level claim value: %s", raw_level)
                token_level = SecurityLevel.AUTHENTICATED

        required_level_value = {
            SecurityLevel.PUBLIC: 0,
            SecurityLevel.AUTHENTICATED: 1,
            SecurityLevel.AUTHORIZED: 2,
            SecurityLevel.ADMIN: 3,
            SecurityLevel.SYSTEM: 4,
        }

        if required_level_value[token_level] < required_level_value[required_level]:
            return {
                "valid": False,
                "message": f"Insufficient permissions. Required: {required_level.value}",
            }

        return {
            "valid": True,
            "message": "Authenticated",
            "user_id": payload.get("sub"),
        }


def create_security_middleware(
    *, enable_security: bool = True
) -> Callable[["ASGIApp"], SecurityMiddleware]:
    """
    Factory function to create security middleware with keyword-only parameters.

    Args:
        enable_security: Keyword-only parameter to control security features

    Returns:
        Middleware factory function compliant with FastAPI add_middleware API

    Example:
        app.add_middleware(
            create_security_middleware(enable_security=True)
        )
    """

    def middleware(app: "ASGIApp") -> SecurityMiddleware:
        return SecurityMiddleware(app, enable_security=enable_security)

    return middleware


def validate_security_middleware_instantiation() -> dict[str, bool | str]:
    """
    Validate that SecurityMiddleware can be properly instantiated.

    This function should be called during application startup to ensure
    the middleware configuration is correct before accepting traffic.

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "message": str,
            "security_manager_available": bool,
            "instantiation_test": str
        }

    Raises:
        RuntimeError: If critical validation failures occur
    """
    from fastapi import FastAPI

    validation_results: dict[str, bool | str] = {
        "valid": True,
        "message": "Security middleware validation passed",
        "security_manager_available": False,
        "instantiation_test": "not_tested",
    }

    try:
        # Test 1: Verify security manager is available
        security_manager = get_security_manager()
        if security_manager:
            validation_results["security_manager_available"] = True
            logger.info("Security manager availability: OK")
        else:
            validation_results["valid"] = False
            validation_results["message"] = "Security manager not available"
            logger.error("Security manager validation FAILED")
            return validation_results

        # Test 2: Verify middleware can be instantiated with keyword argument
        test_app = FastAPI()
        try:
            SecurityMiddleware(test_app, enable_security=True)
            validation_results["instantiation_test"] = "keyword_argument_ok"
            logger.info("Security middleware instantiation (keyword): OK")
        except TypeError as e:
            validation_results["valid"] = False
            validation_results["instantiation_test"] = f"keyword_argument_failed: {str(e)}"
            validation_results["message"] = "Middleware instantiation with keyword argument failed"
            logger.error(f"Security middleware instantiation FAILED: {e}")
            return validation_results

        # Test 3: Verify positional argument is rejected (should fail)
        try:
            # This should raise TypeError due to keyword-only parameter
            cast(  # TODO(TYPE): replace Any with concrete type
                Any, SecurityMiddleware
            )(test_app, True)  # Test: positional arg must be rejected
            # If we get here, the enforcement failed
            validation_results["valid"] = False
            validation_results["instantiation_test"] = "positional_not_rejected"
            validation_results["message"] = "CRITICAL: Keyword-only enforcement not working"
            logger.error("CRITICAL: Positional argument was not rejected by middleware")
        except TypeError:
            # This is expected - positional argument should be rejected
            logger.info("Security middleware keyword-only enforcement: OK")
            validation_results["instantiation_test"] = "keyword_only_enforced"

        return validation_results

    except Exception as e:
        logger.error(f"Security middleware validation exception: {e}")
        validation_results["valid"] = False
        validation_results["message"] = f"Validation exception: {str(e)}"
        return validation_results


# Backward compatibility alias for main.py
UnifiedSecurityMiddleware = SecurityMiddleware
