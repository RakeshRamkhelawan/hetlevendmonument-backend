"""Health domain shared dependencies (ADR-033 Laag 1)."""

from src.core.api.dependencies import require_authenticated_user
from src.core.database.database import get_db

# Re-export for use across health sub-routers
verify_token = require_authenticated_user

__all__ = ["get_db", "verify_token"]
