"""Shared dependencies for management domain routers."""

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user, require_scopes, OAuth2Scope

__all__ = ["UserResponse", "get_current_user", "require_scopes", "OAuth2Scope"]
