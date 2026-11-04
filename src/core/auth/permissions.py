"""
Permission Scopes for Sprint 3.2 RBAC Standardization

Defines 8 core permission scopes using resource:action format.
Used by @require_permission decorator for consistent access control.

Scope Format: resource:action
- resource: what you're accessing (workflow, execution, admin, etc.)
- action: what you're doing (create, read, update, delete, execute, cancel, audit)

Permission Hierarchy:
- resource:* = all actions on resource
- admin:* = all admin operations
"""


# ============================================================================
# Workflow Permissions (4 scopes)
# ============================================================================

WORKFLOW_CREATE = "workflow:create"
"""Create new workflows - requires workflow:create permission"""

WORKFLOW_READ = "workflow:read"
"""View workflow definitions and metadata - read-only access"""

WORKFLOW_UPDATE = "workflow:update"
"""Edit workflow specifications and metadata"""

WORKFLOW_DELETE = "workflow:delete"
"""Remove workflows from system"""

WORKFLOW_EXECUTE = "workflow:execute"
"""Trigger workflow executions (start new runs)"""

# Wildcard for all workflow permissions
WORKFLOW_ALL = "workflow:*"

# ============================================================================
# Execution Permissions (2 scopes)
# ============================================================================

EXECUTION_READ = "execution:read"
"""View execution status, logs, and task details"""

EXECUTION_CANCEL = "execution:cancel"
"""Stop running executions"""

# Wildcard for all execution permissions
EXECUTION_ALL = "execution:*"

# ============================================================================
# Admin Permissions (1 scope, may expand)
# ============================================================================

ADMIN_AUDIT = "admin:audit"
"""View audit logs and security events (admin only)"""

# Wildcard for all admin permissions
ADMIN_ALL = "admin:*"

# ============================================================================
# Template Permissions (future Sprint 3.4)
# ============================================================================

TEMPLATE_READ = "template:read"
"""Access pre-built templates (read-only)"""

# ============================================================================
# Permission Scope Sets (for role definitions)
# ============================================================================

# Scope set for admin role - all permissions
ADMIN_SCOPES: list[str] = [
    WORKFLOW_ALL,
    EXECUTION_ALL,
    ADMIN_ALL,
]

# Scope set for editor role - create/update workflows, manage executions
EDITOR_SCOPES: list[str] = [
    WORKFLOW_CREATE,
    WORKFLOW_READ,
    WORKFLOW_UPDATE,
    WORKFLOW_EXECUTE,
    EXECUTION_READ,
    EXECUTION_CANCEL,
    TEMPLATE_READ,
]

# Scope set for viewer role - read-only access
VIEWER_SCOPES: list[str] = [
    WORKFLOW_READ,
    EXECUTION_READ,
    TEMPLATE_READ,
]

# ============================================================================
# Permission Constants for Easy Reference
# ============================================================================

WORKFLOW_SCOPES = [
    WORKFLOW_CREATE,
    WORKFLOW_READ,
    WORKFLOW_UPDATE,
    WORKFLOW_DELETE,
    WORKFLOW_EXECUTE,
]

EXECUTION_SCOPES = [
    EXECUTION_READ,
    EXECUTION_CANCEL,
]

ADMIN_SCOPES_LIST = [
    ADMIN_AUDIT,
]

ALL_SCOPES = WORKFLOW_SCOPES + EXECUTION_SCOPES + ADMIN_SCOPES_LIST + [TEMPLATE_READ]

# ============================================================================
# Scope Descriptions (for documentation)
# ============================================================================

SCOPE_DESCRIPTIONS = {
    WORKFLOW_CREATE: "Create new workflow definitions",
    WORKFLOW_READ: "View workflow details and specifications",
    WORKFLOW_UPDATE: "Edit workflow specifications",
    WORKFLOW_DELETE: "Remove workflows from system",
    WORKFLOW_EXECUTE: "Trigger workflow executions",
    EXECUTION_READ: "View execution status and logs",
    EXECUTION_CANCEL: "Stop running workflow executions",
    ADMIN_AUDIT: "View audit logs and security events",
    TEMPLATE_READ: "Access pre-built workflow templates",
}

# ============================================================================
# Helper Functions
# ============================================================================


def parse_scope(scope: str) -> tuple[str, str]:
    """
    Parse a scope string into (resource, action) tuple.

    Args:
        scope: Scope string in format "resource:action"

    Returns:
        (resource, action) tuple

    Raises:
        ValueError: If scope format is invalid
    """
    if ":" not in scope:
        raise ValueError(f"Invalid scope format: {scope}. Expected 'resource:action'")

    parts = scope.split(":", 1)
    resource, action = parts[0], parts[1]

    if not resource or not action:
        raise ValueError(
            f"Invalid scope format: {scope}. Both resource and action must be non-empty"
        )

    return resource, action


def scope_matches(user_scope: str, required_scope: str) -> bool:
    """
    Check if a user's scope matches a required scope.

    Supports wildcard matching:
    - "workflow:*" matches "workflow:read", "workflow:create", etc.
    - "*" would match any scope (admin level)

    Args:
        user_scope: Scope granted to user
        required_scope: Scope required for operation

    Returns:
        True if user_scope satisfies required_scope
    """
    # Exact match
    if user_scope == required_scope:
        return True

    # Wildcard matches
    if user_scope == "*":  # Super admin
        return True

    try:
        user_res, user_action = parse_scope(user_scope)
        req_res, req_action = parse_scope(required_scope)

        # Resource mismatch
        if user_res != req_res:
            return False

        # Action matching with wildcard
        if user_action == "*":  # workflow:* matches workflow:read, workflow:create, etc.
            return True

        # Exact action match
        if user_action == req_action:
            return True

    except ValueError:
        # Invalid scope format - no match
        return False

    return False


__all__ = [
    # Workflow scopes
    "WORKFLOW_CREATE",
    "WORKFLOW_READ",
    "WORKFLOW_UPDATE",
    "WORKFLOW_DELETE",
    "WORKFLOW_EXECUTE",
    # Execution scopes
    "EXECUTION_READ",
    "EXECUTION_CANCEL",
    # Admin scopes
    "ADMIN_AUDIT",
    # Template scopes
    "TEMPLATE_READ",
    # Scope sets for roles
    "ADMIN_SCOPES",
    "EDITOR_SCOPES",
    "VIEWER_SCOPES",
    # Utility functions
    "parse_scope",
    "scope_matches",
    "SCOPE_DESCRIPTIONS",
]
