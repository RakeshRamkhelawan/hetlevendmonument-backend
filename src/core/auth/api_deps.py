"""Auth facade voor core_api laag (routers, endpoints).

Re-exporteert auth-primitives die core_api consumers nodig hebben.
Stable import point: interne auth module reorganisatie vereist geen
wijzigingen in core_api router bestanden.

LET OP: RBACService hier is uit auth.rbac (RBAC enforcement laag).
Niet verwarren met src.core.services.rbac_service.RBACService (service laag).
"""

from .auth_service import AuthService, UserCreate, UserResponse
from .dependencies import (
    ADMIN_ROLE_NAMES,
    CurrentUser,
    RequireAdmin,
    _weiger_portaaltoken as weiger_portaaltoken,
    controleer_resource_recht,
    get_current_user,
    get_current_user_dependency,
    get_current_user_id,
    get_current_user_ws,
    get_optional_user_dependency,
    is_admin,
    is_platform_superuser,
    require_admin,
    require_permission,
    require_resource_permission,
)
from .jwt_handler import jwt_handler
from .permissions import ADMIN_SCOPES, EDITOR_SCOPES, VIEWER_SCOPES
from .rbac import Permission, RBACService
from .scope_validator import has_scopes, require_scopes
from .scopes import OAuth2Scope
from .types import JWTPayload, VerifiedJWTPayload
from .websocket_auth import (
    AuthenticatedUser,
    WebSocketAuthenticator,
    get_ws_user,
    websocket_auth,
)

__all__ = [
    "AuthService",
    "UserCreate",
    "UserResponse",
    "CurrentUser",
    "RequireAdmin",
    "get_current_user",
    "get_current_user_dependency",
    "get_current_user_id",
    "get_current_user_ws",
    "get_optional_user_dependency",
    "ADMIN_ROLE_NAMES",
    "is_admin",
    "is_platform_superuser",
    "require_admin",
    "require_permission",
    "require_resource_permission",
    "controleer_resource_recht",
    "weiger_portaaltoken",
    "jwt_handler",
    "ADMIN_SCOPES",
    "EDITOR_SCOPES",
    "VIEWER_SCOPES",
    "Permission",
    "RBACService",
    "has_scopes",
    "require_scopes",
    "OAuth2Scope",
    "JWTPayload",
    "VerifiedJWTPayload",
    "AuthenticatedUser",
    "WebSocketAuthenticator",
    "get_ws_user",
    "websocket_auth",
]
