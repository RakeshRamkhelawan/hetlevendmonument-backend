# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/ai_features/ (SP-API-007 Dag 2)
from typing import Any

from dependency_injector.wiring import Provide, inject  # noqa: F401

from src.core.api.v1.ai_features.router import router  # noqa: F401


# Compatibility stubs for DI factory functions used by src.core.container
def _build_learning_engine() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Factory function for adaptive learning engine (DI Container)."""
    from src.core.ai.adaptive_learning_engine import create_adaptive_learning_engine

    return create_adaptive_learning_engine()


def _build_intelligent_router() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Factory function for intelligent router (DI Container)."""
    from src.core.ai.intelligent_routing import create_intelligent_router

    return create_intelligent_router()


def _build_predictive_analytics() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Factory function for predictive analytics (DI Container)."""
    from src.core.ai.predictive_analytics import create_predictive_analytics_engine

    return create_predictive_analytics_engine()
