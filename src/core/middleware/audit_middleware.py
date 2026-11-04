"""
SC-6.1: Audit Logging Middleware
Logs all API requests with user, action, and resource information.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import Awaitable, Callable, Mapping

from fastapi import Request
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.database.database import Base
from src.core.middleware.tenant_context import get_tenant_id
from src.core.shared.limiet_sleutel import afzender_adres

logger = logging.getLogger(__name__)


class RequestAuditLog(Base):  # type: ignore[misc]
    """Database model for audit logs."""

    __tablename__ = "request_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Request identification
    request_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    timestamp = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    # User info
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Request details
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    query_params: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Response info
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Additional context
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action = mapped_column(String(100), nullable=True)  # e.g., "create_user", "delete_workflow"
    resource_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # e.g., "user", "workflow"
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Changes (for mutations)
    changes: Mapped[object | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<RequestAuditLog({self.method} {self.path} by user {self.user_id})>"


class AuditLoggingMiddleware:
    """
    SC-6.1: Middleware for comprehensive audit logging (pure ASGI).

    Logs:
    - All API requests with timing
    - User identification
    - Request/response metadata
    - Action classification

    CRITICAL FIX: Replaced BaseHTTPMiddleware with pure ASGI pattern
    to fix MissingGreenlet errors caused by anyio task groups not
    propagating greenlet context (Starlette 0.49.3+).
    """

    EXCLUDED_PATHS = [
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    ]

    # Map HTTP methods to actions
    METHOD_ACTIONS = {
        "GET": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }

    _SENSITIVE_PARAM_KEYS = frozenset(
        {"token", "password", "api_key", "secret", "access_token", "refresh_token", "client_secret"}
    )

    def __init__(
        self,
        app: ASGIApp,
        log_to_db: bool = False,
        db_session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        self.app = app
        self.log_to_db = log_to_db
        self.db_session_factory = db_session_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Pass through non-HTTP requests (lifespan, websocket) unchanged.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(p) for p in self.EXCLUDED_PATHS):
            await self.app(scope, receive, send)
            return

        # Generate request ID
        request_id = str(uuid.uuid4())
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Capture start time
        start_time = time.perf_counter()

        # Track response status via send wrapper
        response_started = False
        response_status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started, response_status_code
            if message["type"] == "http.response.start":
                response_started = True
                response_status_code = message.get("status", 500)
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        # Process request with proper error handling
        try:
            await self.app(scope, receive, send_wrapper)

            # Calculate response time
            response_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract user info (if available)
            user_id, tenant_id, user_email = self._extract_user_info(request)

            # Build audit entry
            audit_entry = {
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "user_email": user_email,
                "tenant_id": tenant_id,
                "method": request.method,
                "path": path,
                "query_params": self._mask_query_params(str(request.query_params))
                if request.query_params
                else None,
                "status_code": response_status_code,
                "response_time_ms": response_time_ms,
                "ip_address": afzender_adres(request),
                "user_agent": request.headers.get("user-agent"),
                "action": self._classify_action(request),
                "resource_type": self._extract_resource_type(path),
                "resource_id": self._extract_resource_id(path),
            }

            # Log to stdout
            logger.info(
                "AUDIT %s %s [%s] %dms",
                audit_entry["method"],
                audit_entry["path"],
                audit_entry["status_code"],
                audit_entry["response_time_ms"],
                extra={
                    "tenant_id": audit_entry["tenant_id"],
                    "user_id": audit_entry["user_id"],
                    "request_id": audit_entry["request_id"],
                },
            )

            # Write to database (best-effort)
            await self._write_to_db(audit_entry)

        except Exception as exc:
            # Calculate response time
            response_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract user info (if available)
            user_id, tenant_id, user_email = self._extract_user_info(request)

            # Build audit entry for error
            audit_entry = {
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "user_email": user_email,
                "tenant_id": tenant_id,
                "method": request.method,
                "path": path,
                "query_params": self._mask_query_params(str(request.query_params))
                if request.query_params
                else None,
                "status_code": "ERROR",
                "response_time_ms": response_time_ms,
                "ip_address": afzender_adres(request),
                "user_agent": request.headers.get("user-agent"),
                "action": self._classify_action(request),
                "resource_type": self._extract_resource_type(path),
                "resource_id": self._extract_resource_id(path),
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

            # Log error to stdout
            logger.error(
                "AUDIT_ERROR %s %s [ERROR] %dms %s: %s",
                audit_entry["method"],
                audit_entry["path"],
                audit_entry["response_time_ms"],
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={
                    "tenant_id": audit_entry["tenant_id"],
                    "user_id": audit_entry["user_id"],
                    "request_id": audit_entry["request_id"],
                },
            )

            # Write to database (best-effort)
            await self._write_to_db(audit_entry)

            # Re-raise the exception
            raise

    def _mask_query_params(self, params: str) -> str | None:
        if not params:
            return None
        # params is str representation van QueryParams: "key=val&key2=val2"
        masked = []
        for part in params.split("&"):
            if "=" in part:
                k, _, v = part.partition("=")
                masked.append(
                    f"{k}=[REDACTED]" if k.lower() in self._SENSITIVE_PARAM_KEYS else part
                )
            else:
                masked.append(part)
        return "&".join(masked) if masked else None

    def _classify_action(self, request: Request) -> str:
        """Classify the action based on method and path."""
        base_action = self.METHOD_ACTIONS.get(request.method, "unknown")
        resource = self._extract_resource_type(request.url.path)
        return f"{base_action}_{resource}" if resource else base_action

    def _extract_resource_type(self, path: str) -> str | None:
        """Extract resource type from path."""
        parts = [
            p for p in path.split("/") if p and not p.startswith("api") and not p.startswith("v")
        ]
        return parts[0] if parts else None

    def _extract_resource_id(self, path: str) -> str | None:
        """Extract resource ID from path."""
        parts = path.split("/")
        for i, part in enumerate(parts):
            if part.isdigit():
                return part
            # UUID pattern
            if len(part) == 36 and "-" in part:
                return part
        return None

    def _extract_user_info(self, request: Request) -> tuple[Optional[int], str, Optional[str]]:
        """Extract user_id, tenant_id, and user_email from request state.

        Tenant resolution order (FA-001 SP-SEC-001):
        1. request.state.user.tenant_id (set by auth middleware for authenticated requests)
        2. get_tenant_id() ContextVar (set by TenantMiddleware -- fallback for public endpoints)
        3. "0" (system namespace -- unauthenticated requests without tenant context)
        """
        user_id = None
        tenant_id = "0"
        user_email = None

        if hasattr(request.state, "user") and request.state.user:
            raw_user_id = getattr(request.state.user, "id", None)
            if isinstance(raw_user_id, int):
                user_id = raw_user_id
            elif isinstance(raw_user_id, str) and raw_user_id.isdigit():
                user_id = int(raw_user_id)

            raw_tenant = getattr(request.state.user, "tenant_id", None)
            if isinstance(raw_tenant, (int, str)):
                tenant_id = str(raw_tenant)

            raw_email = getattr(request.state.user, "email", None)
            if isinstance(raw_email, str):
                user_email = raw_email
        else:
            # Fallback: read from ContextVar set by TenantMiddleware (FA-001 SP-SEC-001)
            ctx_tenant_id = get_tenant_id()
            if ctx_tenant_id is not None:
                tenant_id = str(ctx_tenant_id)

        return user_id, tenant_id, user_email

    async def _write_to_db(self, audit_entry: Mapping[str, object]) -> None:
        """Write the audit entry to the database in a best-effort block."""
        if not (self.log_to_db and self.db_session_factory):
            return

        from src.core.utils.best_effort import best_effort

        async with best_effort("request audit log DB write"):
            async with self.db_session_factory() as session:
                status_code = audit_entry["status_code"]
                if status_code == "ERROR":
                    status_code = 500

                db_entry = RequestAuditLog(
                    request_id=audit_entry["request_id"],
                    user_id=audit_entry["user_id"],
                    user_email=audit_entry.get("user_email"),
                    tenant_id=audit_entry["tenant_id"],
                    method=audit_entry["method"],
                    path=audit_entry["path"],
                    query_params=audit_entry["query_params"],
                    status_code=status_code,
                    response_time_ms=audit_entry["response_time_ms"],
                    ip_address=audit_entry["ip_address"],
                    user_agent=audit_entry["user_agent"],
                    action=audit_entry["action"],
                    resource_type=audit_entry["resource_type"],
                    resource_id=audit_entry["resource_id"],
                )
                session.add(db_entry)
                await session.commit()


async def get_audit_logs(
    db: AsyncSession,
    tenant_id: int | str,
    user_id: int | None = None,
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Query audit logs strictly scoped to tenant, with bounded limit and PII sanitized.

    Conforms to backend-patterns rule 5 (pagination limits) and rule 11 (sanitized output).
    """
    if not tenant_id:
        raise ValueError("tenant_id is strictly required for audit log retrieval")

    from sqlalchemy import select

    # Clamp limit strictly between 1 and 100
    bounded_limit = min(max(1, limit), 100)
    safe_offset = max(0, offset)

    query = select(RequestAuditLog).where(RequestAuditLog.tenant_id == str(tenant_id))
    if user_id is not None:
        query = query.where(RequestAuditLog.user_id == user_id)
    if action is not None:
        query = query.where(RequestAuditLog.action == action)
    query = query.order_by(RequestAuditLog.timestamp.desc()).limit(bounded_limit).offset(safe_offset)

    result = await db.execute(query)
    entries = result.scalars().all()

    # Sanitize entries: exclude raw PII (user_email, ip_address, user_agent)
    return [
        {
            "id": entry.id,
            "request_id": entry.request_id,
            "tenant_id": entry.tenant_id,
            "user_id": entry.user_id,
            "method": entry.method,
            "path": entry.path,
            "status_code": entry.status_code,
            "response_time_ms": entry.response_time_ms,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        }
        for entry in entries
    ]
