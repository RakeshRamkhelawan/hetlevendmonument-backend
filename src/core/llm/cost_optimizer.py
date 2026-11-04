# core/llm/cost_optimizer.py
"""
LLM Cost Optimization Service

Task 5.4.3: LLM Cost Optimization
- Multi-model routing based on task complexity
- Cost tracking and budgeting
- Target: 80% cost reduction, <$0.05 per query

Strategy:
1. Use cheaper models (gemini-flash, gpt-3.5) for simple tasks
2. Route complex tasks to premium models (gemini-pro, gpt-4)
3. Cache frequent queries to reduce API calls
4. Track per-tenant and per-query costs
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels for model routing"""

    SIMPLE = "simple"  # Simple queries, classification, short responses
    MODERATE = "moderate"  # Standard generation, summarization
    COMPLEX = "complex"  # Multi-step reasoning, code generation
    CRITICAL = "critical"  # High-stakes decisions, requires best model


class ModelTier(Enum):
    """Model pricing tiers"""

    ECONOMY = "economy"  # Cheapest models (~$0.001/1K tokens)
    STANDARD = "standard"  # Mid-range models (~$0.01/1K tokens)
    PREMIUM = "premium"  # Best models (~$0.03/1K tokens)


@dataclass
class ModelConfig:
    """Configuration for a specific model"""

    name: str
    provider: str
    tier: ModelTier
    input_cost_per_1k: float  # Cost per 1000 input tokens
    output_cost_per_1k: float  # Cost per 1000 output tokens
    max_tokens: int
    supports_function_calling: bool = True
    latency_ms_estimate: int = 500
    quality_score: float = 0.8  # 0-1 quality rating


# Model pricing database (prices in USD)
MODEL_CONFIGS: dict[str, ModelConfig] = {
    # Google Gemini Models
    "gemini-1.5-flash": ModelConfig(
        name="gemini-1.5-flash",
        provider="google",
        tier=ModelTier.ECONOMY,
        input_cost_per_1k=0.000075,  # $0.075 per 1M tokens
        output_cost_per_1k=0.0003,  # $0.30 per 1M tokens
        max_tokens=8192,
        latency_ms_estimate=300,
        quality_score=0.75,
    ),
    "gemini-1.5-pro": ModelConfig(
        name="gemini-1.5-pro",
        provider="google",
        tier=ModelTier.PREMIUM,
        input_cost_per_1k=0.00125,  # $1.25 per 1M tokens
        output_cost_per_1k=0.005,  # $5.00 per 1M tokens
        max_tokens=8192,
        latency_ms_estimate=800,
        quality_score=0.95,
    ),
    "gemini-2.0-flash": ModelConfig(
        name="gemini-2.0-flash",
        provider="google",
        tier=ModelTier.ECONOMY,
        input_cost_per_1k=0.0001,
        output_cost_per_1k=0.0004,
        max_tokens=8192,
        latency_ms_estimate=250,
        quality_score=0.80,
    ),
    # OpenAI Models (for future support)
    "gpt-3.5-turbo": ModelConfig(
        name="gpt-3.5-turbo",
        provider="openai",
        tier=ModelTier.ECONOMY,
        input_cost_per_1k=0.0005,
        output_cost_per_1k=0.0015,
        max_tokens=4096,
        latency_ms_estimate=400,
        quality_score=0.70,
    ),
    "gpt-4o-mini": ModelConfig(
        name="gpt-4o-mini",
        provider="openai",
        tier=ModelTier.STANDARD,
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
        max_tokens=16384,
        latency_ms_estimate=350,
        quality_score=0.85,
    ),
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        provider="openai",
        tier=ModelTier.PREMIUM,
        input_cost_per_1k=0.005,
        output_cost_per_1k=0.015,
        max_tokens=16384,
        latency_ms_estimate=700,
        quality_score=0.95,
    ),
    # Anthropic Models (for future support)
    "claude-3-haiku": ModelConfig(
        name="claude-3-haiku",
        provider="anthropic",
        tier=ModelTier.ECONOMY,
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
        max_tokens=4096,
        latency_ms_estimate=300,
        quality_score=0.80,
    ),
    "claude-3-sonnet": ModelConfig(
        name="claude-3-sonnet",
        provider="anthropic",
        tier=ModelTier.STANDARD,
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        max_tokens=4096,
        latency_ms_estimate=500,
        quality_score=0.90,
    ),
}


@dataclass
class CostRecord:
    """Record of a single LLM query cost"""

    timestamp: datetime
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tenant_id: str | None = None
    user_id: str | None = None
    query_type: str | None = None
    latency_ms: float = 0.0
    cached: bool = False


@dataclass
class CostBudget:
    """Budget configuration for cost control"""

    daily_limit_usd: float = 10.0
    monthly_limit_usd: float = 100.0
    per_query_limit_usd: float = 0.05
    alert_threshold_percent: float = 80.0


class QueryCache:
    """Simple in-memory cache for frequent queries"""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        self.cache: dict[str, tuple[str, datetime]] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def _hash_query(self, query: str, model: str) -> str:
        """Create hash key for cache lookup"""
        content = f"{model}:{query}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def get(self, query: str, model: str) -> str | None:
        """Get cached response if available"""
        key = self._hash_query(query, model)

        if key in self.cache:
            response, cached_at = self.cache[key]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()

            if age < self.ttl_seconds:
                self.hits += 1
                return response
            else:
                # Expired
                del self.cache[key]

        self.misses += 1
        return None

    def set(self, query: str, model: str, response: str) -> None:
        """Cache a query response"""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]

        key = self._hash_query(query, model)
        self.cache[key] = (response, datetime.now(timezone.utc))

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics"""
        total = self.hits + self.misses
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / max(total, 1),
            "ttl_seconds": self.ttl_seconds,
        }

    def clear(self) -> None:
        """Clear the cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


class LLMCostOptimizer:
    """
    Intelligent LLM cost optimization service

    Features:
    - Multi-model routing based on task complexity
    - Cost tracking per tenant/user
    - Budget enforcement
    - Query caching for cost reduction

    Usage:
        optimizer = LLMCostOptimizer()

        # Select optimal model for task
        model, complexity = optimizer.select_model(
            query="Translate this text",
            task_type="translation"
        )

        # Track costs after response
        optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            tenant_id="tenant-123"
        )

        # Check budget
        if optimizer.is_within_budget(tenant_id="tenant-123"):
            # Proceed with query
            pass
    """

    _instance: Optional["LLMCostOptimizer"] = None

    def __init__(self) -> None:
        self.model_configs = MODEL_CONFIGS.copy()
        self.cost_records: list[CostRecord] = []
        self.tenant_budgets: dict[str, CostBudget] = {}
        self.default_budget = CostBudget()
        self.cache = QueryCache()
        self._start_time = datetime.now(timezone.utc)

    @classmethod
    def get_instance(cls) -> "LLMCostOptimizer":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def classify_complexity(
        self,
        query: str,
        task_type: str | None = None,
        require_function_calling: bool = False,
        require_code: bool = False,
        require_reasoning: bool = False,
    ) -> TaskComplexity:
        """
        Classify query complexity for model selection

        Args:
            query: The input query text
            task_type: Optional task type hint (e.g., "translation", "summarization")
            require_function_calling: Whether function calling is needed
            require_code: Whether code generation is needed
            require_reasoning: Whether multi-step reasoning is needed

        Returns:
            TaskComplexity level
        """
        # Simple heuristics for complexity classification
        query_len = len(query)

        # Critical tasks
        if require_reasoning:
            return TaskComplexity.CRITICAL

        # Complex tasks
        if require_code or require_function_calling:
            return TaskComplexity.COMPLEX

        # Task type based classification
        simple_tasks = ["classification", "sentiment", "yes_no", "translation_short"]
        moderate_tasks = ["summarization", "translation", "extraction"]
        complex_tasks = ["generation", "analysis", "code", "reasoning"]

        if task_type:
            if task_type.lower() in simple_tasks:
                return TaskComplexity.SIMPLE
            elif task_type.lower() in moderate_tasks:
                return TaskComplexity.MODERATE
            elif task_type.lower() in complex_tasks:
                return TaskComplexity.COMPLEX

        # Length-based heuristics
        if query_len < 100:
            return TaskComplexity.SIMPLE
        elif query_len < 500:
            return TaskComplexity.MODERATE
        elif query_len < 2000:
            return TaskComplexity.COMPLEX
        else:
            return TaskComplexity.CRITICAL

    def select_model(
        self,
        query: str,
        task_type: str | None = None,
        available_providers: list[str] | None = None,
        require_function_calling: bool = False,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
        max_cost_per_query: float | None = None,
    ) -> tuple[str, TaskComplexity]:
        """
        Select optimal model for given query

        Args:
            query: The input query
            task_type: Optional task type hint
            available_providers: List[Any] of available provider names  # TODO(TYPE): replace Any with concrete type
            require_function_calling: Whether function calling is needed
            prefer_speed: Prefer faster models over cheaper
            prefer_quality: Prefer quality over cost
            max_cost_per_query: Maximum allowed cost per query

        Returns: Tuple[Any, ...] of (model_name, complexity)  # TODO(TYPE): replace Any with concrete type
        """
        complexity = self.classify_complexity(
            query=query,
            task_type=task_type,
            require_function_calling=require_function_calling,
        )

        # Get available models
        available_models = self._get_available_models(
            available_providers=available_providers,
            require_function_calling=require_function_calling,
        )

        if not available_models:
            # Fallback to default
            return "gemini-1.5-flash", complexity

        # Filter by cost limit
        if max_cost_per_query:
            available_models = [
                m
                for m in available_models
                if self._estimate_query_cost(m, query_length=len(query)) <= max_cost_per_query
            ]

        # Select based on complexity and preferences
        if prefer_quality:
            # Select highest quality model
            return self._select_by_quality(available_models, complexity), complexity
        elif prefer_speed:
            # Select fastest model
            return self._select_by_speed(available_models, complexity), complexity
        else:
            # Select by cost-efficiency (default)
            return self._select_by_cost_efficiency(available_models, complexity), complexity

    def _get_available_models(
        self,
        available_providers: list[str] | None = None,
        require_function_calling: bool = False,
    ) -> list[str]:
        """Get list of available models based on constraints"""
        models: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for name, config in self.model_configs.items():
            if available_providers and config.provider not in available_providers:
                continue
            if require_function_calling and not config.supports_function_calling:
                continue
            models.append(name)

        return models

    def _select_by_quality(self, models: list[str], complexity: TaskComplexity) -> str:
        """Select model by quality score"""
        if not models:
            return "gemini-1.5-flash"

        # For critical tasks, always use best quality
        if complexity == TaskComplexity.CRITICAL:
            return max(models, key=lambda m: self.model_configs[m].quality_score)

        # For others, balance quality with tier
        tier_priority = {
            TaskComplexity.SIMPLE: ModelTier.ECONOMY,
            TaskComplexity.MODERATE: ModelTier.STANDARD,
            TaskComplexity.COMPLEX: ModelTier.PREMIUM,
        }

        target_tier = tier_priority.get(complexity, ModelTier.STANDARD)
        tier_models = [m for m in models if self.model_configs[m].tier == target_tier]

        if tier_models:
            return max(tier_models, key=lambda m: self.model_configs[m].quality_score)

        return max(models, key=lambda m: self.model_configs[m].quality_score)

    def _select_by_speed(self, models: list[str], complexity: TaskComplexity) -> str:
        """Select model by latency"""
        if not models:
            return "gemini-1.5-flash"

        # Select fastest that meets minimum quality for complexity
        min_quality = {
            TaskComplexity.SIMPLE: 0.5,
            TaskComplexity.MODERATE: 0.7,
            TaskComplexity.COMPLEX: 0.8,
            TaskComplexity.CRITICAL: 0.9,
        }

        quality_threshold = min_quality.get(complexity, 0.7)
        qualified = [m for m in models if self.model_configs[m].quality_score >= quality_threshold]

        if qualified:
            return min(qualified, key=lambda m: self.model_configs[m].latency_ms_estimate)

        return min(models, key=lambda m: self.model_configs[m].latency_ms_estimate)

    def _select_by_cost_efficiency(self, models: list[str], complexity: TaskComplexity) -> str:
        """Select model by cost efficiency (cost per quality point)"""
        if not models:
            return "gemini-1.5-flash"

        # Map complexity to target tier
        tier_map = {
            TaskComplexity.SIMPLE: ModelTier.ECONOMY,
            TaskComplexity.MODERATE: ModelTier.ECONOMY,  # Try economy first
            TaskComplexity.COMPLEX: ModelTier.STANDARD,
            TaskComplexity.CRITICAL: ModelTier.PREMIUM,
        }

        target_tier = tier_map.get(complexity, ModelTier.ECONOMY)

        # Get models in target tier
        tier_models = [m for m in models if self.model_configs[m].tier == target_tier]

        if tier_models:
            # Select cheapest in tier
            return min(tier_models, key=lambda m: self._get_avg_cost(m))

        # Fall back to cheapest overall
        return min(models, key=lambda m: self._get_avg_cost(m))

    def _get_avg_cost(self, model: str) -> float:
        """Get average cost per 1K tokens for model"""
        config = self.model_configs.get(model)
        if not config:
            return float("inf")
        return (config.input_cost_per_1k + config.output_cost_per_1k) / 2

    def _estimate_query_cost(self, model: str, query_length: int) -> float:
        """Estimate cost for a query"""
        config = self.model_configs.get(model)
        if not config:
            return 0.0

        # Rough estimation: 4 chars = 1 token
        input_tokens = query_length / 4
        output_tokens = input_tokens * 2  # Assume 2x output

        input_cost = (input_tokens / 1000) * config.input_cost_per_1k
        output_cost = (output_tokens / 1000) * config.output_cost_per_1k

        return input_cost + output_cost

    def record_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tenant_id: str | None = None,
        user_id: str | None = None,
        query_type: str | None = None,
        latency_ms: float = 0.0,
        cached: bool = False,
    ) -> CostRecord:
        """
        Record cost of an LLM query

        Args:
            model: Model name used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            tenant_id: Optional tenant ID for cost tracking
            user_id: Optional user ID
            query_type: Optional query type for analysis
            latency_ms: Query latency in milliseconds
            cached: Whether result was from cache

        Returns:
            CostRecord with calculated cost
        """
        config = self.model_configs.get(model)

        if cached:
            cost = 0.0
        elif config:
            input_cost = (input_tokens / 1000) * config.input_cost_per_1k
            output_cost = (output_tokens / 1000) * config.output_cost_per_1k
            cost = input_cost + output_cost
        else:
            # Unknown model, estimate conservatively
            cost = (input_tokens + output_tokens) / 1000 * 0.01

        record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tenant_id=tenant_id,
            user_id=user_id,
            query_type=query_type,
            latency_ms=latency_ms,
            cached=cached,
        )

        self.cost_records.append(record)

        # Keep only last 10000 records
        if len(self.cost_records) > 10000:
            self.cost_records = self.cost_records[-10000:]

        return record

    def get_tenant_costs(
        self,
        tenant_id: str,
        period: str = "daily",
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cost summary for a tenant"""
        now = datetime.now(timezone.utc)

        if period == "daily":
            cutoff = now - timedelta(days=1)
        elif period == "weekly":
            cutoff = now - timedelta(weeks=1)
        elif period == "monthly":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = now - timedelta(days=1)

        records = [
            r for r in self.cost_records if r.tenant_id == tenant_id and r.timestamp >= cutoff
        ]

        total_cost = sum(r.cost_usd for r in records)
        total_queries = len(records)
        cached_queries = sum(1 for r in records if r.cached)

        # Cost by model
        model_costs: dict[str, float] = {}
        for r in records:
            model_costs[r.model] = model_costs.get(r.model, 0) + r.cost_usd

        return {
            "tenant_id": tenant_id,
            "period": period,
            "total_cost_usd": round(total_cost, 4),
            "total_queries": total_queries,
            "cached_queries": cached_queries,
            "cache_savings_percent": (cached_queries / max(total_queries, 1)) * 100,
            "avg_cost_per_query": round(total_cost / max(total_queries, 1), 6),
            "cost_by_model": model_costs,
        }

    def is_within_budget(
        self,
        tenant_id: str | None = None,
        estimated_cost: float = 0.0,
    ) -> bool:
        """Check if query is within budget"""
        budget = (
            self.tenant_budgets.get(tenant_id, self.default_budget)
            if tenant_id is not None
            else self.default_budget
        )

        # Check per-query limit
        if estimated_cost > budget.per_query_limit_usd:
            return False

        if not tenant_id:
            return True

        # Check daily limit
        daily_costs = self.get_tenant_costs(tenant_id, "daily")
        if daily_costs["total_cost_usd"] + estimated_cost > budget.daily_limit_usd:
            return False

        # Check monthly limit
        monthly_costs = self.get_tenant_costs(tenant_id, "monthly")
        if monthly_costs["total_cost_usd"] + estimated_cost > budget.monthly_limit_usd:
            return False

        return True

    def set_tenant_budget(self, tenant_id: str, budget: CostBudget) -> None:
        """Set budget for a specific tenant"""
        self.tenant_budgets[tenant_id] = budget

    def get_optimization_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cost optimization report"""
        if not self.cost_records:
            return {
                "status": "no_data",
                "total_cost_usd": 0,
                "potential_savings_usd": 0,
            }

        total_cost = sum(r.cost_usd for r in self.cost_records)
        cached_count = sum(1 for r in self.cost_records if r.cached)

        # Calculate potential savings if all queries used economy models
        economy_cost = sum(
            self._estimate_economy_cost(r) for r in self.cost_records if not r.cached
        )

        # Calculate cache savings
        cache_stats = self.cache.get_stats()

        return {
            "total_queries": len(self.cost_records),
            "total_cost_usd": round(total_cost, 4),
            "avg_cost_per_query": round(total_cost / len(self.cost_records), 6),
            "cached_queries": cached_count,
            "cache_hit_rate": cache_stats["hit_rate"],
            "potential_economy_cost_usd": round(economy_cost, 4),
            "potential_savings_usd": round(total_cost - economy_cost, 4),
            "savings_percent": round((1 - economy_cost / max(total_cost, 0.001)) * 100, 1),
            "recommendations": self._get_recommendations(),
        }

    def _estimate_economy_cost(self, record: CostRecord) -> float:
        """Estimate cost if economy model was used"""
        # Use gemini-1.5-flash as reference economy model
        config = self.model_configs.get("gemini-1.5-flash")
        if not config:
            return record.cost_usd

        input_cost = (record.input_tokens / 1000) * config.input_cost_per_1k
        output_cost = (record.output_tokens / 1000) * config.output_cost_per_1k
        return input_cost + output_cost

    def _get_recommendations(self) -> list[str]:
        """Get cost optimization recommendations"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        cache_stats = self.cache.get_stats()
        if cache_stats["hit_rate"] < 0.1:
            recommendations.append("Low cache hit rate - consider caching more queries")

        # Analyze model usage
        model_usage: dict[str, int] = {}
        for r in self.cost_records:
            model_usage[r.model] = model_usage.get(r.model, 0) + 1

        premium_usage = sum(
            count
            for model, count in model_usage.items()
            if model in self.model_configs and self.model_configs[model].tier == ModelTier.PREMIUM
        )
        total_usage = len(self.cost_records)

        if premium_usage / max(total_usage, 1) > 0.5:
            recommendations.append(
                "High premium model usage - review if tasks require premium quality"
            )

        if not recommendations:
            recommendations.append("Cost optimization is performing well")

        return recommendations


def get_cost_optimizer() -> LLMCostOptimizer:
    """Get global cost optimizer instance"""
    return LLMCostOptimizer.get_instance()
