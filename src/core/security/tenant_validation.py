"""Tenant isolation validation for all agents.

CRITICAL SECURITY: This module ensures strict tenant isolation across all
agent operations. Any agent method that accesses tenant-scoped resources
MUST use the @validate_tenant_access decorator.
"""

import functools
import logging
from typing import Any, Concatenate, Coroutine, ParamSpec, Protocol, TypeVar
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.expression import ColumnElement

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class _TenantScoped(Protocol):
    """Protocol for objects that have tenant_id and agent_id attributes."""

    tenant_id: int | None
    agent_id: str


def validate_tenant_access(
    resource_name: str,
) -> Callable[
    [Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]]],
    Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]],
]:
    """
    Decorator to validate tenant access on agent methods.

    This decorator ensures that:
    1. The agent has a valid tenant_id
    2. The tenant_id is properly initialized
    3. All operations are logged with tenant context

    Usage:
        @validate_tenant_access("artifact")
        async def get_artifact(self, artifact_id: int):
            ...

    Args:
        resource_name: Name of the resource being accessed (for logging)

    Raises:
        PermissionError: If agent does not have a valid tenant_id
    """

    def decorator(
        func: Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]],
    ) -> Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]]:
        @functools.wraps(func)
        async def wrapper(self: _TenantScoped, /, *args: P.args, **kwargs: P.kwargs) -> R:
            tenant_id = getattr(self, "tenant_id", None)
            agent_id = getattr(self, "agent_id", "unknown")

            if not tenant_id:
                logger.error(
                    f"SECURITY VIOLATION: Agent {agent_id} attempted {resource_name} "
                    f"access without tenant_id",
                    extra={
                        "agent_id": agent_id,
                        "resource": resource_name,
                        "event": "security_violation",
                        "violation_type": "missing_tenant_id",
                    },
                )
                raise PermissionError(
                    f"Agent {agent_id} not properly initialized with tenant context. "
                    f"All agents MUST have a valid tenant_id before accessing {resource_name}."
                )

            # Log access attempt for audit trail
            logger.debug(
                f"Tenant {tenant_id} accessing {resource_name}",
                extra={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "resource": resource_name,
                    "event": "resource_access",
                    "security_context": "tenant_validated",
                },
            )

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def require_tenant_id(
    func: Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]],
) -> Callable[Concatenate[_TenantScoped, P], Coroutine[None, None, R]]:
    """
    Simple decorator that just checks tenant_id exists.
    Use this for methods that don't access specific resources.
    """

    @functools.wraps(func)
    async def wrapper(self: _TenantScoped, /, *args: P.args, **kwargs: P.kwargs) -> R:
        tenant_id = getattr(self, "tenant_id", None)
        agent_id = getattr(self, "agent_id", "unknown")

        if not tenant_id:
            raise PermissionError(f"Agent {agent_id} requires tenant_id but none provided")

        return await func(self, *args, **kwargs)

    return wrapper


async def verify_tenant_isolation(
    db: AsyncSession,
    tenant_id: int,
    resource_id: int,
    model_class: type[DeclarativeBase],
    id_column: str = "id",
) -> bool:
    """
        Verify that a resource belongs to a specific tenant.

        This function performs an explicit database check to ensure
    tenant isolation at the application level (in addition to RLS).

        Args:
            db: Database session
            tenant_id: Expected tenant ID
            resource_id: Resource to check
            model_class: SQLAlchemy model class
            id_column: Name of the ID column (default: "id")

        Returns:
            True if resource belongs to tenant, False otherwise
    """
    from sqlalchemy import column

    id_col: ColumnElement[int] = column(id_column)

    result = await db.execute(
        select(model_class).where(id_col == resource_id, model_class.tenant_id == tenant_id)  # type: ignore[attr-defined]
    )

    return result.scalar_one_or_none() is not None


async def enforce_tenant_isolation(
    db: AsyncSession,
    tenant_id: int,
    resource_id: int,
    model_class: type[DeclarativeBase],
    resource_name: str = "resource",
) -> None:
    """
    Enforce tenant isolation by raising exception on violation.

    Use this function when you want to stop execution if the
    resource doesn't belong to the tenant.

    Args:
        db: Database session
        tenant_id: Expected tenant ID
        resource_id: Resource to check
        model_class: SQLAlchemy model class
        resource_name: Name for error message

    Raises:
        PermissionError: If resource doesn't belong to tenant
    """
    is_valid = await verify_tenant_isolation(db, tenant_id, resource_id, model_class)

    if not is_valid:
        logger.error(
            "SECURITY VIOLATION: Cross-tenant access attempt",
            extra={
                "tenant_id": tenant_id,
                "resource_id": str(resource_id),
                "resource_type": model_class.__name__,
                "event": "security_violation",
                "violation_type": "cross_tenant_access",
            },
        )
        raise PermissionError(
            f"Access denied: {resource_name} does not belong to tenant {tenant_id}"
        )


class TenantContext:
    """
    Context manager for temporary tenant context switching.

    Use this for admin operations that need to access multiple tenants,
    or for testing purposes.

    Example:
        async with TenantContext(agent, admin_tenant_id):
            # Perform admin operation
            await agent.get_system_stats()
    """

    def __init__(self, agent: _TenantScoped, temporary_tenant_id: int) -> None:
        self.agent = agent
        self.temporary_tenant_id = temporary_tenant_id
        self.original_tenant_id: int | None = None

    async def __aenter__(self) -> "TenantContext":
        self.original_tenant_id = getattr(self.agent, "tenant_id", None)
        self.agent.tenant_id = self.temporary_tenant_id
        logger.info(
            f"Switched tenant context: {self.original_tenant_id} -> {self.temporary_tenant_id}",
            extra={
                "original_tenant": self.original_tenant_id,
                "temporary_tenant": self.temporary_tenant_id,
                "event": "tenant_context_switch",
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.agent.tenant_id = self.original_tenant_id
        logger.info(
            f"Restored tenant context: {self.temporary_tenant_id} -> {self.original_tenant_id}",
            extra={
                "restored_tenant": self.original_tenant_id,
                "event": "tenant_context_restore",
            },
        )


__all__ = [
    "validate_tenant_access",
    "require_tenant_id",
    "verify_tenant_isolation",
    "enforce_tenant_isolation",
    "TenantContext",
]
