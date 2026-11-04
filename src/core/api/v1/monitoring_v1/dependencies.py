"""
Dependencies for monitoring_v1 domain (ADR-033 thin delivery).
"""

from src.core.auth.api_deps import (  # noqa: F401 -- re-export
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)

__all__ = [
    "UserResponse",
    "get_current_user",
    "require_scopes",
    "OAuth2Scope",
]
