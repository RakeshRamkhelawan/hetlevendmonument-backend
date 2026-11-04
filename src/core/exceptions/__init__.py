"""
Sanskriti Setu AI Platform Exceptions Package
"""

from typing import Any, NoReturn, Optional

from .exceptions import (
    AgentTimeoutError,
    AuthError,
    ApprovalRightRequiredError,
    ConflictError,
    LastAdminError,
    GovernanceVetoError,
    NotFoundError,
    PermissionDeniedError,
    PromptInjectionError,
    RBACError,
    SanskritiError,
    TenantAccessDeniedError,
    TenantError,
    TenantNotFoundError,
    ValidatieFout,
    ValidationError,
    WorkflowError,
    WorkflowExecutionError,
    WorkflowNotFoundError,
)
from .handlers import (
    raise_not_found as _raise_not_found,
    raise_permission_denied as _raise_permission_denied,
    raise_tenant_error as _raise_tenant_error,
    raise_validation_error as _raise_validation_error,
    raise_workflow_error as _raise_workflow_error,
    register_exception_handlers,
)


# Re-export with explicit NoReturn for type narrowing
def raise_not_found(resource_type: str, resource_id: str | None = None) -> NoReturn:
    """Re-export with explicit NoReturn for type narrowing through re-exports."""
    _raise_not_found(resource_type, resource_id)


def raise_validation_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Re-export with explicit NoReturn for type narrowing through re-exports."""
    _raise_validation_error(message, details=details)


def raise_permission_denied(permission: str, resource: str, user_id: str) -> NoReturn:
    """Re-export with explicit NoReturn for type narrowing through re-exports."""
    _raise_permission_denied(permission, resource, user_id)


def raise_tenant_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Re-export with explicit NoReturn for type narrowing through re-exports."""
    _raise_tenant_error(message, details=details)


def raise_workflow_error(
    message: str,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> NoReturn:  # TODO(TYPE): replace Any with concrete type
    """Re-export with explicit NoReturn for type narrowing through re-exports."""
    _raise_workflow_error(message, details=details)


__all__ = [
    # Exception classes
    "SanskritiError",
    "AuthError",
    "ApprovalRightRequiredError",
    "ConflictError",
    "LastAdminError",
    "WorkflowError",
    "TenantError",
    "RBACError",
    "ValidatieFout",
    "ValidationError",
    "NotFoundError",
    "TenantNotFoundError",
    "TenantAccessDeniedError",
    "PermissionDeniedError",
    "WorkflowNotFoundError",
    "WorkflowExecutionError",
    "AgentTimeoutError",
    "GovernanceVetoError",
    "PromptInjectionError",
    # Handler functions
    "register_exception_handlers",
    "raise_not_found",
    "raise_validation_error",
    "raise_permission_denied",
    "raise_tenant_error",
    "raise_workflow_error",
]
