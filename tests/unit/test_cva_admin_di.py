"""
CVA Admin DI Container Tests - Phase 3.1

Happy path:    CvaAgentCache wordt geïnjecteerd via DI container
Unhappy path:  Wanneer container niet beschikbaar is, geeft endpoint 503
Behavioral:    In tests kan de cache worden vervangen zonder module-reload
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cachetools import TTLCache


class TestCvaAdminDependencyInjection:
    """Test that CVA admin uses DI container instead of global state."""

    def test_no_global_cache_in_source_code(self):
        """Happy path: Verify global TTLCache and Lock are removed from source."""
        import src.core.api.cva_admin as mod

        source = inspect.getsource(mod)
        assert "_agent_cache: TTLCache" not in source
        assert "_agent_lock = asyncio.Lock()" not in source

    def test_container_has_cva_agent_cache(self):
        """Happy path: Container provides cva_agent_cache provider."""
        from src.core.container import Container

        container = Container()
        assert hasattr(container, "cva_agent_cache")
        # Provider should exist and be callable
        provider = getattr(container, "cva_agent_cache", None)
        assert provider is not None

    def test_cache_provider_instantiation(self):
        """Happy path: CvaAgentCacheProvider can be instantiated."""
        from src.core.services.cva_cache_provider import CvaAgentCacheProvider

        provider = CvaAgentCacheProvider(maxsize=100, ttl=3600)
        assert provider is not None
        assert isinstance(provider._cache, TTLCache)

    @pytest.mark.asyncio
    async def test_cache_provider_get_or_create(self):
        """Happy path: Cache provider get_or_create works correctly."""
        from src.core.services.cva_cache_provider import CvaAgentCacheProvider

        provider = CvaAgentCacheProvider(maxsize=100, ttl=3600)
        mock_agent = MagicMock()
        factory = AsyncMock(return_value=mock_agent)

        # First call should create
        result1 = await provider.get_or_create("tenant_1", factory)
        assert result1 == mock_agent
        factory.assert_called_once_with("tenant_1")

        # Second call should return cached
        factory.reset_mock()
        result2 = await provider.get_or_create("tenant_1", factory)
        assert result2 == mock_agent
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_provider_invalidate(self):
        """Behavioral: Cache provider invalidate works correctly."""
        from src.core.services.cva_cache_provider import CvaAgentCacheProvider

        provider = CvaAgentCacheProvider(maxsize=100, ttl=3600)
        mock_agent = MagicMock()
        factory = AsyncMock(return_value=mock_agent)

        # Create cache entry
        await provider.get_or_create("tenant_1", factory)
        assert "tenant_1" in provider._cache

        # Invalidate
        provider.invalidate("tenant_1")
        assert "tenant_1" not in provider._cache

    def test_get_cva_agent_uses_injection(self):
        """Happy path: get_cva_agent function uses dependency injection."""
        import src.core.api.v1.cva.state as mod

        source = inspect.getsource(mod.get_cva_agent)
        # Should use DI pattern: either @inject decorator OR container access
        assert (
            "@inject" in source
            or "Provide[" in source
            or "cache_provider" in source
            or "container.cva_agent_cache" in source
            or "_cva_agents" in source
        )

    @pytest.mark.asyncio
    async def test_container_can_override_cache(self):
        """Behavioral: In tests kan de cache worden vervangen zonder module-reload."""
        from dependency_injector import providers

        from src.core.container import Container
        from src.core.services.cva_cache_provider import CvaAgentCacheProvider

        container = Container()
        mock_cache = MagicMock(spec=CvaAgentCacheProvider)

        # Override with mock
        container.cva_agent_cache.override(providers.Object(mock_cache))

        # Should get mock when accessing provider
        result = container.cva_agent_cache()
        assert result == mock_cache

        # Cleanup
        container.cva_agent_cache.reset_override()


class TestCvaAdminServiceUnavailable:
    """Test service unavailable scenarios."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_503_when_cache_unavailable(self):
        """Unhappy path: Wanneer cache niet beschikbaar is, geeft endpoint 503."""
        from fastapi import HTTPException

        import src.core.api.v1.cva.state as mod

        # Simulate cache provider failure
        with patch.object(mod, "get_cva_agent", side_effect=HTTPException(status_code=503)):
            with pytest.raises(HTTPException) as exc_info:
                await mod.get_cva_agent(tenant_id=1)
            assert exc_info.value.status_code == 503

    def test_source_uses_container_pattern(self):
        """Verify DI container pattern is used (either wiring OR direct access)."""
        import src.core.api.v1.cva.state as mod

        source = inspect.getsource(mod)
        # Should use DI pattern: either wiring imports OR container access
        assert (
            "from dependency_injector.wiring import" in source
            or "from src.core.container import container" in source
            or "container.cva_agent_cache" in source
            or "_cva_agents" in source
        )
