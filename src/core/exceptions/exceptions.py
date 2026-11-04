"""
Custom Exceptions for Sanskriti Setu AI Platform
Unified exception hierarchy for consistent error handling.
"""

from datetime import datetime, timezone
from typing import Any, Optional


class SanskritiError(Exception):
    """Base exception for all Sanskriti Setu platform errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 500,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.status_code = status_code
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert exception to dictionary representation."""
        return {
            "error": {
                "error_code": self.error_code,
                "message": self.message,
                "timestamp": self.timestamp.isoformat() + "Z",
                "details": self.details,
            }
        }


class WorkflowError(SanskritiError):
    """Workflow-related errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 500,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "WORKFLOW_ERROR",
            status_code=status_code,
            details=details,
        )


class TenantError(SanskritiError):
    """Multi-tenant isolation violations."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 403,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "TENANT_ERROR",
            status_code=status_code,
            details=details,
        )


class PromptInjectionError(SanskritiError):
    """Prompt injection attack detected in user input."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 400,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "PROMPT_INJECTION_DETECTED",
            status_code=status_code,
            details=details,
        )


class AuthError(SanskritiError):
    """Authentication and authorization errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 401,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "AUTH_ERROR",
            status_code=status_code,
            details=details,
        )


class GovernanceVetoError(SanskritiError):
    """Council veto: action blocked by governance policy (EU AI Act Art. 14)."""

    def __init__(
        self,
        message: str,
        decision_id: str | None = None,
        verdict: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code="GOVERNANCE_BLOCKED",
            status_code=403,
            details={"decision_id": decision_id, "verdict": verdict},
        )


class RBACError(SanskritiError):
    """Permission denied errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 403,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "PERMISSION_DENIED",
            status_code=status_code,
            details=details,
        )


class ValidatieFout(ValueError):
    """Een eigen, bewust voor de klant bedoelde validatietekst.

    Alleen de tekst van DEZE klasse mag in een antwoord; elke andere ValueError is een
    vreemde fout waarvan de tekst in het logboek hoort (brief 2026-10-21)."""


class ValidationError(SanskritiError):
    """Input validation failures."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int = 400,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "VALIDATION_ERROR",
            status_code=status_code,
            details=details,
        )


class NotFoundError(SanskritiError):
    """Resource not found errors."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        if resource_id:
            message = f"{resource_type} with ID '{resource_id}' not found"
        else:
            message = f"{resource_type} not found"

        super().__init__(
            message=message,
            error_code=error_code or "NOT_FOUND",
            status_code=404,
            details=details or {"resource_type": resource_type, "resource_id": resource_id},
        )


# Specific subclasses for common error scenarios


class TenantNotFoundError(TenantError):
    """Raised when tenant is not found."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(
            message=f"Tenant with ID '{tenant_id}' not found",
            error_code="TENANT_NOT_FOUND",
            details={"tenant_id": tenant_id},
        )


class TenantAccessDeniedError(TenantError):
    """Raised when tenant access is denied."""

    def __init__(self, tenant_id: str, user_id: str) -> None:
        super().__init__(
            message=f"Access denied to tenant '{tenant_id}' for user '{user_id}'",
            error_code="TENANT_ACCESS_DENIED",
            details={"tenant_id": tenant_id, "user_id": user_id},
        )


class PermissionDeniedError(RBACError):
    """Raised when permission is denied for a specific resource."""

    def __init__(self, permission: str, resource: str, user_id: str) -> None:
        super().__init__(
            message=f"Permission '{permission}' denied for resource '{resource}'",
            error_code="PERMISSION_DENIED",
            details={
                "permission": permission,
                "resource": resource,
                "user_id": user_id,
            },
        )


class WorkflowNotFoundError(NotFoundError):
    """Raised when workflow is not found."""

    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            resource_type="Workflow",
            resource_id=workflow_id,
            error_code="WORKFLOW_NOT_FOUND",
        )


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""

    def __init__(self, workflow_id: str, reason: str) -> None:
        super().__init__(
            message=f"Workflow execution failed for workflow '{workflow_id}': {reason}",
            error_code="WORKFLOW_EXECUTION_ERROR",
            details={"workflow_id": workflow_id, "reason": reason},
        )


class AgentTimeoutError(SanskritiError):
    """Raised when an agent times out."""

    def __init__(self, agent_id: str, task: str, timeout_seconds: float) -> None:
        super().__init__(
            message=f"Agent '{agent_id}' timed out after {timeout_seconds}s for task '{task}'",
            error_code="AGENT_TIMEOUT",
            status_code=504,
            details={"agent_id": agent_id, "task": task, "timeout": timeout_seconds},
        )


class ConflictError(SanskritiError):
    """409 Conflict -- optimistic locking or duplicate resource.

    Used for:
    - Optimistic locking conflicts (version mismatch)
    - Duplicate resource creation attempts
    - Concurrent modification conflicts
    """

    def __init__(
        self,
        message: str,
        current_version: int | None = None,
        conflicting_user: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code or "CONFLICT",
            status_code=409,
            details={
                "current_version": current_version,
                "conflicting_user": conflicting_user,
                **(details or {}),
            },
        )


class EgressBlockedError(SanskritiError):
    """Outbound request blocked by egress control policy."""

    def __init__(
        self,
        url: str,
        reason: str,
        tenant_id: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__(
            message=f"Egress blocked for {url}: {reason}",
            error_code=error_code or "EGRESS_BLOCKED",
            status_code=403,
            details={
                "url": url,
                "reason": reason,
                "tenant_id": tenant_id,
                **(details or {}),
            },
        )


class LastAdminError(ConflictError):
    """409 LAST_ADMIN -- een wijziging zou de tenant zonder actieve beheerder laten (ADR-039).

    De platform-superuser telt niet als beheerder van de tenant (F7). Gegooid door
    `RBACService.finish_admin_check`; de wijziging is dan teruggedraaid.
    """

    def __init__(self) -> None:
        super().__init__(
            message="Er moet minstens een beheerder overblijven.",
            error_code="LAST_ADMIN",
        )


class ApprovalRightRequiredError(RBACError):
    """403 APPROVAL_RIGHT_REQUIRED -- de gebruiker heeft het goedkeurrecht van dit proces niet.

    Het scherm toont op basis van de CODE een Nederlandse uitleg; de melding hier is voor logs en
    API-gebruikers (ADR-039).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message=message, error_code="APPROVAL_RIGHT_REQUIRED")
