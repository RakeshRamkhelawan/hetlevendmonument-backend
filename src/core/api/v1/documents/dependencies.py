"""
Documents domain dependencies (ADR-033).

Router-bestanden importeren hieruit in plaats van direct uit
src.core.database of src.core.auth.
"""

from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db
from src.core.governance.audit import audit_service
from src.core.middleware.tenant_context import require_tenant_id
from src.core.models.rbac_models import User

__all__ = [
    "audit_service",
    "get_db",
    "get_current_user",
    "require_tenant_id",
    "User",
]
