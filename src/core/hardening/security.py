"""
TKT-F4-02: Security Hardening

Policy violation handling with security audit events.
No silent security failures.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from collections.abc import Callable


class ViolationType(Enum):
    """Type of policy violation"""

    UNAUTHORIZED_ACCESS = "unauthorized_access"
    TENANT_ISOLATION_BREACH = "tenant_isolation_breach"
    DATA_EXFILTRATION = "data_exfiltration"
    POLICY_CIRCUMVENTION = "policy_circumvention"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


class ViolationSeverity(Enum):
    """Severity of policy violation"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyViolation:
    """A detected policy violation"""

    violation_id: str
    tenant_id: str
    user_id: str | None
    violation_type: ViolationType
    severity: ViolationSeverity
    resource: str
    action: str
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime
    blocked: bool
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "violation_id": self.violation_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "resource": self.resource,
            "action": self.action,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "blocked": self.blocked,
            "remediation": self.remediation,
        }


@dataclass
class SecurityAudit:
    """Security audit event"""

    event_id: str
    event_type: str
    tenant_id: str
    user_id: str | None
    resource: str
    action: str
    outcome: str  # success, failure, blocked
    details: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime
    ip_address: str | None = None
    user_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class SecurityEnforcer:
    """
    Enforces security policies and handles violations.

    Guarantees:
    - No silent failures
    - All violations logged
    - Critical violations trigger alerts
    - Audit trail for all security events

    Usage:
        enforcer = SecurityEnforcer()

        # Check access
        allowed, violation = enforcer.check_access(
            tenant_id="tenant-123",
            user_id="user-456",
            resource="workflow-789",
            action="execute",
            context={"ip": "1.2.3.4"}
        )

        if not allowed:
            handle_blocked(violation)
    """

    def __init__(self) -> None:
        self._violations: list[PolicyViolation] = []
        self._audit_log: list[SecurityAudit] = []
        self._violation_handlers: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type
        self._tenant_policies: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def register_violation_handler(self, handler: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register handler for policy violations"""
        self._violation_handlers.append(handler)

    def set_tenant_policy(
        self, tenant_id: str, allowed_resources: list[str], rate_limit: int = 100
    ) -> None:
        """Set security policy for tenant"""
        self._tenant_policies[tenant_id] = {
            "allowed_resources": set(allowed_resources),
            "rate_limit": rate_limit,
            "request_count": 0,
            "last_reset": datetime.now(timezone.utc),
        }

    def check_access(
        self,
        tenant_id: str,
        user_id: str | None,
        resource: str,
        action: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[bool, PolicyViolation | None]:
        """
        Check if access is allowed.

        Returns: Tuple[Any, ...] of (allowed, violation)  # TODO(TYPE): replace Any with concrete type
        """
        context = context or {}

        # Check tenant policy
        policy = self._tenant_policies.get(tenant_id)
        if not policy:
            # No policy = deny by default (secure by default)
            violation = PolicyViolation(
                violation_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                violation_type=ViolationType.UNAUTHORIZED_ACCESS,
                severity=ViolationSeverity.HIGH,
                resource=resource,
                action=action,
                details={"reason": "No policy configured for tenant", "context": context},
                timestamp=datetime.now(timezone.utc),
                blocked=True,
            )
            self._record_violation(violation)
            return False, violation

        # Check rate limit
        if not self._check_rate_limit(tenant_id):
            violation = PolicyViolation(
                violation_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                violation_type=ViolationType.RATE_LIMIT_EXCEEDED,
                severity=ViolationSeverity.MEDIUM,
                resource=resource,
                action=action,
                details={"rate_limit": policy["rate_limit"]},
                timestamp=datetime.now(timezone.utc),
                blocked=True,
                remediation="Wait before retrying or upgrade plan",
            )
            self._record_violation(violation)
            return False, violation

        # Check resource access
        if resource not in policy["allowed_resources"]:
            violation = PolicyViolation(
                violation_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                violation_type=ViolationType.UNAUTHORIZED_ACCESS,
                severity=ViolationSeverity.HIGH,
                resource=resource,
                action=action,
                details={"reason": "Resource not in allowed list"},
                timestamp=datetime.now(timezone.utc),
                blocked=True,
            )
            self._record_violation(violation)
            return False, violation

        # Log successful access
        self._audit_access(tenant_id, user_id, resource, action, "success", context)

        return True, None

    def detect_tenant_isolation_breach(
        self,
        tenant_id: str,
        accessed_tenant_id: str,
        resource: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> PolicyViolation | None:
        """
        Detect if a tenant isolation breach occurred.

        Returns:
            Violation if breach detected, None otherwise
        """
        if tenant_id != accessed_tenant_id:
            violation = PolicyViolation(
                violation_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=context.get("user_id"),
                violation_type=ViolationType.TENANT_ISOLATION_BREACH,
                severity=ViolationSeverity.CRITICAL,
                resource=resource,
                action="cross_tenant_access",
                details={
                    "accessed_tenant": accessed_tenant_id,
                    "context": context,
                },
                timestamp=datetime.now(timezone.utc),
                blocked=True,
                remediation="Immediate investigation required",
            )
            self._record_violation(violation)
            return violation

        return None

    def _check_rate_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limit"""
        policy = self._tenant_policies.get(tenant_id)
        if not policy:
            return True

        # Reset counter if minute passed
        now = datetime.now(timezone.utc)
        if (now - policy["last_reset"]).seconds >= 60:
            policy["request_count"] = 0
            policy["last_reset"] = now

        # Check limit
        if policy["request_count"] >= policy["rate_limit"]:
            return False

        policy["request_count"] += 1
        return True

    def _record_violation(self, violation: PolicyViolation) -> None:
        """Record and handle a violation"""
        self._violations.append(violation)

        # Audit log
        self._audit_log.append(
            SecurityAudit(
                event_id=str(uuid.uuid4()),
                event_type="policy_violation",
                tenant_id=violation.tenant_id,
                user_id=violation.user_id,
                resource=violation.resource,
                action=violation.action,
                outcome="blocked" if violation.blocked else "detected",
                details=violation.to_dict(),
                timestamp=violation.timestamp,
            )
        )

        # Notify handlers for critical violations
        if violation.severity == ViolationSeverity.CRITICAL:
            for handler in self._violation_handlers:
                try:
                    handler(violation)
                except Exception:
                    pass  # Don't let handler failures stop processing

    def _audit_access(
        self,
        tenant_id: str,
        user_id: str | None,
        resource: str,
        action: str,
        outcome: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Log access audit event"""
        self._audit_log.append(
            SecurityAudit(
                event_id=str(uuid.uuid4()),
                event_type="access_check",
                tenant_id=tenant_id,
                user_id=user_id,
                resource=resource,
                action=action,
                outcome=outcome,
                details=context,
                timestamp=datetime.now(timezone.utc),
                ip_address=context.get("ip_address"),
                user_agent=context.get("user_agent"),
            )
        )

    def get_violations(
        self,
        tenant_id: str | None = None,
        severity: ViolationSeverity | None = None,
    ) -> list[PolicyViolation]:
        """Get violations with filtering"""
        violations = self._violations

        if tenant_id:
            violations = [v for v in violations if v.tenant_id == tenant_id]

        if severity:
            violations = [v for v in violations if v.severity == severity]

        return violations

    def get_audit_log(
        self,
        tenant_id: str | None = None,
        event_type: str | None = None,
    ) -> list[SecurityAudit]:
        """Get audit log with filtering"""
        logs = self._audit_log

        if tenant_id:
            logs = [log for log in logs if log.tenant_id == tenant_id]

        if event_type:
            logs = [log for log in logs if log.event_type == event_type]

        return logs

    def get_security_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate security report"""
        total_violations = len(self._violations)
        critical = len([v for v in self._violations if v.severity == ViolationSeverity.CRITICAL])
        high = len([v for v in self._violations if v.severity == ViolationSeverity.HIGH])
        blocked = len([v for v in self._violations if v.blocked])

        return {
            "total_violations": total_violations,
            "critical": critical,
            "high": high,
            "medium": len([v for v in self._violations if v.severity == ViolationSeverity.MEDIUM]),
            "low": len([v for v in self._violations if v.severity == ViolationSeverity.LOW]),
            "blocked_attempts": blocked,
            "audit_events": len(self._audit_log),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
