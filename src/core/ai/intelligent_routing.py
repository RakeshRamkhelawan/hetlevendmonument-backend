"""
Intelligent Routing - Dynamic request routing based on context and performance
Implements smart load balancing and context-aware routing decisions
"""

import asyncio
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from collections.abc import Callable

from src.core.caching.cache_layer import cached
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class RequestPriority(Enum):
    """Request priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RouteStatus(Enum):
    """Route status"""

    ACTIVE = "active"
    DEGRADED = "degraded"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class RoutingStrategy(Enum):
    """Routing strategies"""

    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LEAST_CONNECTIONS = "least_connections"
    RESPONSE_TIME = "response_time"
    CAPACITY_BASED = "capacity_based"
    CONTEXT_AWARE = "context_aware"


@dataclass
class RequestContext:
    """Context information for routing decisions"""

    request_id: str
    user_id: str | None
    session_id: str | None
    request_type: str
    priority: RequestPriority
    payload_size: int
    expected_complexity: str  # low, medium, high
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "request_type": self.request_type,
            "priority": self.priority.value,
            "payload_size": self.payload_size,
            "expected_complexity": self.expected_complexity,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RouteOption:
    """Available route option with performance metrics"""

    route_id: str
    endpoint: str
    agent_type: str
    capacity: int
    current_load: int
    avg_response_time: float
    success_rate: float
    status: RouteStatus
    weight: float = 1.0
    last_updated: datetime = field(default_factory=datetime.now)

    def get_load_percentage(self) -> float:
        """Get current load as percentage of capacity"""
        return (self.current_load / self.capacity * 100) if self.capacity > 0 else 100

    def is_available(self) -> bool:
        """Check if route is available for requests"""
        return (
            self.status in [RouteStatus.ACTIVE, RouteStatus.DEGRADED]
            and self.current_load < self.capacity
        )

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "route_id": self.route_id,
            "endpoint": self.endpoint,
            "agent_type": self.agent_type,
            "capacity": self.capacity,
            "current_load": self.current_load,
            "avg_response_time": self.avg_response_time,
            "success_rate": self.success_rate,
            "status": self.status.value,
            "weight": self.weight,
            "load_percentage": self.get_load_percentage(),
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class RoutingDecision:
    """Result of routing decision"""

    selected_route: RouteOption
    confidence: float
    reasoning: str
    alternative_routes: list[RouteOption]
    decision_time: float
    strategy_used: RoutingStrategy


class PerformanceTracker:
    """Tracks performance metrics for routes"""

    def __init__(self) -> None:
        self.metrics: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type
        self.response_times: dict[str, list[float]] = {}
        self.success_counts: dict[str, int] = {}
        self.failure_counts: dict[str, int] = {}

    def record_request(
        self,
        route_id: str,
        response_time: float,
        success: bool,
        context: RequestContext,
    ) -> None:
        """Record request metrics"""
        if route_id not in self.metrics:
            self.metrics[route_id] = []
            self.response_times[route_id] = []
            self.success_counts[route_id] = 0
            self.failure_counts[route_id] = 0

        # Record metrics
        metric = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_time": response_time,
            "success": success,
            "request_type": context.request_type,
            "priority": context.priority.value,
            "payload_size": context.payload_size,
            "complexity": context.expected_complexity,
        }
        self.metrics[route_id].append(metric)

        # Update response times (keep last 100)
        self.response_times[route_id].append(response_time)
        if len(self.response_times[route_id]) > 100:
            self.response_times[route_id] = self.response_times[route_id][-100:]

        # Update success/failure counts
        if success:
            self.success_counts[route_id] += 1
        else:
            self.failure_counts[route_id] += 1

        # Cleanup old metrics (keep last 1000)
        if len(self.metrics[route_id]) > 1000:
            self.metrics[route_id] = self.metrics[route_id][-1000:]

    def get_avg_response_time(self, route_id: str) -> float:
        """Get average response time for route"""
        if route_id not in self.response_times or not self.response_times[route_id]:
            return 0.0

        # Weight recent responses more heavily
        times = self.response_times[route_id]
        if len(times) <= 10:
            return statistics.mean(times)

        # Use weighted average with more weight on recent responses
        weights = [1 + (i / len(times)) for i in range(len(times))]
        weighted_sum = sum(time * weight for time, weight in zip(times, weights))
        total_weight = sum(weights)

        return weighted_sum / total_weight

    def get_success_rate(self, route_id: str) -> float:
        """Get success rate for route"""
        if route_id not in self.success_counts:
            return 1.0

        total = self.success_counts[route_id] + self.failure_counts[route_id]
        if total == 0:
            return 1.0

        return self.success_counts[route_id] / total

    def get_performance_trend(self, route_id: str, window_minutes: int = 30) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get performance trend for route"""
        if route_id not in self.metrics:
            return {"trend": "stable", "change_percentage": 0.0}

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        recent_metrics = [
            m
            for m in self.metrics[route_id]
            if datetime.fromisoformat(m["timestamp"]) >= cutoff_time
        ]

        if len(recent_metrics) < 5:
            return {"trend": "insufficient_data", "change_percentage": 0.0}

        # Calculate trend in response time
        recent_times = [m["response_time"] for m in recent_metrics]
        if len(recent_times) >= 10:
            # Compare first half with second half
            mid_point = len(recent_times) // 2
            first_half_avg = statistics.mean(recent_times[:mid_point])
            second_half_avg = statistics.mean(recent_times[mid_point:])

            if first_half_avg > 0:
                change_percentage = ((second_half_avg - first_half_avg) / first_half_avg) * 100

                if change_percentage > 20:
                    trend = "degrading"
                elif change_percentage < -20:
                    trend = "improving"
                else:
                    trend = "stable"

                return {"trend": trend, "change_percentage": change_percentage}

        return {"trend": "stable", "change_percentage": 0.0}


class IntelligentRouter:
    """
    Intelligent routing system that makes context-aware routing decisions
    Uses performance metrics and machine learning to optimize routing
    """

    def __init__(self) -> None:
        self.routes: dict[str, RouteOption] = {}
        self.performance_tracker = PerformanceTracker()
        self.routing_strategies: dict[RoutingStrategy, Callable[..., Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.default_strategy = RoutingStrategy.CONTEXT_AWARE
        self._initialized = False
        self._monitor_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "requests_routed": 0,
            "routing_decisions": 0,
            "average_decision_time": 0.0,
            "strategy_usage": {},
        }

    async def initialize(self) -> bool:
        """Initialize intelligent router"""
        try:
            # Setup routing strategies
            self._setup_routing_strategies()

            # Load route configurations
            await self._load_route_configurations()

            # Start performance monitoring (task stored for cleanup)
            self._monitor_task = asyncio.create_task(self._monitor_performance())

            self._initialized = True
            logger.info("Intelligent Router initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize intelligent router: {e}")
            return False

    async def register_route(self, route: RouteOption) -> bool:
        """Register a new route"""
        try:
            self.routes[route.route_id] = route
            logger.info(f"Registered route: {route.route_id} ({route.endpoint})")
            return True
        except Exception as e:
            logger.error(f"Failed to register route {route.route_id}: {e}")
            return False

    async def update_route_status(
        self,
        route_id: str,
        status: RouteStatus,
        metrics: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Update route status and metrics"""
        try:
            if route_id not in self.routes:
                return False

            route = self.routes[route_id]
            route.status = status
            route.last_updated = datetime.now(timezone.utc)

            if metrics:
                if "current_load" in metrics:
                    route.current_load = metrics["current_load"]
                if "capacity" in metrics:
                    route.capacity = metrics["capacity"]
                if "success_rate" in metrics:
                    route.success_rate = metrics["success_rate"]

            logger.debug(f"Updated route {route_id}: status={status.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to update route status: {e}")
            return False

    async def route_request(
        self, context: RequestContext, strategy: RoutingStrategy | None = None
    ) -> RoutingDecision | None:
        """Route request using intelligent decision making"""
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Select routing strategy
            selected_strategy = strategy or self._select_strategy(context)

            # Get available routes
            available_routes = self._get_available_routes(context)

            if not available_routes:
                logger.warning(f"No available routes for request {context.request_id}")
                return None

            # Apply routing strategy
            strategy_func = self.routing_strategies[selected_strategy]
            selected_route = await strategy_func(context, available_routes)

            if not selected_route:
                logger.warning(f"Strategy {selected_strategy.value} failed to select route")
                return None

            # Calculate decision confidence
            confidence = self._calculate_confidence(selected_route, available_routes, context)

            # Create routing decision
            decision_time = time.time() - start_time
            decision = RoutingDecision(
                selected_route=selected_route,
                confidence=confidence,
                reasoning=f"Selected using {selected_strategy.value} strategy",
                alternative_routes=[
                    r for r in available_routes if r.route_id != selected_route.route_id
                ][:3],
                decision_time=decision_time,
                strategy_used=selected_strategy,
            )

            # Update statistics
            self._update_routing_stats(selected_strategy, decision_time)

            # Update route load
            selected_route.current_load += 1

            logger.debug(f"Routed request {context.request_id} to {selected_route.route_id}")
            return decision

        except Exception as e:
            logger.error(f"Request routing failed: {e}")
            return None

    async def complete_request(
        self,
        route_id: str,
        context: RequestContext,
        response_time: float,
        success: bool,
    ) -> None:
        """Record completion of routed request"""
        try:
            # Update route load
            if route_id in self.routes:
                self.routes[route_id].current_load = max(0, self.routes[route_id].current_load - 1)

            # Record performance metrics
            self.performance_tracker.record_request(route_id, response_time, success, context)

            # Update route metrics
            if route_id in self.routes:
                route = self.routes[route_id]
                route.avg_response_time = self.performance_tracker.get_avg_response_time(route_id)
                route.success_rate = self.performance_tracker.get_success_rate(route_id)

            self._stats["requests_routed"] += 1

        except Exception as e:
            logger.error(f"Failed to complete request tracking: {e}")

    @cached(ttl=60, key_prefix="route_recommendations")  # NOTE: cached from cache_layer not typed
    async def get_route_recommendations(self, context: RequestContext) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get route recommendations with explanations"""
        try:
            available_routes = self._get_available_routes(context)

            recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for route in available_routes:
                score = self._calculate_route_score(route, context)
                performance_trend = self.performance_tracker.get_performance_trend(route.route_id)

                recommendation = {
                    "route_id": route.route_id,
                    "endpoint": route.endpoint,
                    "agent_type": route.agent_type,
                    "score": score,
                    "load_percentage": route.get_load_percentage(),
                    "avg_response_time": route.avg_response_time,
                    "success_rate": route.success_rate,
                    "status": route.status.value,
                    "performance_trend": performance_trend,
                    "recommendation": self._get_route_recommendation_text(
                        route, score, performance_trend
                    ),
                }
                recommendations.append(recommendation)

            # Sort by score
            recommendations.sort(key=lambda x: x["score"], reverse=True)

            return recommendations

        except Exception as e:
            logger.error(f"Failed to get route recommendations: {e}")
            return []

    async def get_routing_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get routing statistics"""
        try:
            total_routes = len(self.routes)
            active_routes = len([r for r in self.routes.values() if r.status == RouteStatus.ACTIVE])
            total_load = sum(r.current_load for r in self.routes.values())
            total_capacity = sum(r.capacity for r in self.routes.values())

            return {
                "total_routes": total_routes,
                "active_routes": active_routes,
                "degraded_routes": len(
                    [r for r in self.routes.values() if r.status == RouteStatus.DEGRADED]
                ),
                "inactive_routes": len(
                    [r for r in self.routes.values() if r.status == RouteStatus.INACTIVE]
                ),
                "total_load": total_load,
                "total_capacity": total_capacity,
                "capacity_utilization": (
                    (total_load / total_capacity * 100) if total_capacity > 0 else 0
                ),
                "requests_routed": self._stats["requests_routed"],
                "routing_decisions": self._stats["routing_decisions"],
                "average_decision_time_ms": round(self._stats["average_decision_time"] * 1000, 2),
                "strategy_usage": self._stats["strategy_usage"],
                "routes": [route.to_dict() for route in self.routes.values()],
            }

        except Exception as e:
            logger.error(f"Failed to get routing stats: {e}")
            return {}

    def _setup_routing_strategies(self) -> None:
        """Setup routing strategy functions"""
        self.routing_strategies = {
            RoutingStrategy.ROUND_ROBIN: self._route_round_robin,
            RoutingStrategy.WEIGHTED: self._route_weighted,
            RoutingStrategy.LEAST_CONNECTIONS: self._route_least_connections,
            RoutingStrategy.RESPONSE_TIME: self._route_response_time,
            RoutingStrategy.CAPACITY_BASED: self._route_capacity_based,
            RoutingStrategy.CONTEXT_AWARE: self._route_context_aware,
        }

    async def _load_route_configurations(self) -> None:
        """Load route configurations from settings"""
        try:
            # Default routes for testing
            api_base_url = os.getenv("API_BASE_URL")
            if not api_base_url:
                raise ValueError("API_BASE_URL environment variable required for agent routing")

            default_routes = [
                RouteOption(
                    route_id="cva_primary",
                    endpoint=f"{api_base_url}/api/v1/cva",
                    agent_type="cva",
                    capacity=10,
                    current_load=0,
                    avg_response_time=0.5,
                    success_rate=0.95,
                    status=RouteStatus.ACTIVE,
                ),
                RouteOption(
                    route_id="analytics_primary",
                    endpoint=f"{api_base_url}/api/v1/analytics",
                    agent_type="analytics",
                    capacity=15,
                    current_load=0,
                    avg_response_time=0.3,
                    success_rate=0.98,
                    status=RouteStatus.ACTIVE,
                ),
                RouteOption(
                    route_id="orchestrator_primary",
                    endpoint=f"{api_base_url}/api/v1/orchestrator",
                    agent_type="orchestrator",
                    capacity=5,
                    current_load=0,
                    avg_response_time=1.2,
                    success_rate=0.92,
                    status=RouteStatus.ACTIVE,
                ),
            ]

            for route in default_routes:
                await self.register_route(route)

        except Exception as e:
            logger.warning(f"Failed to load route configurations: {e}")

    async def _monitor_performance(self) -> None:
        """Background task to monitor route performance"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                for route_id, route in self.routes.items():
                    # Check for performance degradation
                    trend = self.performance_tracker.get_performance_trend(route_id)

                    if trend["trend"] == "degrading" and route.status == RouteStatus.ACTIVE:
                        logger.warning(f"Performance degradation detected for route {route_id}")
                        await self.update_route_status(route_id, RouteStatus.DEGRADED)

                    elif trend["trend"] == "improving" and route.status == RouteStatus.DEGRADED:
                        logger.info(f"Performance improvement detected for route {route_id}")
                        await self.update_route_status(route_id, RouteStatus.ACTIVE)

            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    def _select_strategy(self, context: RequestContext) -> RoutingStrategy:
        """Select appropriate routing strategy based on context"""
        # High priority requests use response time strategy
        if context.priority in [RequestPriority.HIGH, RequestPriority.CRITICAL]:
            return RoutingStrategy.RESPONSE_TIME

        # Large payloads use capacity-based strategy
        if context.payload_size > 1024 * 1024:  # 1MB
            return RoutingStrategy.CAPACITY_BASED

        # Complex requests use context-aware strategy
        if context.expected_complexity == "high":
            return RoutingStrategy.CONTEXT_AWARE

        return self.default_strategy

    def _get_available_routes(self, context: RequestContext) -> list[RouteOption]:
        """Get routes available for the request context"""
        available_routes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for route in self.routes.values():
            if route.is_available():
                # Filter by agent type if specified in context
                agent_type = context.metadata.get("preferred_agent_type")
                if agent_type and route.agent_type != agent_type:
                    continue

                available_routes.append(route)

        return available_routes

    async def _route_round_robin(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Round robin routing strategy"""
        if not routes:
            return None

        # Simple round robin based on request count
        request_count: int = int(self._stats["requests_routed"])
        selected_index = request_count % len(routes)
        return routes[selected_index]

    async def _route_weighted(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Weighted routing strategy"""
        if not routes:
            return None

        # Calculate weighted selection based on route weights and performance
        weights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for route in routes:
            weight = route.weight * route.success_rate * (1 - route.get_load_percentage() / 100)
            weights.append(max(0.1, weight))  # Minimum weight

        # Select based on weights
        total_weight = sum(weights)
        if total_weight == 0:
            return routes[0]

        import random

        r = random.uniform(0, total_weight)
        cumulative_weight = 0

        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if r <= cumulative_weight:
                return routes[i]

        return routes[-1]

    async def _route_least_connections(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Least connections routing strategy"""
        if not routes:
            return None

        # Select route with lowest current load percentage
        return min(routes, key=lambda r: r.get_load_percentage())

    async def _route_response_time(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Response time based routing strategy"""
        if not routes:
            return None

        # Select route with best response time, considering load
        def score_route(route: RouteOption) -> float:
            load_penalty = route.get_load_percentage() / 100 * 0.5  # 50% penalty for load
            response_time_score = 1 / (route.avg_response_time + 0.1)  # Avoid division by zero
            return response_time_score * (1 - load_penalty) * route.success_rate

        return max(routes, key=score_route)

    async def _route_capacity_based(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Capacity based routing strategy"""
        if not routes:
            return None

        # Select route with most available capacity
        def available_capacity(route: RouteOption) -> int:
            return route.capacity - route.current_load

        return max(routes, key=available_capacity)

    async def _route_context_aware(
        self, context: RequestContext, routes: list[RouteOption]
    ) -> RouteOption | None:
        """Context aware routing strategy"""
        if not routes:
            return None

        # Score routes based on multiple factors
        def comprehensive_score(route: RouteOption) -> float:
            # Base score from performance
            performance_score = route.success_rate * (1 / (route.avg_response_time + 0.1))

            # Load factor (prefer less loaded routes)
            load_factor = 1 - (route.get_load_percentage() / 100)

            # Priority factor
            priority_factor = 1.0
            if context.priority == RequestPriority.CRITICAL:
                priority_factor = 1.5
            elif context.priority == RequestPriority.HIGH:
                priority_factor = 1.2

            # Complexity factor
            complexity_factor = 1.0
            if context.expected_complexity == "high" and route.capacity > 5:
                complexity_factor = 1.3

            return performance_score * load_factor * priority_factor * complexity_factor

        return max(routes, key=comprehensive_score)

    def _calculate_confidence(
        self,
        selected_route: RouteOption,
        available_routes: list[RouteOption],
        context: RequestContext,
    ) -> float:
        """Calculate confidence in routing decision"""
        if len(available_routes) <= 1:
            return 1.0

        # Calculate score for selected route
        selected_score = self._calculate_route_score(selected_route, context)

        # Calculate scores for other routes
        other_scores = [
            self._calculate_route_score(route, context)
            for route in available_routes
            if route.route_id != selected_route.route_id
        ]

        if not other_scores:
            return 1.0

        # Confidence based on score difference
        max_other_score = max(other_scores)
        if max_other_score == 0:
            return 1.0

        score_ratio = selected_score / max_other_score
        confidence = min(1.0, score_ratio - 0.5) if score_ratio > 0.5 else 0.1

        return confidence

    def _calculate_route_score(self, route: RouteOption, context: RequestContext) -> float:
        """Calculate overall score for route"""
        # Performance score
        performance_score = route.success_rate * (1 / (route.avg_response_time + 0.1))

        # Availability score
        availability_score = 1 - (route.get_load_percentage() / 100)

        # Status score
        status_scores = {
            RouteStatus.ACTIVE: 1.0,
            RouteStatus.DEGRADED: 0.7,
            RouteStatus.INACTIVE: 0.0,
            RouteStatus.MAINTENANCE: 0.0,
        }
        status_score = status_scores.get(route.status, 0.0)

        return performance_score * availability_score * status_score

    def _get_route_recommendation_text(
        self, route: RouteOption, score: float, performance_trend: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Generate recommendation text for route"""
        if score > 0.8:
            recommendation = "Excellent choice"
        elif score > 0.6:
            recommendation = "Good option"
        elif score > 0.4:
            recommendation = "Acceptable"
        else:
            recommendation = "Consider alternatives"

        if performance_trend["trend"] == "degrading":
            recommendation += " (performance declining)"
        elif performance_trend["trend"] == "improving":
            recommendation += " (performance improving)"

        return recommendation

    def _update_routing_stats(self, strategy: RoutingStrategy, decision_time: float) -> None:
        """Update routing statistics"""
        self._stats["routing_decisions"] += 1

        # Update average decision time
        current_avg = self._stats["average_decision_time"]
        count = self._stats["routing_decisions"]
        self._stats["average_decision_time"] = ((current_avg * (count - 1)) + decision_time) / count

        # Update strategy usage
        strategy_name = strategy.value
        self._stats["strategy_usage"][strategy_name] = (
            self._stats["strategy_usage"].get(strategy_name, 0) + 1
        )

    async def route(self, context: RequestContext) -> Optional["RoutingDecision"]:
        """Alias method for route_request - main routing method for API compatibility"""
        return await self.route_request(context)

    async def get_available_routes(self) -> int:
        """Get number of available routes"""
        available = [r for r in self.routes.values() if r.is_available()]
        return len(available)

    async def get_average_decision_time(self) -> float:
        """Get average decision time in milliseconds"""
        return (
            round(self._stats["average_decision_time"] * 1000, 2)
            if self._stats["routing_decisions"] > 0
            else 0.0
        )

    async def cleanup(self) -> None:
        """Cleanup background tasks - call this in test teardown"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass  # Expected


# Factory function
async def create_intelligent_router() -> IntelligentRouter:
    """Create and initialize intelligent router"""
    router = IntelligentRouter()
    await router.initialize()
    return router


# Global router instance
_global_router: IntelligentRouter | None = None


async def get_intelligent_router() -> IntelligentRouter:
    """Get global intelligent router instance"""
    global _global_router

    if _global_router is None:
        _global_router = await create_intelligent_router()

    return _global_router
