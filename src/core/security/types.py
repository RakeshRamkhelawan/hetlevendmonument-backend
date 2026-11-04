"""Shared type definitions for the security layer.

These Protocols and enums describe runtime-checkable security contracts
without introducing circular imports between middleware, ORM models, and
validators.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class SecurityEventType(str, Enum):
    """Security event types for audit logging (OWASP A09: Security Logging Failures)"""

    # Authentication Events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_GENERATED = "token_generated"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    TOKEN_REVOKED = "token_revoked"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_FAILED = "mfa_failed"

    # Authorization Events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"
    PERMISSION_CHANGED = "permission_changed"

    # Data Access Events
    DATA_READ = "data_read"
    DATA_CREATED = "data_created"
    DATA_UPDATED = "data_updated"
    DATA_DELETED = "data_deleted"
    DATA_EXPORTED = "data_exported"
    BULK_OPERATION = "bulk_operation"

    # Security Incidents
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    CSRF_ATTEMPT = "csrf_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    IP_BLOCKED = "ip_blocked"
    IP_UNBLOCKED = "ip_unblocked"

    # System Events
    CONFIG_CHANGED = "config_changed"
    SYSTEM_ERROR = "system_error"
    SERVICE_STARTED = "service_started"
    SERVICE_STOPPED = "service_stopped"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"

    # Tenant Events
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"
    TENANT_DELETED = "tenant_deleted"
    TENANT_SUSPENDED = "tenant_suspended"
    CROSS_TENANT_ACCESS = "cross_tenant_access"


class ThreatLevel(str, Enum):
    """Threat severity levels for security events"""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Status of security alerts"""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@runtime_checkable
class HasTenantId(Protocol):
    """Protocol for objects that carry a tenant identifier.

    Used by RLS validators to accept any object with a ``tenant_id``
    attribute (SQLAlchemy models, dataclasses, or plain objects) without
    requiring a common base class.
    """

    tenant_id: int
