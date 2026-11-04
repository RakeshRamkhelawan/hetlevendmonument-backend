"""
VIBE_BE_002: WebSocket Authentication Module

Provides JWT-based authentication for WebSocket connections used in
the VIBE Workflow Builder real-time streaming.

Features:
- JWT validation in WebSocket handshake
- Token extraction from cookie, subprotocol, or Authorization header (never query param)
- Tenant isolation
- Connection tracking with user context
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

from fastapi import WebSocket, WebSocketException, status

from src.core.auth.jwt_handler import jwt_handler
from src.core.auth.types import VerifiedJWTPayload
from src.core.middleware.tenant_context import set_tenant_id

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


def tenant_from_claim(ruw: object) -> int | None:
    """De tenant uit een JWT-claim: een positief geheel getal, of None.

    Gedeeld door de hele websocketlaag. `int(claim)` maakte van `true` tenant 1 en van `1.9` ook
    tenant 1, en gaf op een tekst als het superscript-twee een ValueError in plaats van een
    weigering (security-review 2026-10-05).
    """
    if isinstance(ruw, bool):
        return None
    if isinstance(ruw, int):
        return ruw if ruw > 0 else None
    if isinstance(ruw, str) and ruw.isascii() and ruw.isdigit():
        waarde = int(ruw)
        return waarde if waarde > 0 else None
    return None


async def account_is_active_for_ws(subject: str, tenant_id: int) -> bool:
    """Uitgeschakeld is uitgeschakeld, ook voor een WebSocket (gemeten 2026-10-12).

    Voor elke WebSocket-ingang die een token zelf leest. Alleen `ACTIEF` is `True`: een
    uitgezet account en een niet te controleren status (database weg, `OSError`, time-out)
    weigeren allebei. De logica staat in `src.core.auth.account_status`.
    """
    from src.core.auth.account_status import AccountStatus, haal_account_status

    return await haal_account_status(subject, tenant_id) is AccountStatus.ACTIEF


async def token_mag_op_een_websocket(payload: Mapping[str, object]) -> bool:
    """De ENE vraag voor elke WebSocket-ingang die een token zelf leest.

    `True` alleen voor een medewerkerstoken van een ingeschakeld account. Weigert: een
    portaaltoken (portaalgebruikers horen niet op deze WebSockets; hun `sub` is een
    `portal_users`-nummer en werd getoetst tegen `users`: gemeten 2026-10-13 liet dat een
    portaalgebruiker binnen als medewerker met hetzelfde nummer), een onbruikbare tenantclaim, en
    een uitgezet of niet te controleren account.
    """
    from src.core.auth.account_status import is_portal_token, token_is_ingetrokken

    if is_portal_token(payload):
        return False
    tenant_id = tenant_from_claim(payload.get("tenant_id"))
    if tenant_id is None:
        return False
    # Ingetrokken is ingetrokken, ook op een WebSocket: losse intrekking (uitloggen) EN een nieuw wachtwoord
    # (alle eerder uitgegeven tokens). Op deze ene plek, zodat elke ingang die deze vraag stelt haar erft.
    if await token_is_ingetrokken(payload):
        return False
    subject = str(payload.get("sub") or payload.get("user_id") or "")
    return await account_is_active_for_ws(subject, tenant_id)


@dataclass
class AuthenticatedUser:
    """Authenticated user information from JWT."""

    user_id: str
    tenant_id: int
    email: str | None = None
    roles: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = []


@dataclass
class AuthenticatedConnection:
    """WebSocket connection with authentication context."""

    websocket: WebSocket
    user: AuthenticatedUser
    connected_at: datetime
    last_activity: datetime
    messages_sent: int = 0
    messages_received: int = 0


# ============================================================================
# WebSocket Authentication
# ============================================================================


class WebSocketAuthenticator:
    """
    Handles JWT authentication for WebSocket connections.

    Usage:
        authenticator = WebSocketAuthenticator()

        @router.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            user = await authenticator.authenticate(websocket)
            if not user:
                return  # Connection already closed

            # Use user.tenant_id for filtering, etc.
    """

    def __init__(self) -> None:
        self.jwt_handler = jwt_handler
        self._connections: dict[str, AuthenticatedConnection] = {}

    async def authenticate(
        self, websocket: WebSocket, required_roles: list[str] | None = None
    ) -> AuthenticatedUser | None:
        """
        Authenticate WebSocket connection using JWT.

        Token can be provided via:
        1. HTTP-only cookie (canonical)
        2. Sec-WebSocket-Protocol header
        3. Authorization: Bearer header

        Args:
            websocket: FastAPI WebSocket instance
            required_roles: Optional list of required roles

        Returns:
            AuthenticatedUser if valid, None if authentication failed
        """
        token = self._extract_token(websocket)

        if not token or not isinstance(token, str):
            await self._close_with_error(websocket, 4001, "No authentication token provided")
            return None

        # Verify JWT
        payload = self.jwt_handler.verify_token(token)

        if not payload:
            await self._close_with_error(websocket, 4002, "Invalid or expired token")
            return None

        # Extract user info from payload
        user = self._payload_to_user(payload)

        if not user:
            await self._close_with_error(websocket, 4003, "Invalid token payload")
            return None

        # Check required roles
        if required_roles:
            if not any(role in user.roles for role in required_roles):
                await self._close_with_error(websocket, 4004, "Insufficient permissions")
                return None

        if not await token_mag_op_een_websocket(cast(Mapping[str, object], payload)):
            await self._close_with_error(websocket, 4005, "Account not allowed on a websocket")
            return None

        # Set tenant context
        set_tenant_id(user.tenant_id)

        # Accept connection
        await websocket.accept()

        # Track connection
        connection = AuthenticatedConnection(
            websocket=websocket,
            user=user,
            connected_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        self._connections[user.user_id] = connection

        logger.info("WebSocket authenticated: user=%s, tenant=%s", user.user_id, user.tenant_id)

        return user

    async def authenticate_connected_user(
        self, websocket: WebSocket, required_roles: list[str] | None = None
    ) -> AuthenticatedUser | None:
        """
        Authenticate an ALREADY ACCEPTED WebSocket connection.

        Use this when you must call `await websocket.accept()` before authentication
        (e.g., to avoid Starlette 403 Forbidden issues).
        """
        token = self._extract_token(websocket)

        if not token:
            await self._close_with_error(websocket, 4001, "No authentication token provided")
            return None

        # Verify JWT
        payload = self.jwt_handler.verify_token(token)

        if not payload:
            await self._close_with_error(websocket, 4002, "Invalid or expired token")
            return None

        # Extract user info from payload
        user = self._payload_to_user(payload)

        if not user:
            await self._close_with_error(websocket, 4003, "Invalid token payload")
            return None

        # Check required roles
        if required_roles:
            if not any(role in user.roles for role in required_roles):
                await self._close_with_error(websocket, 4004, "Insufficient permissions")
                return None

        if not await token_mag_op_een_websocket(cast(Mapping[str, object], payload)):
            await self._close_with_error(websocket, 4005, "Account not allowed on a websocket")
            return None

        # Set tenant context
        set_tenant_id(user.tenant_id)

        # Track connection
        connection = AuthenticatedConnection(
            websocket=websocket,
            user=user,
            connected_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        self._connections[user.user_id] = connection

        logger.info(
            "WebSocket authenticated (post-accept): user=%s, tenant=%s",
            user.user_id,
            user.tenant_id,
        )

        return user

    def extract_token(self, websocket: WebSocket) -> str | None:
        """Public entry point for the three allowed token sources.

        Use this from endpoints that need the raw token (for example to hand it to
        a connection manager) instead of adding a ``token: str = Query(...)``
        parameter -- that reintroduces the query-string leak SEC-AGT-004 removed.
        Enforced by tests/architecture/test_websocket_no_query_param_token.py.
        """
        return self._extract_token(websocket)

    def _extract_token(self, websocket: WebSocket) -> str | None:
        """Extract JWT token from WebSocket request.

        SEC-AGT-004: the ``?token=`` query-param method was removed. OWASP ASVS V7
        forbids session identifiers in URL query strings -- they leak into access logs,
        browser history, proxy logs and the Referer header. Tokens must arrive via the
        HTTP-only cookie (canonical), the Sec-WebSocket-Protocol subprotocol, or the
        Authorization header.
        """
        # Method 1: Cookie (canonical for Phase 6)
        token = websocket.cookies.get("access_token")
        if token:
            logger.debug("WS: token found in cookie")
            return token

        # Method 2: Sec-WebSocket-Protocol header
        protocols = websocket.scope.get("subprotocols", [])
        for i, protocol in enumerate(protocols):
            if protocol == "access_token" and i + 1 < len(protocols):
                logger.debug("WS: token found in subprotocol")
                return str(protocols[i + 1])

        # Method 3: Authorization header
        headers = dict(websocket.scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        if auth_header.startswith("Bearer "):
            logger.debug("WS: token found in Authorization header")
            return str(auth_header[7:])

        logger.debug("WS: no token found in cookie, subprotocol, or header")
        return None

    def _payload_to_user(self, payload: VerifiedJWTPayload) -> AuthenticatedUser | None:
        """Convert JWT payload to AuthenticatedUser."""
        try:
            user_id = payload.get("sub") or payload.get("user_id")
            if not user_id:
                return None

            tenant_id = tenant_from_claim(payload.get("tenant_id"))
            if tenant_id is None:
                logger.warning("JWT missing or unusable tenant_id claim")
                return None

            return AuthenticatedUser(
                user_id=str(user_id),
                email=payload.get("email"),
                tenant_id=tenant_id,
                roles=payload.get("roles", []),
            )
        except Exception as e:
            logger.warning("Failed to parse JWT payload: %s: %s", type(e).__name__, e)
            return None

    async def _close_with_error(self, websocket: WebSocket, code: int, reason: str) -> None:
        """Close WebSocket with error code and reason."""
        logger.warning("WebSocket auth failed: %s", reason)
        try:
            await websocket.close(code=code, reason=reason)
        except Exception:
            pass  # Connection may already be closed

    def disconnect(self, user_id: str) -> None:
        """Remove connection from tracking."""
        if user_id in self._connections:
            del self._connections[user_id]
            logger.info("WebSocket disconnected: user=%s", user_id)

    def get_connection(self, user_id: str) -> AuthenticatedConnection | None:
        """Get connection by user ID."""
        return self._connections.get(user_id)

    def get_tenant_connections(self, tenant_id: int) -> list[AuthenticatedConnection]:
        """Get all connections for a tenant."""
        return [conn for conn in self._connections.values() if conn.user.tenant_id == tenant_id]

    @property
    def active_connections(self) -> int:
        """Number of active authenticated connections."""
        return len(self._connections)


# ============================================================================
# Global Instance
# ============================================================================

websocket_auth = WebSocketAuthenticator()


# ============================================================================
# Dependency for FastAPI
# ============================================================================


async def get_ws_user(websocket: WebSocket) -> AuthenticatedUser:
    """
    FastAPI dependency for WebSocket authentication.

    Usage:
        @router.websocket("/ws")
        async def endpoint(
            websocket: WebSocket,
            user: AuthenticatedUser = Depends(get_ws_user)
        ):
            # user is authenticated

    Raises:
        WebSocketException if authentication fails
    """
    user = await websocket_auth.authenticate(websocket)
    if not user:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required"
        )
    return user
