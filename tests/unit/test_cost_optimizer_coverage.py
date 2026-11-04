"""
Comprehensive tests for src/core/llm/cost_optimizer.py
Coverage target: 100% of LLM cost optimization
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.llm.cost_optimizer import (
    MODEL_CONFIGS,
    CostBudget,
    CostRecord,
    LLMCostOptimizer,
    ModelConfig,
    ModelTier,
    QueryCache,
    TaskComplexity,
    get_cost_optimizer,
)


class TestTaskComplexityEnum:
    """Test TaskComplexity enum"""

    def test_all_complexity_levels(self):
        """Test all complexity levels are defined"""
        assert TaskComplexity.SIMPLE.value == "simple"
        assert TaskComplexity.MODERATE.value == "moderate"
        assert TaskComplexity.COMPLEX.value == "complex"
        assert TaskComplexity.CRITICAL.value == "critical"


class TestModelTierEnum:
    """Test ModelTier enum"""

    def test_all_tiers(self):
        """Test all model tiers are defined"""
        assert ModelTier.ECONOMY.value == "economy"
        assert ModelTier.STANDARD.value == "standard"
        assert ModelTier.PREMIUM.value == "premium"


class TestModelConfig:
    """Test ModelConfig dataclass"""

    def test_model_config_creation(self):
        """Test creating model configuration"""
        config = ModelConfig(
            name="test-model",
            provider="test-provider",
            tier=ModelTier.ECONOMY,
            input_cost_per_1k=0.001,
            output_cost_per_1k=0.002,
            max_tokens=4096,
            supports_function_calling=True,
            latency_ms_estimate=300,
            quality_score=0.8,
        )

        assert config.name == "test-model"
        assert config.provider == "test-provider"
        assert config.tier == ModelTier.ECONOMY
        assert config.input_cost_per_1k == 0.001
        assert config.output_cost_per_1k == 0.002
        assert config.max_tokens == 4096


class TestModelConfigs:
    """Test MODEL_CONFIGS database"""

    def test_gemini_flash_config(self):
        """Test Gemini Flash configuration"""
        config = MODEL_CONFIGS["gemini-1.5-flash"]

        assert config.provider == "google"
        assert config.tier == ModelTier.ECONOMY
        assert config.input_cost_per_1k < config.output_cost_per_1k

    def test_gemini_pro_config(self):
        """Test Gemini Pro configuration"""
        config = MODEL_CONFIGS["gemini-1.5-pro"]

        assert config.provider == "google"
        assert config.tier == ModelTier.PREMIUM
        assert config.quality_score > 0.9

    def test_all_models_have_required_fields(self):
        """Test all models have required fields"""
        for model_name, config in MODEL_CONFIGS.items():
            assert config.name == model_name
            assert config.provider
            assert config.tier
            assert config.input_cost_per_1k >= 0
            assert config.output_cost_per_1k >= 0
            assert config.max_tokens > 0


class TestCostRecord:
    """Test CostRecord dataclass"""

    def test_cost_record_creation(self):
        """Test creating cost record"""
        now = datetime.now(timezone.utc)
        record = CostRecord(
            timestamp=now,
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.05,
            tenant_id="tenant-123",
            user_id="user-456",
            query_type="chat",
            latency_ms=300.5,
            cached=False,
        )

        assert record.timestamp == now
        assert record.model == "gemini-1.5-flash"
        assert record.input_tokens == 100
        assert record.output_tokens == 200
        assert record.cost_usd == 0.05


class TestCostBudget:
    """Test CostBudget dataclass"""

    def test_budget_defaults(self):
        """Test budget default values"""
        budget = CostBudget()

        assert budget.daily_limit_usd == 10.0
        assert budget.monthly_limit_usd == 100.0
        assert budget.per_query_limit_usd == 0.05
        assert budget.alert_threshold_percent == 80.0

    def test_custom_budget(self):
        """Test creating custom budget"""
        budget = CostBudget(
            daily_limit_usd=50.0,
            monthly_limit_usd=500.0,
            per_query_limit_usd=0.10,
            alert_threshold_percent=90.0,
        )

        assert budget.daily_limit_usd == 50.0
        assert budget.monthly_limit_usd == 500.0


class TestQueryCache:
    """Test QueryCache class"""

    def test_cache_initialization(self):
        """Test cache initialization"""
        cache = QueryCache(max_size=100, ttl_seconds=3600)

        assert cache.max_size == 100
        assert cache.ttl_seconds == 3600
        assert cache.hits == 0
        assert cache.misses == 0

    def test_cache_miss(self):
        """Test cache miss"""
        cache = QueryCache()

        result = cache.get("query1", "model1")

        assert result is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_cache_set_and_hit(self):
        """Test cache set and hit"""
        cache = QueryCache()

        cache.set("query1", "model1", "response1")
        result = cache.get("query1", "model1")

        assert result == "response1"
        assert cache.hits == 1

    def test_cache_expiry(self):
        """Test cache expiry"""
        cache = QueryCache(ttl_seconds=0)  # Immediate expiry

        cache.set("query1", "model1", "response1")
        # Wait a moment for expiry
        import time

        time.sleep(0.01)
        result = cache.get("query1", "model1")

        assert result is None
        assert cache.misses == 1

    def test_cache_max_size(self):
        """Test cache max size limit"""
        cache = QueryCache(max_size=2)

        cache.set("query1", "model1", "response1")
        cache.set("query2", "model1", "response2")
        cache.set("query3", "model1", "response3")  # Should evict oldest

        assert len(cache.cache) == 2

    def test_cache_stats(self):
        """Test cache statistics"""
        cache = QueryCache()

        cache.set("query1", "model1", "response1")
        cache.get("query1", "model1")  # Hit
        cache.get("query2", "model1")  # Miss

        stats = cache.get_stats()

        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_clear(self):
        """Test cache clear"""
        cache = QueryCache()

        cache.set("query1", "model1", "response1")
        cache.get("query1", "model1")

        cache.clear()

        assert len(cache.cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0


class TestLLMCostOptimizerInitialization:
    """Test LLMCostOptimizer initialization"""

    def test_initialization(self):
        """Test optimizer initialization"""
        optimizer = LLMCostOptimizer()

        assert len(optimizer.model_configs) > 0
        assert optimizer.cost_records == []
        assert optimizer.tenant_budgets == {}
        assert isinstance(optimizer.default_budget, CostBudget)
        assert isinstance(optimizer.cache, QueryCache)

    def test_singleton_pattern(self):
        """Test get_instance returns singleton"""
        optimizer1 = LLMCostOptimizer.get_instance()
        optimizer2 = LLMCostOptimizer.get_instance()

        assert optimizer1 is optimizer2


class TestComplexityClassification:
    """Test classify_complexity method"""

    def test_classify_simple_by_length(self):
        """Test simple classification by length"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Short query")

        assert complexity == TaskComplexity.SIMPLE

    def test_classify_moderate_by_length(self):
        """Test moderate classification by length"""
        optimizer = LLMCostOptimizer()
        query = "This is a moderately long query. " * 5

        complexity = optimizer.classify_complexity(query)

        assert complexity == TaskComplexity.MODERATE

    def test_classify_complex_by_length(self):
        """Test complex classification by length"""
        optimizer = LLMCostOptimizer()
        query = "This is a very long query. " * 50

        complexity = optimizer.classify_complexity(query)

        assert complexity == TaskComplexity.COMPLEX

    def test_classify_critical_by_reasoning(self):
        """Test critical classification when reasoning required"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Test query", require_reasoning=True)

        assert complexity == TaskComplexity.CRITICAL

    def test_classify_complex_by_code_requirement(self):
        """Test complex classification for code generation"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Test query", require_code=True)

        assert complexity == TaskComplexity.COMPLEX

    def test_classify_by_task_type_simple(self):
        """Test classification by simple task type"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Long query" * 100, task_type="classification")

        assert complexity == TaskComplexity.SIMPLE

    def test_classify_by_task_type_moderate(self):
        """Test classification by moderate task type"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Query", task_type="summarization")

        assert complexity == TaskComplexity.MODERATE

    def test_classify_by_task_type_complex(self):
        """Test classification by complex task type"""
        optimizer = LLMCostOptimizer()

        complexity = optimizer.classify_complexity("Query", task_type="code")

        assert complexity == TaskComplexity.COMPLEX


class TestModelSelection:
    """Test select_model method"""

    def test_select_for_simple_task(self):
        """Test model selection for simple task"""
        optimizer = LLMCostOptimizer()

        model, complexity = optimizer.select_model("Short query")

        assert complexity == TaskComplexity.SIMPLE
        assert model in optimizer.model_configs

    def test_select_with_provider_filter(self):
        """Test model selection with provider filter"""
        optimizer = LLMCostOptimizer()

        model, _ = optimizer.select_model("Test query", available_providers=["google"])

        assert optimizer.model_configs[model].provider == "google"

    def test_select_with_function_calling_requirement(self):
        """Test selection with function calling requirement"""
        optimizer = LLMCostOptimizer()

        model, _ = optimizer.select_model("Test query", require_function_calling=True)

        assert optimizer.model_configs[model].supports_function_calling

    def test_select_prefer_speed(self):
        """Test selection preferring speed"""
        optimizer = LLMCostOptimizer()

        model, _ = optimizer.select_model("Test query", prefer_speed=True)

        assert model in optimizer.model_configs

    def test_select_prefer_quality(self):
        """Test selection preferring quality"""
        optimizer = LLMCostOptimizer()

        model, _ = optimizer.select_model("Test query", prefer_quality=True)

        config = optimizer.model_configs[model]
        assert config.quality_score > 0.5

    def test_select_with_cost_limit(self):
        """Test selection with cost limit"""
        optimizer = LLMCostOptimizer()

        model, _ = optimizer.select_model("Test query", max_cost_per_query=0.001)

        assert model in optimizer.model_configs


class TestCostRecording:
    """Test record_cost method"""

    def test_record_cost_basic(self):
        """Test basic cost recording"""
        optimizer = LLMCostOptimizer()

        record = optimizer.record_cost(
            model="gemini-1.5-flash", input_tokens=100, output_tokens=200
        )

        assert record.model == "gemini-1.5-flash"
        assert record.input_tokens == 100
        assert record.output_tokens == 200
        assert record.cost_usd > 0
        assert len(optimizer.cost_records) == 1

    def test_record_cost_with_tenant(self):
        """Test cost recording with tenant ID"""
        optimizer = LLMCostOptimizer()

        record = optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            tenant_id="tenant-123",
        )

        assert record.tenant_id == "tenant-123"

    def test_record_cached_query(self):
        """Test recording cached query has zero cost"""
        optimizer = LLMCostOptimizer()

        record = optimizer.record_cost(
            model="gemini-1.5-flash", input_tokens=100, output_tokens=200, cached=True
        )

        assert record.cached is True
        assert record.cost_usd == 0.0

    def test_record_unknown_model(self):
        """Test recording cost for unknown model"""
        optimizer = LLMCostOptimizer()

        record = optimizer.record_cost(model="unknown-model", input_tokens=100, output_tokens=200)

        assert record.cost_usd > 0  # Should estimate conservatively

    def test_record_limits_history(self):
        """Test cost records are limited to 10000"""
        optimizer = LLMCostOptimizer()

        # Record more than limit
        for i in range(10005):
            optimizer.record_cost(model="gemini-1.5-flash", input_tokens=10, output_tokens=10)

        assert len(optimizer.cost_records) == 10000


class TestTenantCosts:
    """Test get_tenant_costs method"""

    def test_get_tenant_costs_daily(self):
        """Test getting daily tenant costs"""
        optimizer = LLMCostOptimizer()

        optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            tenant_id="tenant-123",
        )

        costs = optimizer.get_tenant_costs("tenant-123", "daily")

        assert costs["tenant_id"] == "tenant-123"
        assert costs["total_queries"] == 1
        assert costs["total_cost_usd"] > 0

    def test_get_tenant_costs_with_cache(self):
        """Test tenant costs include cache statistics"""
        optimizer = LLMCostOptimizer()

        optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            tenant_id="tenant-123",
            cached=True,
        )

        costs = optimizer.get_tenant_costs("tenant-123", "daily")

        assert costs["cached_queries"] == 1
        assert costs["cache_savings_percent"] == 100.0

    def test_get_tenant_costs_by_model(self):
        """Test tenant costs broken down by model"""
        optimizer = LLMCostOptimizer()

        optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=200,
            tenant_id="tenant-123",
        )

        costs = optimizer.get_tenant_costs("tenant-123", "daily")

        assert "cost_by_model" in costs
        assert "gemini-1.5-flash" in costs["cost_by_model"]


class TestBudgetEnforcement:
    """Test is_within_budget method"""

    def test_within_budget_no_tenant(self):
        """Test budget check without tenant"""
        optimizer = LLMCostOptimizer()

        is_within = optimizer.is_within_budget(estimated_cost=0.01)

        assert is_within is True

    def test_exceeds_per_query_limit(self):
        """Test exceeding per-query limit"""
        optimizer = LLMCostOptimizer()

        is_within = optimizer.is_within_budget(
            tenant_id="tenant-123",
            estimated_cost=1.0,  # Exceeds default 0.05 limit
        )

        assert is_within is False

    def test_within_daily_limit(self):
        """Test within daily limit"""
        optimizer = LLMCostOptimizer()

        # Record some costs
        for _ in range(5):
            optimizer.record_cost(
                model="gemini-1.5-flash",
                input_tokens=100,
                output_tokens=200,
                tenant_id="tenant-123",
            )

        is_within = optimizer.is_within_budget(tenant_id="tenant-123", estimated_cost=0.01)

        assert is_within is True

    def test_custom_tenant_budget(self):
        """Test setting custom tenant budget"""
        optimizer = LLMCostOptimizer()

        budget = CostBudget(daily_limit_usd=0.01)
        optimizer.set_tenant_budget("tenant-123", budget)

        # Record cost that exceeds custom budget
        optimizer.record_cost(
            model="gemini-1.5-flash",
            input_tokens=1000,
            output_tokens=2000,
            tenant_id="tenant-123",
        )

        is_within = optimizer.is_within_budget(tenant_id="tenant-123", estimated_cost=0.01)

        # Should exceed the low daily limit
        assert is_within is False


class TestOptimizationReport:
    """Test get_optimization_report method"""

    def test_report_no_data(self):
        """Test report with no data"""
        optimizer = LLMCostOptimizer()

        report = optimizer.get_optimization_report()

        assert report["status"] == "no_data"
        assert report["total_cost_usd"] == 0

    def test_report_with_data(self):
        """Test report with cost data"""
        optimizer = LLMCostOptimizer()

        optimizer.record_cost(model="gemini-1.5-flash", input_tokens=100, output_tokens=200)

        report = optimizer.get_optimization_report()

        assert report["total_queries"] == 1
        assert report["total_cost_usd"] > 0
        assert "recommendations" in report

    def test_report_includes_cache_stats(self):
        """Test report includes cache statistics"""
        optimizer = LLMCostOptimizer()

        optimizer.record_cost(
            model="gemini-1.5-flash", input_tokens=100, output_tokens=200, cached=True
        )

        report = optimizer.get_optimization_report()

        assert report["cached_queries"] == 1
        assert "cache_hit_rate" in report

    def test_report_recommendations(self):
        """Test report includes recommendations"""
        optimizer = LLMCostOptimizer()

        # Record with premium model
        for _ in range(10):
            optimizer.record_cost(model="gemini-1.5-pro", input_tokens=100, output_tokens=200)

        report = optimizer.get_optimization_report()

        assert len(report["recommendations"]) > 0


class TestFactoryFunction:
    """Test get_cost_optimizer factory"""

    def test_get_cost_optimizer(self):
        """Test factory function returns instance"""
        optimizer = get_cost_optimizer()

        assert isinstance(optimizer, LLMCostOptimizer)

    def test_get_cost_optimizer_singleton(self):
        """Test factory returns same instance"""
        optimizer1 = get_cost_optimizer()
        optimizer2 = get_cost_optimizer()

        assert optimizer1 is optimizer2
