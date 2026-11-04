"""Security event constants and lightweight logging for ASGI middleware layers.

This module provides SecurityEvent constants and a logger-only log_security_event
for use in tenancy-layer middleware (quota, tenant). These callers do not have a
DB session available and only need the system-logger path.

For DB-backed audit logging, use:
    governance.services.audit_service.log_security_event(db=session, ...)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SecurityEvent:
    """Security event type constants for multi-tenant audit logging."""

    TENANT_CONTEXT_FAILED = "tenant_context_failed"
    CROSS_TENANT_ATTEMPT = "cross_tenant_access_attempt"
    TENANT_NOT_FOUND = "tenant_not_found"
    TENANT_SUSPENDED = "tenant_suspended"
    SUPERUSER_BYPASS = "superuser_bypass"
    QUOTA_EXCEEDED = "quota_exceeded"
    INVALID_JWT = "invalid_jwt"
    TOKEN_EXPIRED = "token_expired"
    RESOURCE_NOT_FOUND_404 = "resource_not_found_404"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    REGISTRATION_SUCCESS = "REGISTRATION_SUCCESS"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"


_SEVERITY_MAP: dict[str, str] = {
    SecurityEvent.CROSS_TENANT_ATTEMPT: "critical",
    SecurityEvent.QUOTA_EXCEEDED: "high",
    SecurityEvent.SUPERUSER_BYPASS: "low",
    SecurityEvent.INVALID_JWT: "high",
    SecurityEvent.TOKEN_EXPIRED: "medium",
    SecurityEvent.TENANT_CONTEXT_FAILED: "high",
    SecurityEvent.TENANT_NOT_FOUND: "high",
}


async def log_security_event(
    event_type: str,
    user_id: int | None = None,
    tenant_id: int | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    threat_level: str = "medium",
) -> None:
    """Log security event to system logs (no DB -- middleware callers only).

    Derives severity from event_type via _SEVERITY_MAP, falls back to threat_level.
    Does not write to the audit database -- for that, pass db= to
    governance.services.audit_service.log_security_event.
    """
    derived_level = _SEVERITY_MAP.get(event_type, threat_level)
    _msg = "SECURITY EVENT [%s]: %s | user_id=%s | tenant_id=%s | path=%s | method=%s | ip=%s | details=%s"
    _args = (
        derived_level.upper(),
        event_type,
        user_id,
        tenant_id,
        request_path,
        request_method,
        ip_address,
        details,
    )
    if derived_level == "critical":
        logger.error(_msg, *_args)
    elif derived_level in ["high", "medium"]:
        logger.warning(_msg, *_args)
    else:
        logger.info(_msg, *_args)
