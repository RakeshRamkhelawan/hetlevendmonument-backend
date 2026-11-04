from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm.intelligent_router import (
    IntelligentRouter,
    ProviderConfiguration,
    ProviderHealth,
    ProviderMetrics,
    RoutingStrategy,
)


class TestIntelligentRouter:
    @pytest.fixture
    def mock_cache(self):
        return AsyncMock()

    @pytest.fixture
    def router(self, mock_cache):
        # Patch get_cache_manager global import or injection
        with patch("src.core.llm.intelligent_router.get_cache_manager", return_value=mock_cache):
            r = IntelligentRouter(strategy=RoutingStrategy.ROUND_ROBIN)
            r.cache_manager = mock_cache
            return r

    @pytest.mark.asyncio
    async def test_round_robin_selection(self, router):
        # Register 2 providers
        router.register_provider(
            ProviderConfiguration(provider_id="p1", endpoint_url="url1", api_key_env="k1")
        )
        router.register_provider(
            ProviderConfiguration(provider_id="p2", endpoint_url="url2", api_key_env="k2")
        )

        # Test alternation
        s1 = await router.select_provider()
        s2 = await router.select_provider()
        s3 = await router.select_provider()

        assert s1 != s2
        assert s1 == s3

    @pytest.mark.asyncio
    async def test_circuit_breaker_trip(self, router):
        router.register_provider(
            ProviderConfiguration(provider_id="p1", endpoint_url="url1", api_key_env="k1")
        )

        # Fail 5 times
        for _ in range(5):
            await router.record_request_completion("p1", success=False, response_time=1.0)

        metrics = router.get_provider_metrics("p1")
        assert metrics["health_status"] == ProviderHealth.OFFLINE.value

        # Should now return None (no providers)
        assert await router.select_provider() is None

    @pytest.mark.asyncio
    async def test_performance_based_selection(self, router):
        router.set_routing_strategy(RoutingStrategy.PERFORMANCE_BASED)
        router.register_provider(
            ProviderConfiguration(provider_id="fast", endpoint_url="url1", api_key_env="k1")
        )
        router.register_provider(
            ProviderConfiguration(provider_id="slow", endpoint_url="url2", api_key_env="k2")
        )

        # Simulate fast provider success
        await router.record_request_completion("fast", success=True, response_time=0.1)
        # Simulate slow provider success
        await router.record_request_completion("slow", success=True, response_time=1.0)

        # Should select 'fast'
        selected = await router.select_provider()
        assert selected == "fast"

    @pytest.mark.asyncio
    async def test_cost_optimized_selection(self, router):
        router.set_routing_strategy(RoutingStrategy.COST_OPTIMIZED)
        router.register_provider(
            ProviderConfiguration(
                provider_id="cheap",
                endpoint_url="url1",
                api_key_env="k1",
                cost_per_token=0.001,
            )
        )
        router.register_provider(
            ProviderConfiguration(
                provider_id="expensive",
                endpoint_url="url2",
                api_key_env="k2",
                cost_per_token=0.1,
            )
        )

        selected = await router.select_provider()
        assert selected == "cheap"

    @pytest.mark.asyncio
    async def test_provider_registration_validation(self, router):
        # Missing ID
        res = router.register_provider(
            ProviderConfiguration(provider_id="", endpoint_url="url", api_key_env="k")
        )
        assert res is False

        # Missing URL
        res = router.register_provider(
            ProviderConfiguration(provider_id="p1", endpoint_url="", api_key_env="k")
        )
        assert res is False

    @pytest.mark.asyncio
    async def test_caching_behavior(self, router, mock_cache):
        router.register_provider(
            ProviderConfiguration(provider_id="p1", endpoint_url="url1", api_key_env="k1")
        )

        context = {"task": "test"}
        await router.select_provider(request_context=context)

        # Verify cache set was called
        assert mock_cache.set.called
        call_args = mock_cache.set.call_args
        assert call_args[0][1] == "p1"  # Value cached
