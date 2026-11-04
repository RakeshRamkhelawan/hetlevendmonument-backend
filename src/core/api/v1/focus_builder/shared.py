"""
Shared helpers for FocusBuilder sub-routers (ADR-033).

Centralises helpers used across flows_router, execution_router,
pieces_router, ai_router and ws_router.
"""

import functools
import inspect
from typing import TYPE_CHECKING, Any, Callable, cast

from fastapi import Depends

if TYPE_CHECKING:
    from src.domains.flows.service import FocusBuilderService
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

# OpenTelemetry tracing (optional) - handle version mismatches gracefully
try:
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
except (ImportError, TypeError):
    trace = None  # type: ignore[assignment]
    tracer = None  # type: ignore[assignment]

from src.core.api.v1.focus_builder.dependencies import get_db  # own-domain -- ADR-033
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.utils.best_effort import best_effort


class _LazyLimiter:
    """Proxy for slowapi.Limiter that defers creation until first request.

    Router modules can apply ``@limiter.limit(...)`` at import time without
    paying the import/initialization cost of slowapi during startup.
    """

    def __init__(self) -> None:
        self._limiter: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._decorated: dict[int, Callable[..., Any]] = {}

    def _get_limiter(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        if self._limiter is None:
            from src.core.middleware.rate_limiter import get_limiter

            self._limiter = get_limiter()
        return self._limiter

    def limit(
        self, limit_value: str, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            func_id = id(func)

            @functools.wraps(func)
            async def async_wrapper(*f_args: Any, **f_kwargs: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
                if func_id not in self._decorated:
                    self._decorated[func_id] = self._get_limiter().limit(
                        limit_value, *args, **kwargs
                    )(func)
                return await self._decorated[func_id](*f_args, **f_kwargs)

            @functools.wraps(func)
            def sync_wrapper(*f_args: Any, **f_kwargs: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
                if func_id not in self._decorated:
                    self._decorated[func_id] = self._get_limiter().limit(
                        limit_value, *args, **kwargs
                    )(func)
                return self._decorated[func_id](*f_args, **f_kwargs)

            wrapper = async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
            return wrapper

        return decorator


limiter = _LazyLimiter()


def enrich_span(request: Any, user_id: int | None, **kwargs: Any) -> None:
    """Add contextual attributes to OpenTelemetry span for Jaeger filtering."""
    if trace is None:
        return
    span = trace.get_current_span()
    if span and span.is_recording():
        if user_id is not None:
            span.set_attribute("user.id", user_id)
        if hasattr(request.state, "tenant_id") and request.state.tenant_id:
            span.set_attribute("tenant.id", str(request.state.tenant_id))
        for key, value in kwargs.items():
            if value is not None:
                span.set_attribute(f"focus_builder.{key}", str(value))


async def get_focus_builder_service(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
) -> "FocusBuilderService":
    """Dependency that provides tenant-scoped FocusBuilderService."""
    from src.domains.flows.service import FocusBuilderService

    return FocusBuilderService(db=db, tenant_id=tenant_id)


async def _track_focus_builder_action(
    db: AsyncSession,
    user_id: int,
    tenant_id: int,
    session_id: str,
    behavior_type: str,
    context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> None:
    """Track a Focus Builder action via the Digital Twin (best-effort)."""
    from src.core.api.v1.focus_builder.dependencies import (  # own-domain -- ADR-033
        create_practical_twin_service,
    )

    async with best_effort("focus_builder_twin_track", db_session=db):
        service = await create_practical_twin_service(db=db, tenant_id=tenant_id)
        await service.track_behavior(
            user_id=str(user_id),
            tenant_id=tenant_id,
            session_id=session_id,
            behavior_type=behavior_type,
            context=context,
        )


def create_error_response(
    code: str, message: str, details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a structured error response."""
    response: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        response["error"]["details"] = details
    return response


class WSUser:
    """Minimal user object for WebSocket authentication."""

    def __init__(self, user_id: int, tenant_id: int) -> None:
        self.id = user_id
        self.tenant_id = tenant_id


async def validate_ws_token(token: str) -> WSUser:
    """
    Validate JWT token for WebSocket authentication.

    Returns:
        WSUser object if valid

    Raises:
        Exception if token is invalid or expired
    """
    from src.core.api.dependencies import verify_token

    try:
        payload = verify_token(token)
        if payload is None:
            raise ValueError("Invalid token payload")

        from src.core.api.dependencies import token_mag_op_een_websocket

        # Geen portaaltoken, account ingeschakeld (uitgeschakeld is uitgeschakeld; 2026-10-12/13).
        if not await token_mag_op_een_websocket(payload):
            raise ValueError("Token not allowed on a websocket")

        return WSUser(
            user_id=cast(int, payload.get("sub")),
            tenant_id=cast(int, payload.get("tenant_id")),
        )
    except Exception as e:
        logger.error(
            "WebSocket token validation failed: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise


async def verify_flow_exists(flow_id: int, db: AsyncSession, tenant_id: int) -> bool:
    """
    Verify that a flow exists and belongs to the tenant.

    Returns:
        True if flow exists, False otherwise
    """
    try:
        from src.domains.flows.service import FocusBuilderService

        service = FocusBuilderService(db=db, tenant_id=tenant_id)
        flow = await service.repository.get(flow_id)
        return flow is not None
    except Exception as e:
        logger.error("Error checking flow existence: %s: %s", type(e).__name__, e, exc_info=True)
        return False
