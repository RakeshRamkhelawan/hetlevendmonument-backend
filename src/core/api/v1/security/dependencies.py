"""Security domain dependencies (ADR-033 Laag 1)."""

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_admin,
    require_scopes,
    OAuth2Scope,
)
from src.core.database.database import get_db
from src.core.security.ip_reputation import get_ip_reputation
from src.core.security.security_manager import SecurityLevel, ThreatLevel, get_security_manager

__all__ = [
    "UserResponse",
    "get_current_user",
    "require_scopes",
    "OAuth2Scope",
    "get_db",
    "SecurityLevel",
    "ThreatLevel",
    "get_security_manager",
    "get_ip_reputation",
    "require_admin",
]
