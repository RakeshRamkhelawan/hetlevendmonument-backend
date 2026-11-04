# orphan:exempt reason: Laag 1 dependencies, imported by tools sub-routers (ADR-033)
"""Tools API shared dependencies (ADR-033 Laag 1)."""

from src.core.auth.api_deps import get_current_user as get_current_user
from src.core.database.database import get_db as get_db
