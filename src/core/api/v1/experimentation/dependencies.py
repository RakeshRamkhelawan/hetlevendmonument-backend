"""Experimentation domain dependencies (ADR-033 Laag 2)."""

from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db

__all__ = ["get_current_user", "get_db"]
