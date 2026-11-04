from enum import Enum


class OAuth2Scope(str, Enum):
    # Read scopes
    AGENTS_READ = "agents:read"
    WORKFLOWS_READ = "workflows:read"
    AUDIT_READ = "audit:read"
    USERS_READ = "users:read"
    ROLES_READ = "roles:read"
    PRANA_READ = "prana:read"
    GOVERNANCE_READ = "governance:read"
    TRACE_READ = "trace:read"
    TWIN_READ = "twin:read"

    # Write scopes
    AGENTS_WRITE = "agents:write"
    WORKFLOWS_WRITE = "workflows:write"
    USERS_WRITE = "users:write"
    ROLES_WRITE = "roles:write"
    PRANA_MANAGE = "prana:manage"

    # Admin scopes
    ADMIN_ALL = "admin:*"
    COMPLIANCE_EXPORT = "compliance:export"

    # Portal scopes (ADR-029)
    PORTAL_READ = "portal:read"
    PORTAL_UPLOAD = "portal:upload"
    PORTAL_CURATE = "portal:curate"
    PORTAL_ADMIN = "portal:admin"
    PORTAL_EDU = "portal:edu"
