"""
Auth Module - Production Implementation
Authenticatie en autorisatie services voor FASE 1
"""

from typing import TYPE_CHECKING

# Only import safe modules that don't trigger circular imports
from .jwt_handler import JWTHandler, jwt_handler

# Import types that don't cause circular imports
from .auth_service import (
    AuthService,
    TokenResponse,
    UserCreate,
    UserResponse,
    auth_service,
)
from .rbac import Permission, RBACService, rbac_service

if TYPE_CHECKING:
    from .dependencies import require_permission

__all__ = [
    "jwt_handler",
    "JWTHandler",
    "auth_service",
    "AuthService",
    "UserCreate",
    "UserResponse",
    "TokenResponse",
    "Permission",
    "rbac_service",
    "RBACService",
    "require_permission",
]
