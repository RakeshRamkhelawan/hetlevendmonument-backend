"""Factory for creating StrategyEngine instances."""

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.core.strategy.facade import StrategyEngine

if TYPE_CHECKING:
    from src.core.strategy.repository import StrategyRepository

logger = logging.getLogger(__name__)

# Tenant-scoped engine cache
_tenant_strategy_engines: dict[int, StrategyEngine] = {}


def get_strategy_engine_for_tenant(
    tenant_id: int,
    repository: Optional["StrategyRepository"] = None,
) -> StrategyEngine:
    """Return a tenant-specific StrategyEngine (lazy-init, cached)."""
    if tenant_id not in _tenant_strategy_engines:
        _tenant_strategy_engines[tenant_id] = StrategyEngine(
            tenant_id=tenant_id, repository=repository
        )
    return _tenant_strategy_engines[tenant_id]


def get_strategy_engine(
    tenant_id: int | None = None,
    repository: Optional["StrategyRepository"] = None,
) -> StrategyEngine:
    """Get a strategy engine, optionally for a specific tenant."""
    if tenant_id is not None:
        return get_strategy_engine_for_tenant(tenant_id, repository)

    # Try to get from context
    try:
        from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

        ctx_tid = _ctx_tid()
        if ctx_tid:
            return get_strategy_engine_for_tenant(ctx_tid, repository)
    except Exception:
        pass

    # Return global instance for backward compatibility
    return _global_strategy_engine


# Global instance for backward compatibility
_global_strategy_engine = StrategyEngine()

# Legacy alias for backward compatibility
strategy_engine = _global_strategy_engine


async def develop_comprehensive_strategy(
    strategy_type: str,
    context_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None,
    repository: Optional["StrategyRepository"] = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Convenience function for strategy development.

    When tenant_id is provided the result is persisted and
    tenant-scoped. Otherwise falls back to the legacy global engine.
    """
    from src.core.strategy.types import StrategicContext, StrategyType

    engine = get_strategy_engine(tenant_id, repository)

    # Convert string to enum
    strategy_enum = (
        StrategyType(strategy_type)
        if strategy_type in [t.value for t in StrategyType]
        else StrategyType.BUSINESS_DEVELOPMENT
    )

    # Create strategic context
    context = StrategicContext(
        organization_goals=context_data.get("goals", ["growth", "innovation", "market_leadership"]),
        market_conditions=context_data.get("market", {}),
        competitive_landscape=context_data.get("competition", {}),
        internal_capabilities=context_data.get("capabilities", {}),
        constraints=context_data.get("constraints", {}),
        time_horizon=context_data.get("time_horizon", "12 months"),
        success_criteria=context_data.get("success_criteria", ["revenue_growth", "market_share"]),
    )

    return await engine.develop_strategy(strategy_enum, context)


class TenantContextError(Exception):
    """Raised when tenant context is required but not available."""

    pass


def resolve_strategy_engine() -> StrategyEngine:
    """Return tenant-scoped StrategyEngine or raise TenantContextError."""
    try:
        from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

        _tid = _ctx_tid()
        if _tid:
            return get_strategy_engine_for_tenant(_tid)
    except Exception:
        pass

    # P0 FIX: No fallback - enforce tenant context
    raise TenantContextError("Tenant context required for strategy engine")
