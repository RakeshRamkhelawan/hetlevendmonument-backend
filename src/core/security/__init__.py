"""
Security module for production-grade security features

SECURITY FIX (P5.1.4): Added RLS validation module for tenant isolation
SECURITY FIX (P5.1.3): Added SQL/NoSQL injection prevention module
SECURITY FIX (P5.1.10): Added SSRF prevention module for internal network protection

WARNING: Direct imports from src.core.security are deprecated.
Use src.core.auth.jwt_handler and src.core.auth.dependencies instead.
Submodules (security_manager, crypto_utils, etc.) remain valid.
"""

import warnings
from datetime import timedelta
from typing import Any, NoReturn, cast
from collections.abc import Callable

# Issue deprecation warning at import time for legacy direct imports.
# Submodules (security_manager, crypto_utils, etc.) remain valid.
# MIGRATION: Use src.core.auth.jwt_handler and src.core.auth.dependencies instead.
warnings.warn(
    "DEPRECATED: Direct imports from src.core.security are deprecated. "
    "Use src.core.auth.jwt_handler and src.core.auth.dependencies instead.",
    DeprecationWarning,
    stacklevel=2,
)

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Canonical Imports - Lazy to avoid circular imports
if TYPE_CHECKING:
    from src.core.auth.auth_service import UserResponse

# Lazy import to avoid circular dependency - imports deferred to function calls
# from src.core.auth.dependencies import get_current_user as canonical_get_current_user
from src.core.auth.jwt_handler import jwt_handler
from src.core.auth.types import JWTPayload
from src.core.security.jwt_handler_deprecated import TokenData as LegacyTokenData

# =============================================================================
# DEPRECATED ITEMS - Mapped to Canonical Implementation
# =============================================================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class TokenData(LegacyTokenData):
    """Deprecated legacy token data model kept for backward compatibility."""

    def __init__(self, **data: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        warnings.warn(
            "TokenData from src.core.security is deprecated. Use src.core.auth schemas instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**data)


def create_access_token(
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    expires_delta: timedelta | None = None,
) -> str:
    """DEPRECATED: Use jwt_handler.create_access_token() instead."""
    warnings.warn(
        "create_access_token() from security is deprecated. Use src.core.auth.jwt_handler.jwt_handler.create_access_token()",
        DeprecationWarning,
        stacklevel=2,
    )
    # Adapt legacy call to new singleton
    return cast(str, jwt_handler.create_access_token(cast(JWTPayload, data), expires_delta))


async def get_current_user(token: str = Depends(oauth2_scheme)) -> NoReturn:
    """
    DEPRECATED: Use src.core.auth.dependencies.get_current_user instead.
    NOTE: This legacy wrapper does NOT work with the new dependency injection signature.
    It raises an error to force migration.
    """
    warnings.warn(
        "src.core.security.get_current_user is deprecated and incompatible. "
        "Update imports to: from src.core.auth.dependencies import get_current_user",
        DeprecationWarning,
        stacklevel=2,
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Legacy security.get_current_user is removed. Please update imports to src.core.auth.dependencies.",
    )


def check_tool_authorization(
    required_scopes: list[str],
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """DEPRECATED: Use RBAC system from src.core.auth.rbac instead"""
    warnings.warn(
        "check_tool_authorization() is deprecated. Use RBAC system.",
        DeprecationWarning,
        stacklevel=2,
    )

    def _check_auth(
        current_user: "UserResponse" = Depends(
            lambda: __import__(
                "src.core.auth.dependencies", fromlist=["get_current_user_dependency"]
            ).get_current_user_dependency()
        ),
    ) -> "UserResponse":
        # Simple shim using new UserResponse scopes
        for scope in required_scopes:
            if scope not in current_user.scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Not authorized. Missing scope: {scope}",
                )
        return current_user

    return _check_auth


# P5.1.3: SQL/NoSQL Injection Prevention (OWASP A03:2021)
from .input_sanitization import (
    InjectionProtector,
    InjectionType,
    SecureIntField,
    SecureStringField,
    ValidationResult,
    escape_like_pattern,
    log_injection_attempt,
    validate_email,
    validate_integer_id,
    validate_json_data,
    validate_search_query,
    validate_string_input,
    validate_uuid,
)
from .query_validation import (
    QueryParams,
    SafeQueryBuilder,
    safe_filter_by_id,
    safe_filter_by_tenant,
    safe_json_contains_filter,
    safe_like_filter,
    validate_pagination,
    validate_sort_column,
)

# P5.1.4: Row-Level Security validation utilities
from .rls_validation import (
    RLSViolationError,
    TenantContextMissingError,
    add_tenant_filter,
    audit_tenant_access,
    ensure_tenant_isolation,
    get_required_tenant_id,
    get_safe_tenant_id,
    require_tenant_context,
    validate_bulk_tenant_ids,
    validate_model_has_tenant_id,
    validate_resource_tenant,
    validate_tenant_access,
    validate_tenant_id_param,
)
from .security_manager import (
    ProductionSecurityManager,
    RateLimitRule,
    SecurityEvent,
    SecurityLevel,
    get_security_manager,
)
from .types import ThreatLevel


class SecurityMiddleware:
    """Lazy proxy to avoid importing the full API stack during package init."""

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        from .security_middleware import SecurityMiddleware as middleware_cls

        return middleware_cls(*args, **kwargs)


def create_security_middleware(*args: Any, **kwargs: Any) -> Any:
    """Lazily import the middleware factory to keep package imports side-effect free."""
    from .security_middleware import create_security_middleware as factory

    return factory(*args, **kwargs)


# IP Whitelisting middleware
from .ip_whitelist import (
    IPWhitelistConfig,
    IPWhitelistResult,
    IPWhitelistService,
    get_ip_whitelist_service,
)

# P5.1.10: SSRF Prevention (OWASP A10:2021)
from .ssrf_protection import (
    SafeHttpUrl,
    SSRFConfig,
    SSRFProtector,
    SSRFValidationError,
    SSRFViolationType,
    get_default_protector,
    is_safe_ip,
    is_safe_url,
    validate_callback_url,
    validate_url,
)

__all__ = [
    # Legacy backward compatibility (DEPRECATED)
    "create_access_token",
    "TokenData",
    "get_current_user",
    "oauth2_scheme",
    # Security manager
    "get_security_manager",
    "ProductionSecurityManager",
    "SecurityLevel",
    "ThreatLevel",
    "SecurityEvent",
    "RateLimitRule",
    "SecurityMiddleware",
    "create_security_middleware",
    # RLS validation (P5.1.4)
    "RLSViolationError",
    "TenantContextMissingError",
    "validate_resource_tenant",
    "validate_tenant_id_param",
    "ensure_tenant_isolation",
    "require_tenant_context",
    "validate_tenant_access",
    "add_tenant_filter",
    "validate_bulk_tenant_ids",
    "get_safe_tenant_id",
    "get_required_tenant_id",
    "validate_model_has_tenant_id",
    "audit_tenant_access",
    # P5.1.3: Injection Prevention
    "InjectionProtector",
    "ValidationResult",
    "InjectionType",
    "validate_string_input",
    "validate_integer_id",
    "validate_search_query",
    "validate_json_data",
    "validate_email",
    "validate_uuid",
    "escape_like_pattern",
    "log_injection_attempt",
    "SecureStringField",
    "SecureIntField",
    "SafeQueryBuilder",
    "QueryParams",
    "safe_filter_by_id",
    "safe_filter_by_tenant",
    "safe_like_filter",
    "safe_json_contains_filter",
    "validate_sort_column",
    "validate_pagination",
    # P5.1.10: SSRF Prevention
    "SSRFProtector",
    "SSRFConfig",
    "SSRFValidationError",
    "SSRFViolationType",
    "validate_url",
    "is_safe_url",
    "is_safe_ip",
    "SafeHttpUrl",
    "validate_callback_url",
    "get_default_protector",
    # IP Whitelisting
    "IPWhitelistService",
    "IPWhitelistConfig",
    "IPWhitelistResult",
    "get_ip_whitelist_service",
]
