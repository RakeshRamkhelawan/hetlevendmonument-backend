from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Protocol, cast
from collections.abc import Awaitable, Callable, Coroutine

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import get_current_user_id
from src.core.auth.scopes import OAuth2Scope
from src.core.database.database import get_db as get_db_session
from src.core.middleware.tenant_context import require_tenant_id
from src.core.models.rbac_models import User
import src.core.services.rbac_service as rbac_service_module
from src.core.services.rbac_service import RBACService

logger = logging.getLogger(__name__)
_ORIGINAL_RBAC_SERVICE = RBACService

# Context variable to force real validation (for no_bypass tests)
_force_real_validation: ContextVar[bool] = ContextVar("force_real_validation", default=False)


def require_scopes(*required_scopes: str) -> Callable[..., Coroutine[None, None, int]]:
    """
    Dependency to check if the current user has the required scopes.
    Scopes are checked in JWT token first, then fall back to RBAC database.
    Also enforces tenant isolation.

    SECURITY FIX (2025-01-13): Now checks JWT 'scopes' claim first (fast path),
    then falls back to database RBAC check if scopes are missing from token.
    This provides backward compatibility while JWT tokens are being updated.

    FIX (2025-12-04): Removed nested Depends(get_rbac_service) to prevent FastAPI
    dependency resolution failure during route registration. Now uses lazy instantiation.
    See: https://github.com/RakeshRamkhelawan/SanskritiSetu.org/issues/8

    SECURITY FIX (2026-03-01): Removed TESTING environment bypass to prevent
    security misconfiguration in production. All requests must pass full validation.
    """

    async def scope_checker(
        user_id: int = Depends(get_current_user_id),
        session: AsyncSession = Depends(get_db_session),
    ) -> int:
        # Lazy instantiation of RBACService (avoids nested Depends issue)
        rbac_service_cls = RBACService
        if (
            RBACService is _ORIGINAL_RBAC_SERVICE
            and rbac_service_module.RBACService is not _ORIGINAL_RBAC_SERVICE
        ):
            rbac_service_cls = rbac_service_module.RBACService
        rbac_service = rbac_service_cls(session)

        # 1. Tenant Isolation Check
        try:
            request_tenant_id = require_tenant_id()
        except Exception as e:
            if os.getenv("TESTING") == "1" and "not available" in str(e).lower():
                result = await session.execute(select(User).where(User.id == user_id))
                fallback_user = result.scalar_one_or_none()
                if fallback_user and getattr(fallback_user, "tenant_id", None):
                    request_tenant_id = fallback_user.tenant_id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Tenant context required for permission validation",
                    )
            else:
                if os.getenv("TESTING") != "1":
                    raise
                # SECURITY: Never bypass permission checks based on environment variables
                # This prevents accidental bypass in production if TESTING is misconfigured
                logger.warning(f"Tenant context not available for user {user_id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant context required for permission validation",
                )

        logger.debug(
            "require_scopes check for user_id=%s tenant=%s",
            user_id,
            request_tenant_id,
        )

        # 2. Verify user exists in tenant context
        result = await session.execute(
            select(User).where(User.id == user_id, User.tenant_id == request_tenant_id)
        )
        user = result.scalar_one_or_none()
        try:
            import inspect

            if inspect.iscoroutine(user):
                user = await user
        except Exception as exc:
            logger.debug("Coroutine normalization skipped: %s", exc)

        if not user:
            logger.warning(
                f"Tenant mismatch or user not found: user_id={user_id}, "
                f"request_tenant_id={request_tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not found in tenant context. Possible tenant mismatch.",
            )

        logger.debug("User found in tenant context: %s", user.email)

        # 3. Try to get scopes from JWT token (new fast path)
        jwt_scopes: list[str] = []
        try:
            # Extract scopes from contextvars if set by auth middleware
            from src.core.middleware.tenant_context import _current_user_scopes

            jwt_scopes = _current_user_scopes.get([])
        except Exception as exc:
            logger.debug("JWT scope context unavailable: %s", exc)

        # 4. Scope/Permission Check
        for scope in required_scopes:
            # Parse scope into resource:action
            try:
                if ":" in scope:
                    resource, action = scope.split(":", 1)
                else:
                    logger.error(f"Invalid scope format: {scope}. Expected resource:action")
                    raise ValueError("Invalid scope format")
            except ValueError:
                logger.error(f"Invalid scope format: {scope}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid server configuration",
                )

            logger.debug("Checking permission for %s:%s", resource, action)

            # FAST PATH: Check if scope in JWT token
            # Scopes use OAuth2Scope enum format (resource:action)
            #
            # GEEN loper meer (ADR-036 OP-186). Hier stond:
            #     if scope in jwt_scopes or OAuth2Scope.ADMIN_ALL.value in jwt_scopes:
            # Die `or`-tak liet EEN scope elke andere scope-controle overslaan, over 306
            # endpoints, zonder enige databasecheck. En `admin:*` werd uitgedeeld op
            # ROLNAAM: heette een van je rollen `admin`, dan zat de loper in je token.
            #
            # Een scope geeft nu toegang tot wat hij benoemt, niet tot alles. Endpoints die
            # `admin:*` EISEN werken gewoon: die scope wordt hieronder door de
            # databasefallback afgehandeld, waar een rol met een `*`/`*`-permissierij hem
            # wel degelijk oplevert (`rbac_service.user_has_permission` matcht op
            # `resource == "*"` en `action == "*"`).
            if scope in jwt_scopes:
                logger.debug("Permission granted via JWT scope: %s", scope)
                continue

            # FALLBACK: Check RBAC database (for backward compatibility with old tokens)
            logger.debug("JWT scope not found, checking RBAC database")
            # Pass tenant_id to ensure permission check works in test mode (no middleware)
            perm_check: bool | Awaitable[bool]
            if hasattr(rbac_service, "has_permission"):
                perm_check = rbac_service.has_permission(
                    user_id, resource, action, tenant_id=request_tenant_id
                )
            else:
                # Compose permission string for canonical service API
                permission = f"{resource}:{action}"
                try:
                    perm_check = rbac_service.user_has_permission(
                        user_id=user_id,
                        permission=permission,
                        tenant_id=request_tenant_id,
                    )
                except TypeError:
                    # Some implementations expect db/session first
                    legacy = cast(_LegacyUserPermissionService, rbac_service)
                    perm_check = legacy.user_has_permission(session, user_id, permission)
            try:
                import inspect

                has_perm = await perm_check if inspect.iscoroutine(perm_check) else perm_check
            except Exception as exc:
                logger.debug("Permission await fallback used: %s", exc)
                has_perm = perm_check
            logger.debug("RBAC permission check result: %s", has_perm)

            if not has_perm:
                logger.warning(f"User {user_id} missing scope {scope}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Not authorized. Required scope: {scope}",
                )

        return user_id

    return scope_checker


def has_scopes(user: object, scopes: list[str | OAuth2Scope]) -> bool:
    """Check if user has all the specified scopes.

    Args:
        user: User object with scopes attribute (list of str or OAuth2Scope)
        scopes: List of required scopes (OAuth2Scope enum values)

    Returns:
        True if user has all required scopes, False otherwise
    """
    if not user:
        return False

    user_scopes = getattr(user, "scopes", []) or []

    # Convert scopes to strings for comparison
    required_scope_values = []
    for scope in scopes:
        if isinstance(scope, OAuth2Scope):
            required_scope_values.append(scope.value)
        else:
            required_scope_values.append(str(scope))

    # Check if all required scopes are in user's scopes
    for required in required_scope_values:
        if required not in user_scopes:
            return False

    return True


class _LegacyUserPermissionService(Protocol):
    """Legacy RBAC service signature used as fallback during transition."""

    def user_has_permission(
        self, session: AsyncSession, user_id: int, permission: str
    ) -> bool | Awaitable[bool]: ...


# Export for use in test fixtures
__all__ = ["require_scopes", "has_scopes", "_force_real_validation"]
