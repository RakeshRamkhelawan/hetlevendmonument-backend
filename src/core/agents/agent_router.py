"""
Agent Router - P4.5.1 Intelligent Agent Selection with Caching
Implements LLM-based agent selection, intelligent routing decisions, and performance caching

Features:
    - LLM-based agent selection based on task requirements
    - Multi-strategy routing (performance, cost, capability-based)
    - Request-level caching for repeated queries
    - Agent performance metrics tracking
    - Intelligent fallback strategies
    - Tenant-isolated routing decisions

Architecture:
    - RouteCache: In-memory cache for routing decisions
    - AgentRouter: Main routing engine with LLM integration
    - RoutingContext: Request context for routing decisions
    - RoutingMetrics: Performance metrics for routing decisions
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from src.core.middleware.tenant_context import get_tenant_id
from src.core.shared.production_logging import SafeLogger
from src.core.types import AgentType

logger = SafeLogger(__name__)

if TYPE_CHECKING:
    from src.core.caching.cache_layer import get_cache_manager

# Try to import caching layer (optional, graceful degradation)
try:
    from src.core.caching.cache_layer import get_cache_manager

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    logger.warning("Cache layer not available - routing caching disabled")


class RoutingStrategy(str, Enum):
    """Agent selection strategies"""

    PERFORMANCE_BASED = "performance_based"
    CAPABILITY_MATCH = "capability_match"
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    AVAILABILITY_BASED = "availability_based"
    WEIGHTED_SCORE = "weighted_score"
    LLM_BASED = "llm_based"
    ROUND_ROBIN = "round_robin"


class CacheStrategy(str, Enum):
    """Caching strategies for routing decisions"""

    TTL_BASED = "ttl_based"
    LRU = "lru"
    ADAPTIVE = "adaptive"


@dataclass
class RoutingContext:
    """Context information for routing decisions"""

    request_id: str
    task_type: str
    task_description: str
    required_capabilities: list[str] = field(default_factory=list)
    priority: int = 5
    complexity_score: float = 0.5
    user_id: str | None = None
    preferred_agents: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=datetime.now)

    def to_cache_key(self) -> str:
        """Generate cache key from context"""
        key_data = {
            "task_type": self.task_type,
            "required_capabilities": sorted(self.required_capabilities),
            "priority": self.priority,
            "complexity_score": round(self.complexity_score, 2),
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]


@dataclass
class RoutingDecision:
    """Result of routing decision"""

    primary_agent: str
    secondary_agents: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    reasoning: str = ""
    strategy_used: RoutingStrategy = RoutingStrategy.PERFORMANCE_BASED
    routing_cost: float = 0.0
    estimated_latency: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    cached: bool = False


@dataclass
class AgentMetrics:
    """Performance metrics for agents"""

    agent_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_execution_time: float = 0.0
    success_rate: float = 0.95
    availability_score: float = 1.0
    cost_per_request: float = 0.0
    last_used: datetime | None = None
    last_failed: datetime | None = None
    consecutive_failures: int = 0

    @property
    def health_score(self) -> float:
        """Calculate overall health score (0.0 - 1.0)"""
        if self.consecutive_failures > 3:
            return 0.0
        if self.consecutive_failures > 1:
            return 0.5

        base_score = (self.success_rate / 100.0) * 0.5
        availability_component = self.availability_score * 0.3
        latency_component = max(0.0, 1.0 - (self.avg_execution_time / 10.0)) * 0.2

        return min(1.0, base_score + availability_component + latency_component)

    @property
    def routing_score(self, strategy: RoutingStrategy = RoutingStrategy.WEIGHTED_SCORE) -> float:
        """Calculate routing score based on metrics"""
        if strategy == RoutingStrategy.PERFORMANCE_BASED:
            return self.health_score
        elif strategy == RoutingStrategy.COST_OPTIMIZED:
            return 1.0 - (self.cost_per_request / 1.0)  # Normalize cost
        elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            return max(0.0, 1.0 - (self.avg_execution_time / 10.0))
        elif strategy == RoutingStrategy.AVAILABILITY_BASED:
            return self.availability_score
        else:
            return self.health_score


class RouteCache:
    """In-memory cache for routing decisions with TTL and LRU support"""

    def __init__(
        self,
        max_size: int = 10000,
        default_ttl: int = 300,
        strategy: CacheStrategy = CacheStrategy.ADAPTIVE,
    ) -> None:
        self.cache: dict[str, tuple[RoutingDecision, datetime]] = {}
        self.access_times: dict[str, datetime] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        self.hits = 0
        self.misses = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> RoutingDecision | None:
        """Retrieve cached routing decision"""
        async with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None

            decision, timestamp = self.cache[key]

            # Check TTL
            if datetime.now(timezone.utc) - timestamp > timedelta(seconds=self.default_ttl):
                del self.cache[key]
                self.misses += 1
                return None

            self.hits += 1
            self.access_times[key] = datetime.now(timezone.utc)
            return decision

    async def set(self, key: str, decision: RoutingDecision) -> None:
        """Cache a routing decision"""
        async with self._lock:
            # Evict if necessary
            if len(self.cache) >= self.max_size:
                if self.strategy == CacheStrategy.LRU:
                    lru_key = min(
                        self.access_times,
                        key=lambda k: self.access_times.get(k, datetime.min),
                    )
                    del self.cache[lru_key]
                    del self.access_times[lru_key]
                else:  # TTL-based or ADAPTIVE
                    oldest_key = min(self.cache, key=lambda k: self.cache[k][1])
                    del self.cache[oldest_key]
                    if oldest_key in self.access_times:
                        del self.access_times[oldest_key]

            self.cache[key] = (decision, datetime.now(timezone.utc))
            self.access_times[key] = datetime.now(timezone.utc)

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern"""
        async with self._lock:
            keys_to_delete = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self.cache[key]
                if key in self.access_times:
                    del self.access_times[key]
            return len(keys_to_delete)

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics"""
        async with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                "total_entries": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "strategy": self.strategy.value,
            }

    async def clear(self) -> None:
        """Clear all cached entries"""
        async with self._lock:
            self.cache.clear()
            self.access_times.clear()
            self.hits = 0
            self.misses = 0


class AgentRouter:
    """Intelligent agent router with LLM-based selection and caching"""

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.WEIGHTED_SCORE,
        enable_caching: bool = True,
        cache_ttl: int = 300,
    ) -> None:
        self.strategy = strategy
        self.enable_caching = enable_caching and CACHE_AVAILABLE
        self.cache = RouteCache(default_ttl=cache_ttl)

        # Agent metrics tracking
        self.agent_metrics: dict[str, AgentMetrics] = {}
        self.agent_capabilities: dict[str, set[str]] = defaultdict(set)

        # Routing history and statistics
        self.routing_history: list[RoutingDecision] = []
        self.routing_stats = {
            "total_routings": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_confidence": 0.0,
        }

        # LLM client for intelligent routing (optional)
        self._llm_client = None
        self._initialized = False

        logger.info(
            f"AgentRouter initialized with strategy={strategy.value}, caching={self.enable_caching}"
        )

    async def initialize(self, llm_client: Any | None = None) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Initialize router with LLM client"""
        try:
            self._llm_client = llm_client
            self._initialized = True
            logger.info("AgentRouter initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize AgentRouter: {e}")
            return False

    async def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        capabilities: list[str] | None = None,
    ) -> bool:
        """Register an agent in the routing system"""
        try:
            if agent_id not in self.agent_metrics:
                self.agent_metrics[agent_id] = AgentMetrics(agent_id=agent_id)

            if capabilities:
                self.agent_capabilities[agent_id] = set(capabilities)

            logger.info(f"Registered agent {agent_id} with capabilities {capabilities}")
            return True
        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False

    async def route(self, context: RoutingContext) -> RoutingDecision:
        """Route request to appropriate agent"""
        try:
            tenant_id = get_tenant_id()

            # Try cache first
            if self.enable_caching:
                cache_key = f"{tenant_id}:{context.to_cache_key()}"
                cached_decision = await self.cache.get(cache_key)
                if cached_decision:
                    self.routing_stats["cache_hits"] += 1
                    cached_decision.cached = True
                    logger.debug(f"Routing decision from cache: {context.request_id}")
                    return cached_decision

            self.routing_stats["cache_misses"] += 1

            # Route based on strategy
            if self.strategy == RoutingStrategy.LLM_BASED and self._llm_client:
                decision = await self._route_llm_based(context)
            elif self.strategy == RoutingStrategy.CAPABILITY_MATCH:
                decision = await self._route_capability_match(context)
            elif self.strategy == RoutingStrategy.PERFORMANCE_BASED:
                decision = await self._route_performance_based(context)
            elif self.strategy == RoutingStrategy.COST_OPTIMIZED:
                decision = await self._route_cost_optimized(context)
            else:
                decision = await self._route_weighted_score(context)

            # Cache decision
            if self.enable_caching:
                cache_key = f"{tenant_id}:{context.to_cache_key()}"
                await self.cache.set(cache_key, decision)

            # Record metrics
            self.routing_history.append(decision)
            self.routing_stats["total_routings"] += 1
            self._update_routing_stats(decision)

            return decision

        except Exception as e:
            logger.error(f"Routing error for request {context.request_id}: {e}")
            return RoutingDecision(
                primary_agent=self._get_fallback_agent(),
                reasoning=f"Routing error: {str(e)}",
                strategy_used=self.strategy,
            )

    async def _route_llm_based(self, context: RoutingContext) -> RoutingDecision:
        """Route using LLM-based decision making"""
        if not self._llm_client:
            logger.warning("LLM client not available, falling back to performance-based routing")
            return await self._route_performance_based(context)

        try:
            # Prepare prompt for LLM
            prompt = self._prepare_routing_prompt(context)

            # Call LLM for agent selection
            response = await self._llm_client.generate(prompt)

            # Parse LLM response
            agent_id, confidence, reasoning = self._parse_llm_response(response)

            # Get secondary agents
            secondary_agents = await self._get_secondary_agents(context, agent_id)

            return RoutingDecision(
                primary_agent=agent_id,
                secondary_agents=secondary_agents,
                confidence_score=confidence,
                reasoning=reasoning,
                strategy_used=RoutingStrategy.LLM_BASED,
            )
        except Exception as e:
            logger.error(f"LLM-based routing error: {e}")
            return await self._route_performance_based(context)

    async def _route_capability_match(self, context: RoutingContext) -> RoutingDecision:
        """Route based on capability matching"""
        try:
            best_agent = None
            best_match_score = 0.0
            candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent_id, capabilities in self.agent_capabilities.items():
                if agent_id not in self.agent_metrics:
                    continue

                # Calculate capability match score
                required = set(context.required_capabilities)
                available = capabilities
                if required:
                    match_score = len(required & available) / len(required) if required else 1.0
                else:
                    match_score = 1.0

                # Apply health score
                health_score = self.agent_metrics[agent_id].health_score
                total_score = match_score * 0.7 + health_score * 0.3

                candidates.append((agent_id, total_score))

                if total_score > best_match_score:
                    best_match_score = total_score
                    best_agent = agent_id

            candidates.sort(key=lambda x: x[1], reverse=True)
            secondary = [a for a, _ in candidates[1:3]]

            return RoutingDecision(
                primary_agent=best_agent or self._get_fallback_agent(),
                secondary_agents=secondary,
                confidence_score=min(best_match_score, 1.0),
                reasoning=f"Selected based on capability match (match_score={best_match_score:.2f})",
                strategy_used=RoutingStrategy.CAPABILITY_MATCH,
            )
        except Exception as e:
            logger.error(f"Capability match routing error: {e}")
            return await self._route_performance_based(context)

    async def _route_performance_based(self, context: RoutingContext) -> RoutingDecision:
        """Route based on agent performance metrics"""
        try:
            best_agent = None
            best_score = -1.0
            candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent_id, metrics in self.agent_metrics.items():
                score = metrics.health_score
                candidates.append((agent_id, score))

                if score > best_score:
                    best_score = score
                    best_agent = agent_id

            candidates.sort(key=lambda x: x[1], reverse=True)
            secondary = [a for a, _ in candidates[1:3]]

            return RoutingDecision(
                primary_agent=best_agent or self._get_fallback_agent(),
                secondary_agents=secondary,
                confidence_score=min(best_score, 1.0),
                reasoning=f"Selected based on performance metrics (health_score={best_score:.2f})",
                strategy_used=RoutingStrategy.PERFORMANCE_BASED,
            )
        except Exception as e:
            logger.error(f"Performance-based routing error: {e}")
            return RoutingDecision(
                primary_agent=self._get_fallback_agent(),
                reasoning=f"Routing error: {e}",
            )

    async def _route_cost_optimized(self, context: RoutingContext) -> RoutingDecision:
        """Route based on cost optimization"""
        try:
            best_agent = None
            best_score = -1.0
            candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent_id, metrics in self.agent_metrics.items():
                # Cost efficiency (lower cost is better)
                cost_efficiency = 1.0 - (metrics.cost_per_request / 1.0)
                health_score = metrics.health_score
                score = cost_efficiency * 0.6 + health_score * 0.4

                candidates.append((agent_id, score))

                if score > best_score:
                    best_score = score
                    best_agent = agent_id

            candidates.sort(key=lambda x: x[1], reverse=True)
            secondary = [a for a, _ in candidates[1:3]]

            return RoutingDecision(
                primary_agent=best_agent or self._get_fallback_agent(),
                secondary_agents=secondary,
                confidence_score=min(best_score, 1.0),
                reasoning=f"Selected based on cost optimization (cost_score={best_score:.2f})",
                strategy_used=RoutingStrategy.COST_OPTIMIZED,
            )
        except Exception as e:
            logger.error(f"Cost-optimized routing error: {e}")
            return await self._route_performance_based(context)

    async def _route_weighted_score(self, context: RoutingContext) -> RoutingDecision:
        """Route using weighted scoring of all metrics"""
        try:
            best_agent = None
            best_score = -1.0
            candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for agent_id, metrics in self.agent_metrics.items():
                # Weighted combination of metrics
                health_weight = metrics.health_score * 0.4
                availability = metrics.availability_score * 0.3
                cost_efficiency = (1.0 - metrics.cost_per_request / 1.0) * 0.15
                latency = max(0.0, 1.0 - (metrics.avg_execution_time / 10.0)) * 0.15

                score = health_weight + availability + cost_efficiency + latency
                candidates.append((agent_id, score))

                if score > best_score:
                    best_score = score
                    best_agent = agent_id

            candidates.sort(key=lambda x: x[1], reverse=True)
            secondary = [a for a, _ in candidates[1:3]]

            return RoutingDecision(
                primary_agent=best_agent or self._get_fallback_agent(),
                secondary_agents=secondary,
                confidence_score=min(best_score, 1.0),
                reasoning=f"Selected based on weighted scoring (score={best_score:.2f})",
                strategy_used=RoutingStrategy.WEIGHTED_SCORE,
            )
        except Exception as e:
            logger.error(f"Weighted score routing error: {e}")
            return RoutingDecision(
                primary_agent=self._get_fallback_agent(),
                reasoning=f"Routing error: {e}",
            )

    async def _get_secondary_agents(self, context: RoutingContext, primary: str) -> list[str]:
        """Get list of secondary (fallback) agents"""
        candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id, metrics in self.agent_metrics.items():
            if agent_id != primary:
                candidates.append((agent_id, metrics.health_score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [agent_id for agent_id, _ in candidates[:2]]

    async def update_agent_metrics(
        self,
        agent_id: str,
        execution_time: float,
        success: bool,
        cost: float = 0.0,
    ) -> None:
        """Update agent performance metrics after execution"""
        try:
            if agent_id not in self.agent_metrics:
                return

            metrics = self.agent_metrics[agent_id]
            metrics.total_requests += 1

            if success:
                metrics.successful_requests += 1
                metrics.consecutive_failures = 0
                metrics.last_used = datetime.now(timezone.utc)
            else:
                metrics.failed_requests += 1
                metrics.consecutive_failures += 1
                metrics.last_failed = datetime.now(timezone.utc)

            # Update running averages
            total_time = metrics.avg_execution_time * (metrics.total_requests - 1) + execution_time
            metrics.avg_execution_time = total_time / metrics.total_requests
            metrics.success_rate = (metrics.successful_requests / metrics.total_requests) * 100

        except Exception as e:
            logger.error(f"Error updating metrics for {agent_id}: {e}")

    def _prepare_routing_prompt(self, context: RoutingContext) -> str:
        """Prepare prompt for LLM-based routing"""
        prompt = f"""
Select the best agent for this task. Return JSON with agent_id, confidence (0-1), and reasoning.

Task Type: {context.task_type}
Description: {context.task_description}
Required Capabilities: {", ".join(context.required_capabilities)}
Priority: {context.priority}
Complexity: {context.complexity_score}

Available Agents and Their Metrics:
"""
        for agent_id, metrics in self.agent_metrics.items():
            capabilities = ", ".join(self.agent_capabilities.get(agent_id, []))
            prompt += f"\n- {agent_id}: capabilities=[{capabilities}], health={metrics.health_score:.2f}, cost={metrics.cost_per_request:.4f}"

        prompt += (
            '\n\nRespond in JSON format: {"agent_id": "...", "confidence": 0.0, "reasoning": "..."}'
        )
        return prompt

    def _parse_llm_response(self, response: str) -> tuple[str, float, str]:
        """Parse LLM response for routing decision"""
        try:
            data = json.loads(response)
            agent_id = data.get("agent_id", self._get_fallback_agent())
            confidence = float(data.get("confidence", 0.7))
            reasoning = data.get("reasoning", "LLM-based selection")
            return agent_id, min(confidence, 1.0), reasoning
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return self._get_fallback_agent(), 0.5, "Failed to parse LLM response"

    def _get_fallback_agent(self) -> str:
        """Get fallback agent when routing fails"""
        if not self.agent_metrics:
            return "generic"
        return max(self.agent_metrics.items(), key=lambda x: x[1].health_score)[0]

    def _update_routing_stats(self, decision: RoutingDecision) -> None:
        """Update routing statistics"""
        if self.routing_stats["total_routings"] == 0:
            self.routing_stats["avg_confidence"] = decision.confidence_score
        else:
            current_avg = self.routing_stats["avg_confidence"]
            total = self.routing_stats["total_routings"]
            self.routing_stats["avg_confidence"] = (
                current_avg * total + decision.confidence_score
            ) / (total + 1)

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get routing statistics"""
        cache_stats = await self.cache.get_stats()
        return {
            "total_routings": self.routing_stats["total_routings"],
            "avg_confidence": round(self.routing_stats["avg_confidence"], 2),
            "strategy": self.strategy.value,
            "cache": cache_stats,
            "agent_count": len(self.agent_metrics),
            "recent_routings": len(self.routing_history[-10:]),
        }

    async def reset_stats(self) -> None:
        """Reset routing statistics"""
        self.routing_history.clear()
        self.routing_stats = {
            "total_routings": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_confidence": 0.0,
        }
        await self.cache.clear()


# Global router instance
_global_router: AgentRouter | None = None


async def get_agent_router() -> AgentRouter:
    """Get or create global agent router"""
    global _global_router
    if _global_router is None:
        _global_router = AgentRouter()
        await _global_router.initialize()
    return _global_router


async def create_agent_router(
    strategy: RoutingStrategy = RoutingStrategy.WEIGHTED_SCORE,
    enable_caching: bool = True,
) -> AgentRouter:
    """Create a new agent router instance"""
    router = AgentRouter(strategy=strategy, enable_caching=enable_caching)
    await router.initialize()
    return router
