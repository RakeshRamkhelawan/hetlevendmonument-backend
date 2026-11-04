"""
Core Optimization Module - System performance optimization and tuning
Provides performance optimization, system tuning, and resource management
ASCII-only compliance enforced
"""

from .performance_optimizer import (
    OptimizationResult,
    OptimizationType,
    PerformanceOptimizer,
    create_performance_optimizer,
)
from .system_tuner import (
    SystemTuner,
    TuningConfiguration,
    TuningStrategy,
    get_system_tuner,
)

# Optional imports - intentionally deferred to Phase 22+ (post-MVP optimization features)
try:
    from .cache_optimizer import (  # type: ignore[import-not-found]
        CacheMetrics,
        CacheOptimizer,
        CacheStrategy,
    )
except ImportError:  # pragma: no cover - optional module, Phase 22+
    CacheMetrics = None
    CacheOptimizer = None
    CacheStrategy = None

try:
    from .query_optimizer import (  # type: ignore[import-not-found]
        QueryMetrics,
        QueryOptimizer,
        QueryPlan,
    )
except ImportError:  # pragma: no cover - optional module, Phase 22+
    QueryMetrics = None
    QueryOptimizer = None
    QueryPlan = None

try:
    from .resource_manager import (  # type: ignore[import-not-found]
        ResourceManager,
        ResourceMetrics,
        ResourcePolicy,
    )
except ImportError:  # pragma: no cover - optional module, Phase 22+
    ResourceManager = None
    ResourceMetrics = None
    ResourcePolicy = None

__all__ = [
    "PerformanceOptimizer",
    "OptimizationResult",
    "OptimizationType",
    "create_performance_optimizer",
    "SystemTuner",
    "TuningConfiguration",
    "TuningStrategy",
    "get_system_tuner",
    "ResourceManager",
    "ResourceMetrics",
    "ResourcePolicy",
    "QueryOptimizer",
    "QueryPlan",
    "QueryMetrics",
    "CacheOptimizer",
    "CacheStrategy",
    "CacheMetrics",
]
