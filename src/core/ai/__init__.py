from typing import Any

"""
Core AI Module - Advanced AI capabilities for M-MDP system
Provides adaptive learning, intelligent routing, and predictive analytics
ASCII-only compliance enforced

LAZY LOADING: All imports are deferred to avoid circular dependencies
between core.ai <-> core.learning modules.
"""


def get_adaptive_learning_engine() -> tuple:  # type: ignore[type-arg]
    """Lazy-load AdaptiveLearningEngine (avoids circular import with core.learning)"""
    from .adaptive_learning_engine import (
        AdaptationInsight,
        AdaptiveLearningEngine,
        LearningEvent,
        create_adaptive_learning_engine,
    )

    return (
        AdaptiveLearningEngine,
        LearningEvent,
        AdaptationInsight,
        create_adaptive_learning_engine,
    )


def get_intelligent_routing() -> tuple:  # type: ignore[type-arg]
    """Lazy-load IntelligentRouter"""
    from .intelligent_routing import (
        IntelligentRouter,
        RequestContext,
        RequestPriority,
        RouteOption,
        create_intelligent_router,
    )

    return (
        IntelligentRouter,
        RequestContext,
        RouteOption,
        RequestPriority,
        create_intelligent_router,
    )


def get_predictive_analytics() -> tuple:  # type: ignore[type-arg]
    """Lazy-load PredictiveAnalyticsEngine"""
    from .predictive_analytics import (
        PredictionRequest,
        PredictionType,
        PredictiveAnalyticsEngine,
        TimeHorizon,
        create_predictive_analytics_engine,
    )

    return (
        PredictiveAnalyticsEngine,
        PredictionRequest,
        PredictionType,
        TimeHorizon,
        create_predictive_analytics_engine,
    )


__all__ = [
    "get_adaptive_learning_engine",
    "get_intelligent_routing",
    "get_predictive_analytics",
]
