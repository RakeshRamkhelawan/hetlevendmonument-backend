"""Prediction domain dependencies (ADR-033 Laag 1)."""

from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.learning.predictive_evolution import predictive_evolution_engine

__all__ = [
    "UserResponse",
    "get_current_user",
    "require_scopes",
    "OAuth2Scope",
    "predictive_evolution_engine",
]
