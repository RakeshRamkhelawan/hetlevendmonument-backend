"""
Intelligent LLM Router - Production-Ready Dynamic Provider Selection
Handles intelligent routing between multiple LLM providers based on performance, cost, and availability
ASCII-only compliance enforced - no Unicode characters
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from src.core.middleware.tenant_context import get_tenant_id

# Import caching for performance optimization
get_cache_manager: Any = None

try:
    from src.core.caching.cache_layer import get_cache_manager

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """LLM routing strategies for production deployment"""

    ROUND_ROBIN = "round_robin"
    PERFORMANCE_BASED = "performance_based"
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    AVAILABILITY_BASED = "availability_based"
    SMART_BALANCE = "smart_balance"
    FAILOVER_CASCADE = "failover_cascade"


class ProviderHealth(Enum):
    """Provider health status levels"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ProviderConfiguration:
    """Provider configuration and limits"""

    provider_id: str
    endpoint_url: str
    api_key_env: str
    max_concurrent_requests: int = 10
    request_timeout: float = 30.0
    cost_per_token: float = 0.001
    max_tokens_per_request: int = 4096
    rate_limit_per_minute: int = 60
    retry_attempts: int = 3
    retry_delay: float = 1.0
    priority: int = 50
    enabled: bool = True


@dataclass
class ProviderMetrics:
    """Production metrics for LLM provider performance tracking"""

    provider_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    avg_response_time: float = 0.0
    min_response_time: float = float("inf")
    max_response_time: float = 0.0
    total_tokens_processed: int = 0
    total_cost: float = 0.0
    current_load: int = 0
    last_request_time: datetime | None = None
    last_success_time: datetime | None = None
    last_failure_time: datetime | None = None
    consecutive_failures: int = 0
    health_status: ProviderHealth = ProviderHealth.UNKNOWN

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100.0

    @property
    def availability_score(self) -> float:
        """Calculate availability score based on recent performance"""
        if self.consecutive_failures > 5:
            return 0.0
        elif self.consecutive_failures > 2:
            return 0.5
        elif self.success_rate > 95.0:
            return 1.0
        elif self.success_rate > 85.0:
            return 0.8
        elif self.success_rate > 70.0:
            return 0.6
        else:
            return 0.3

    @property
    def cost_efficiency(self) -> float:
        """Calculate cost efficiency score"""
        if self.total_tokens_processed == 0:
            return 1.0
        cost_per_token = self.total_cost / self.total_tokens_processed
        return max(0.1, 1.0 - (cost_per_token / 0.01))  # Normalize against 0.01 max cost

    @property
    def latency_score(self) -> float:
        """Calculate latency performance score"""
        if self.avg_response_time == 0:
            return 1.0
        return max(0.1, 1.0 - (self.avg_response_time / 10.0))  # Normalize against 10s max

    @property
    def composite_score(self) -> float:
        """Calculate overall provider performance score"""
        weights = {"availability": 0.4, "latency": 0.3, "cost": 0.2, "load": 0.1}

        load_score = 1.0 - (self.current_load / 100.0) if self.current_load <= 100 else 0.0

        return (
            weights["availability"] * self.availability_score
            + weights["latency"] * self.latency_score
            + weights["cost"] * self.cost_efficiency
            + weights["load"] * load_score
        )


class IntelligentRouter:
    """Production-Ready Intelligent LLM Router with Advanced Load Balancing"""

    def __init__(self, strategy: RoutingStrategy = RoutingStrategy.SMART_BALANCE) -> None:
        self.strategy = strategy
        self.providers: dict[str, ProviderConfiguration] = {}
        self.metrics: dict[str, ProviderMetrics] = {}
        self.routing_history: list[dict[str, Any]] = (  # TODO(TYPE): replace Any with concrete type
            []
        )
        self.circuit_breaker_threshold = 5  # Consecutive failures before circuit break
        self.health_check_interval = timedelta(minutes=2)
        self.last_health_check = datetime.now(timezone.utc)
        self.round_robin_index = 0
        self.cache_manager = None

        if CACHE_AVAILABLE:
            try:
                cache_mgr = get_cache_manager()
                if cache_mgr is not None:
                    self.cache_manager = cache_mgr
            except Exception as e:
                logger.warning(f"Cache manager unavailable: {e}")

        logger.info(f"Intelligent Router initialized with strategy: {strategy.value}")

    def register_provider(self, config: ProviderConfiguration) -> bool:
        """Register a new LLM provider with production configuration"""
        try:
            if not config.provider_id or not config.endpoint_url:
                logger.error("Provider ID and endpoint URL are required")
                return False

            self.providers[config.provider_id] = config
            self.metrics[config.provider_id] = ProviderMetrics(provider_id=config.provider_id)

            logger.info(f"Registered provider: {config.provider_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to register provider {config.provider_id}: {e}")
            return False

    def deregister_provider(self, provider_id: str) -> bool:
        """Remove a provider from routing"""
        try:
            if provider_id in self.providers:
                del self.providers[provider_id]
                if provider_id in self.metrics:
                    del self.metrics[provider_id]
                logger.info(f"Deregistered provider: {provider_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to deregister provider {provider_id}: {e}")
            return False

    async def select_provider(
        self,
        request_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        required_capabilities: list[str] | None = None,
    ) -> str | None:
        """
        Select optimal provider based on routing strategy and current conditions

        Args:
            request_context: Context information for the request
            required_capabilities: Specific capabilities required

        Returns:
            Selected provider ID or None if no suitable provider available
        """
        try:
            # Get available providers
            available_providers = await self._get_available_providers(required_capabilities)

            if not available_providers:
                logger.warning("No available providers for request")
                return None

            # Perform health check if needed
            if datetime.now(timezone.utc) - self.last_health_check > self.health_check_interval:
                await self._update_health_status()

            # Apply routing strategy
            selected = await self._apply_routing_strategy(available_providers, request_context)

            if selected:
                # Update provider load
                self.metrics[selected].current_load += 1

                # Cache recent selection if cache available -- prefixed with tenant_id (SP-SEC-001 TI-004)
                if self.cache_manager and get_cache_manager is not None:
                    _tid = get_tenant_id() or 0
                    # NOTE: t0 = system namespace; never a real tenant (tenant_id > 0 per ADR-005)
                    cache_key = f"t{_tid}:router_selection_{hashlib.md5(str(request_context).encode(), usedforsecurity=False).hexdigest()}"
                    await self.cache_manager.set(cache_key, selected, ttl=60)

            return selected

        except Exception as e:
            logger.error(f"Error in provider selection: {e}")
            return None

    async def _get_available_providers(
        self, required_capabilities: list[str] | None = None
    ) -> list[str]:
        """Get list of currently available providers"""
        available: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for provider_id, config in self.providers.items():
            if not config.enabled:
                continue

            metrics = self.metrics[provider_id]

            # Check circuit breaker
            if metrics.consecutive_failures >= self.circuit_breaker_threshold:
                continue

            # Check load capacity
            if metrics.current_load >= config.max_concurrent_requests:
                continue

            # Check health status
            if metrics.health_status == ProviderHealth.OFFLINE:
                continue

            available.append(provider_id)

        return available

    async def _apply_routing_strategy(
        self,
        available_providers: list[str],
        request_context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Apply the configured routing strategy"""
        if not available_providers:
            return None

        if self.strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin_selection(available_providers)
        elif self.strategy == RoutingStrategy.PERFORMANCE_BASED:
            return self._performance_based_selection(available_providers)
        elif self.strategy == RoutingStrategy.COST_OPTIMIZED:
            return self._cost_optimized_selection(available_providers)
        elif self.strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            return self._latency_optimized_selection(available_providers)
        elif self.strategy == RoutingStrategy.AVAILABILITY_BASED:
            return self._availability_based_selection(available_providers)
        elif self.strategy == RoutingStrategy.FAILOVER_CASCADE:
            return self._failover_cascade_selection(available_providers)
        else:  # SMART_BALANCE
            return self._smart_balance_selection(available_providers, request_context)

    def _round_robin_selection(self, providers: list[str]) -> str:
        """Round-robin provider selection"""
        selected = providers[self.round_robin_index % len(providers)]
        self.round_robin_index += 1
        return selected

    def _performance_based_selection(self, providers: list[str]) -> str:
        """Select provider with highest composite performance score"""
        return max(providers, key=lambda p: self.metrics[p].composite_score)

    def _cost_optimized_selection(self, providers: list[str]) -> str:
        """Select provider with lowest cost per token"""
        return min(providers, key=lambda p: self.providers[p].cost_per_token)

    def _latency_optimized_selection(self, providers: list[str]) -> str:
        """Select provider with lowest average response time"""
        return min(
            providers,
            key=lambda p: (
                self.metrics[p].avg_response_time if self.metrics[p].avg_response_time > 0 else 1.0
            ),
        )

    def _availability_based_selection(self, providers: list[str]) -> str:
        """Select provider with highest availability score"""
        return max(providers, key=lambda p: self.metrics[p].availability_score)

    def _failover_cascade_selection(self, providers: list[str]) -> str:
        """Select based on priority cascade failover"""
        return max(providers, key=lambda p: self.providers[p].priority)

    def _smart_balance_selection(
        self,
        providers: list[str],
        request_context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Intelligent balanced selection considering multiple factors"""
        # Dynamic weight adjustment based on request context
        base_weights = {
            "performance": 0.3,
            "latency": 0.25,
            "cost": 0.2,
            "availability": 0.25,
        }

        # Adjust weights based on context
        if request_context and "priority" in request_context:
            priority = request_context["priority"]
            if priority == "speed":
                base_weights["latency"] = 0.5
                base_weights["performance"] = 0.3
                base_weights["cost"] = 0.1
                base_weights["availability"] = 0.1
            elif priority == "cost":
                base_weights["cost"] = 0.5
                base_weights["performance"] = 0.2
                base_weights["latency"] = 0.2
                base_weights["availability"] = 0.1
            elif priority == "reliability":
                base_weights["availability"] = 0.4
                base_weights["performance"] = 0.3
                base_weights["latency"] = 0.2
                base_weights["cost"] = 0.1

        # Calculate weighted scores
        scored_providers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for provider_id in providers:
            metrics = self.metrics[provider_id]

            score = (
                base_weights["performance"] * metrics.composite_score
                + base_weights["latency"] * metrics.latency_score
                + base_weights["cost"] * metrics.cost_efficiency
                + base_weights["availability"] * metrics.availability_score
            )

            scored_providers.append((provider_id, score))

        # Return provider with highest weighted score
        best_provider: str = max(scored_providers, key=lambda x: x[1])[0]
        return best_provider

    async def record_request_start(self, provider_id: str, request_size: int = 0) -> bool:
        """Record the start of a request to a provider"""
        try:
            if provider_id not in self.metrics:
                logger.warning(f"Unknown provider {provider_id}")
                return False

            metrics = self.metrics[provider_id]
            metrics.last_request_time = datetime.now(timezone.utc)

            return True

        except Exception as e:
            logger.error(f"Error recording request start for {provider_id}: {e}")
            return False

    async def record_request_completion(
        self,
        provider_id: str,
        success: bool,
        response_time: float,
        tokens_used: int = 0,
        cost: float = 0.0,
        error_details: str | None = None,
    ) -> bool:
        """Record the completion of a request"""
        try:
            if provider_id not in self.metrics:
                logger.warning(f"Unknown provider {provider_id}")
                return False

            metrics = self.metrics[provider_id]
            config = self.providers[provider_id]

            # Update basic counters
            metrics.total_requests += 1
            metrics.current_load = max(0, metrics.current_load - 1)

            if success:
                metrics.successful_requests += 1
                metrics.consecutive_failures = 0
                metrics.last_success_time = datetime.now(timezone.utc)

                # Update cost tracking
                if cost > 0:
                    metrics.total_cost += cost
                elif tokens_used > 0:
                    metrics.total_cost += tokens_used * config.cost_per_token

                metrics.total_tokens_processed += tokens_used

                # Update timing metrics
                self._update_timing_metrics(metrics, response_time)

            else:
                metrics.failed_requests += 1
                metrics.consecutive_failures += 1
                metrics.last_failure_time = datetime.now(timezone.utc)

                if error_details:
                    logger.warning(f"Request failed for {provider_id}: {error_details}")

            # Update health status
            self._update_provider_health(provider_id)

            # Record routing decision
            self.routing_history.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": provider_id,
                    "success": success,
                    "response_time": response_time,
                    "strategy": self.strategy.value,
                }
            )

            # Maintain history size
            if len(self.routing_history) > 1000:
                self.routing_history = self.routing_history[-500:]

            return True

        except Exception as e:
            logger.error(f"Error recording request completion for {provider_id}: {e}")
            return False

    def _update_timing_metrics(self, metrics: ProviderMetrics, response_time: float) -> None:
        """Update response time metrics"""
        # Update min/max
        metrics.min_response_time = min(metrics.min_response_time, response_time)
        metrics.max_response_time = max(metrics.max_response_time, response_time)

        # Update rolling average using exponential moving average
        if metrics.avg_response_time == 0:
            metrics.avg_response_time = response_time
        else:
            alpha = 0.1  # Smoothing factor
            metrics.avg_response_time = (
                alpha * response_time + (1 - alpha) * metrics.avg_response_time
            )

    def _update_provider_health(self, provider_id: str) -> None:
        """Update provider health status based on recent performance"""
        metrics = self.metrics[provider_id]

        if metrics.consecutive_failures >= self.circuit_breaker_threshold:
            metrics.health_status = ProviderHealth.OFFLINE
        elif metrics.consecutive_failures >= 3:
            metrics.health_status = ProviderHealth.CRITICAL
        elif metrics.failure_rate > 20.0:
            metrics.health_status = ProviderHealth.DEGRADED
        elif metrics.success_rate > 95.0 and metrics.consecutive_failures == 0:
            metrics.health_status = ProviderHealth.HEALTHY
        else:
            metrics.health_status = ProviderHealth.UNKNOWN

    async def _update_health_status(self) -> None:
        """Periodic health status update for all providers"""
        self.last_health_check = datetime.now(timezone.utc)

        for provider_id in self.providers.keys():
            # Reset circuit breaker if enough time has passed since last failure
            metrics = self.metrics[provider_id]
            if metrics.last_failure_time and datetime.now(timezone.utc) - metrics.last_failure_time > timedelta(minutes=5):
                if metrics.consecutive_failures >= self.circuit_breaker_threshold:
                    metrics.consecutive_failures = max(0, metrics.consecutive_failures - 1)
                    logger.info(f"Circuit breaker recovery attempt for {provider_id}")

    def get_provider_metrics(
        self, provider_id: str
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive metrics for a specific provider"""
        if provider_id not in self.metrics:
            return None

        metrics = self.metrics[provider_id]
        config = self.providers[provider_id]

        return {
            "provider_id": provider_id,
            "health_status": metrics.health_status.value,
            "success_rate": round(metrics.success_rate, 2),
            "failure_rate": round(metrics.failure_rate, 2),
            "avg_response_time": round(metrics.avg_response_time, 3),
            "min_response_time": round(metrics.min_response_time, 3),
            "max_response_time": round(metrics.max_response_time, 3),
            "total_requests": metrics.total_requests,
            "current_load": metrics.current_load,
            "max_concurrent": config.max_concurrent_requests,
            "total_cost": round(metrics.total_cost, 4),
            "tokens_processed": metrics.total_tokens_processed,
            "availability_score": round(metrics.availability_score, 3),
            "composite_score": round(metrics.composite_score, 3),
            "consecutive_failures": metrics.consecutive_failures,
            "cost_per_token": config.cost_per_token,
            "enabled": config.enabled,
        }

    def get_routing_statistics(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive routing statistics"""
        total_requests = sum(m.total_requests for m in self.metrics.values())
        total_successes = sum(m.successful_requests for m in self.metrics.values())

        provider_distribution: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for provider_id, metrics in self.metrics.items():
            provider_distribution[provider_id] = {
                "requests": metrics.total_requests,
                "percentage": (
                    round((metrics.total_requests / total_requests * 100), 2)
                    if total_requests > 0
                    else 0
                ),
            }

        return {
            "routing_strategy": self.strategy.value,
            "total_providers": len(self.providers),
            "active_providers": len([p for p in self.providers.values() if p.enabled]),
            "total_requests": total_requests,
            "total_successes": total_successes,
            "overall_success_rate": (
                round((total_successes / total_requests * 100), 2) if total_requests > 0 else 0
            ),
            "provider_distribution": provider_distribution,
            "recent_routing_decisions": len(self.routing_history),
            "health_summary": {
                status.value: len([m for m in self.metrics.values() if m.health_status == status])
                for status in ProviderHealth
            },
        }

    def set_routing_strategy(self, strategy: RoutingStrategy) -> None:
        """Change the routing strategy"""
        self.strategy = strategy
        logger.info(f"Routing strategy changed to: {strategy.value}")

    def enable_provider(self, provider_id: str) -> bool:
        """Enable a provider for routing"""
        if provider_id in self.providers:
            self.providers[provider_id].enabled = True
            logger.info(f"Enabled provider: {provider_id}")
            return True
        return False

    def disable_provider(self, provider_id: str) -> bool:
        """Disable a provider from routing"""
        if provider_id in self.providers:
            self.providers[provider_id].enabled = False
            logger.info(f"Disabled provider: {provider_id}")
            return True
        return False


# Global router instance management
_global_router: IntelligentRouter | None = None


def get_router() -> IntelligentRouter:
    """Get the global router instance"""
    global _global_router
    if _global_router is None:
        _global_router = IntelligentRouter()
    return _global_router


def initialize_router(
    strategy: RoutingStrategy = RoutingStrategy.SMART_BALANCE,
) -> IntelligentRouter:
    """Initialize the global router with a specific strategy"""
    global _global_router
    _global_router = IntelligentRouter(strategy)
    return _global_router


def reset_router() -> None:
    """Reset the global router instance"""
    global _global_router
    _global_router = None


# Production configuration factory functions
def create_openai_config(api_key_env: str = "OPENAI_API_KEY") -> ProviderConfiguration:
    """Create OpenAI provider configuration"""
    return ProviderConfiguration(
        provider_id="openai",
        endpoint_url="https://api.openai.com/v1/chat/completions",
        api_key_env=api_key_env,
        max_concurrent_requests=5,
        cost_per_token=0.002,
        rate_limit_per_minute=60,
        priority=80,
    )


def create_anthropic_config(
    api_key_env: str = "ANTHROPIC_API_KEY",
) -> ProviderConfiguration:
    """Create Anthropic provider configuration"""
    return ProviderConfiguration(
        provider_id="anthropic",
        endpoint_url="https://api.anthropic.com/v1/messages",
        api_key_env=api_key_env,
        max_concurrent_requests=3,
        cost_per_token=0.003,
        rate_limit_per_minute=50,
        priority=85,
    )


def create_google_config(api_key_env: str = "GOOGLE_API_KEY") -> ProviderConfiguration:
    """Create Google Gemini provider configuration"""
    return ProviderConfiguration(
        provider_id="google",
        endpoint_url="https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent",
        api_key_env=api_key_env,
        max_concurrent_requests=8,
        cost_per_token=0.001,
        rate_limit_per_minute=100,
        priority=70,
    )
