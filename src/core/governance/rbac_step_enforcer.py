"""
RBAC Step Enforcer - Slice 5

Fine-grained access control per procedure step.
Validates user roles, tenant isolation, and logs denials.

Sprint 4 - S4.5: RBAC per procedure step
"""

from typing import Any


class RoleViolationError(Exception):
    """Raised when user lacks required role for step."""

    pass


class TenantViolationError(Exception):
    """Raised when user attempts cross-tenant access."""

    pass


class RBACStepEnforcer:
    """Enforces role-based access control per procedure step."""

    def __init__(self, policy_engine: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Initialize enforcer with policy engine.

        Args:
            policy_engine: Policy evaluation engine (e.g., OPA, Casbin)
        """
        self.policy_engine = policy_engine
        self.last_denial: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def check_step_permission(self, user: Any, step: dict[str, Any], tenant_id: int) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if user has permission to execute step.

        Args:
            user: User object with id, roles, tenant_id attributes
            step: Step definition with step_name, required_roles
            tenant_id: Tenant ID for the operation

        Returns:
            True if allowed

        Raises:
            TenantViolationError: If user attempts cross-tenant access
            RoleViolationError: If user lacks required roles
        """
        # 1. Check tenant isolation
        if hasattr(user, "tenant_id") and user.tenant_id != tenant_id:
            raise TenantViolationError(
                f"User from tenant {user.tenant_id} cannot access resources in tenant {tenant_id}"
            )

        # 2. SuperAdmin bypass
        if "SuperAdmin" in user.roles:
            return True

        # 3. If no required roles, allow all
        required_roles = step.get("required_roles", [])
        if not required_roles:
            return True

        # 4. Check if user has ANY of required roles
        user_roles = set(user.roles)
        required_roles_set = set(required_roles)
        has_role = bool(user_roles & required_roles_set)

        if has_role:
            # Use policy engine for additional checks
            allowed = self.policy_engine.check_permission(
                user_id=user.id,
                action=step.get("step_name"),
                resource="workflow_step",
                context={
                    "tenant_id": tenant_id,
                    "user_roles": user.roles,
                    "required_roles": required_roles,
                },
            )
            return bool(allowed)

        # 5. Role violation - log and raise
        self.last_denial = {
            "user_id": user.id,
            "step_name": step.get("step_name"),
            "required_roles": required_roles,
            "user_roles": user.roles,
            "tenant_id": tenant_id,
        }

        raise RoleViolationError(
            f"User {user.id} lacks required roles {required_roles} for step '{step.get('step_name')}'"
        )
