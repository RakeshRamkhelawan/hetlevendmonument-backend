"""Users domain dependencies (ADR-033)."""

from src.core.api.auth.uitnodiging import stuur_uitnodiging
from src.core.auth.api_deps import (
    AuthService,
    UserCreate as AuthUserCreate,
    get_current_user,
    is_platform_superuser,
    jwt_handler,
)
from src.core.database.database import get_db
from src.core.models.rbac_models import Role, User
from src.core.services.rbac_service import RBACService

__all__ = [
    "get_db",
    "AuthService",
    "AuthUserCreate",
    "get_current_user",
    "is_platform_superuser",
    "jwt_handler",
    "RBACService",
    "Role",
    "User",
    "stuur_uitnodiging",
]
