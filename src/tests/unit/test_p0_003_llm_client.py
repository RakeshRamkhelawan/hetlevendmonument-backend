"""
Unit tests for P0-3: MOCK-003 - Mock LLM Client Fallback
Tests that mock LLM fallback is removed and production client works correctly
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.llm.production_llm_client import ProductionLLMClient, QueryComplexity, RateLimiter
from src.core.shared.llm_client import LLMMessage


class TestProductionLLMClient:
    """Tests for ProductionLLMClient"""

    def test_no_api_key_raises_error(self):
        """Test that missing GOOGLE_API_KEY raises EnvironmentError"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(EnvironmentError, match="GOOGLE_API_KEY must be set"):
                ProductionLLMClient()

    def test_api_key_from_env(self):
        """Test that API key is loaded from environment"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-api-key-12345"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()
                    assert client.config.api_key == "test-api-key-12345"

    def test_complexity_analysis_simple(self):
        """Test that short queries are classified as SIMPLE"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()

                    messages = [LLMMessage(role="user", content="Hello")]
                    complexity = client._analyze_complexity(messages)

                    assert complexity == QueryComplexity.SIMPLE

    def test_complexity_analysis_medium(self):
        """Test that medium-length queries are classified as MEDIUM"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()

                    # Medium query (250 chars)
                    messages = [LLMMessage(role="user", content="a" * 250)]
                    complexity = client._analyze_complexity(messages)

                    assert complexity == QueryComplexity.MEDIUM

    def test_complexity_analysis_complex(self):
        """Test that complex queries are classified as COMPLEX"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()

                    # Complex query with keywords
                    messages = [
                        LLMMessage(
                            role="user",
                            content="Please analyze the architecture and provide a detailed design",
                        )
                    ]
                    complexity = client._analyze_complexity(messages)

                    assert complexity == QueryComplexity.COMPLEX

    def test_routing_simple_to_flash(self):
        """Test that simple queries route to Flash model"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel") as mock_model:
                    mock_flash: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
                    mock_pro: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type

                    def model_side_effect(name):
                        if "flash" in name:
                            return mock_flash
                        return mock_pro

                    mock_model.side_effect = model_side_effect

                    client = ProductionLLMClient()
                    model = client._route_query(QueryComplexity.SIMPLE)

                    assert model == client.flash_model
                    assert client.flash_count == 1
                    assert client.pro_count == 0

    def test_routing_complex_to_pro(self):
        """Test that complex queries route to Pro model"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel") as mock_model:
                    mock_flash: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
                    mock_pro: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type

                    def model_side_effect(name):
                        if "flash" in name:
                            return mock_flash
                        return mock_pro

                    mock_model.side_effect = model_side_effect

                    client = ProductionLLMClient()
                    model = client._route_query(QueryComplexity.COMPLEX)

                    assert model == client.pro_model
                    assert client.pro_count == 1
                    assert client.flash_count == 0

    def test_routing_stats_calculation(self):
        """Test routing statistics calculation"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()

                    # Simulate routing: 8 flash, 2 pro (80/20 split)
                    for _ in range(8):
                        client._route_query(QueryComplexity.SIMPLE)
                    for _ in range(2):
                        client._route_query(QueryComplexity.COMPLEX)

                    stats = client.get_routing_stats()

                    assert stats["flash_count"] == 8
                    assert stats["pro_count"] == 2
                    assert stats["total_queries"] == 10
                    assert stats["flash_percentage"] == 80.0
                    assert stats["pro_percentage"] == 20.0

    @pytest.mark.asyncio
    async def test_text_completion_no_mock_fallback(self):
        """Test that text completion fails fast without mock fallback"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel") as mock_model:
                    # Mock model that raises exception
                    mock_instance: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
                    mock_instance.generate_content.side_effect = Exception("API Error")
                    mock_model.return_value = mock_instance

                    client = ProductionLLMClient()

                    response = await client.text_completion("Test prompt")

                    # Should fail (not fall back to mock)
                    assert response.success is False
                    assert "API Error" in response.error_message


class TestRateLimiter:
    """Tests for RateLimiter"""

    def test_rate_limiter_without_redis(self):
        """Test that rate limiter allows requests when Redis unavailable"""
        with patch("redis.from_url", side_effect=Exception("Redis unavailable")):
            limiter = RateLimiter()
            assert limiter.check_limit("user123") is True  # Fail open

    def test_rate_limiter_first_request(self):
        """Test that first request is allowed"""
        mock_redis: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
        mock_redis.get.return_value = None  # No existing count

        limiter = RateLimiter()
        limiter.redis = mock_redis

        result = limiter.check_limit("user123")

        assert result is True
        mock_redis.setex.assert_called_once()

    def test_rate_limiter_within_limit(self):
        """Test that requests within limit are allowed"""
        mock_redis: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
        mock_redis.get.return_value = "50"  # Within limit

        limiter = RateLimiter()
        limiter.redis = mock_redis
        limiter.daily_limit = 100

        result = limiter.check_limit("user123")

        assert result is True
        mock_redis.incr.assert_called_once()

    def test_rate_limiter_exceeds_limit(self):
        """Test that requests exceeding limit are blocked"""
        mock_redis: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
        mock_redis.get.return_value = "100"  # At limit

        limiter = RateLimiter()
        limiter.redis = mock_redis
        limiter.daily_limit = 100

        result = limiter.check_limit("user123")

        assert result is False
        mock_redis.incr.assert_not_called()


class TestProductionConfig:
    """Tests for production configuration"""

    def test_no_mock_provider_in_production_config(self):
        """Verify that production config has no mock provider"""
        # Check the production_config.py file
        with open("core/config/production_config.py") as f:
            content = f.read()

        # Should have comment about removed mock provider
        assert "Mock provider REMOVED for production" in content
        assert "P0-3: MOCK-003" in content

        # Should not configure mock LLM provider
        assert 'self.llm_providers["mock"]' not in content

    def test_no_mock_fallback_in_production_config(self):
        """Verify that production config has no fallback to mock"""
        with open("core/config/production_config.py") as f:
            content = f.read()

        # Should not have fallback_to="mock"
        assert 'fallback_to="mock"' not in content

        # Should have fail-fast approach
        assert "fail fast" in content.lower() or "No fallback" in content


class TestCaching:
    """Tests for Redis caching"""

    def test_cache_key_generation(self):
        """Test that cache keys are generated consistently"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    client = ProductionLLMClient()

                    messages = [LLMMessage(role="user", content="Test")]
                    key1 = client._generate_cache_key(messages)
                    key2 = client._generate_cache_key(messages)

                    # Same messages should generate same key
                    assert key1 == key2
                    assert key1.startswith("llm:cache:")

    def test_cache_miss_returns_none(self):
        """Test that cache miss returns None"""
        with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
            with patch("google.generativeai.configure"):
                with patch("google.generativeai.GenerativeModel"):
                    mock_redis: Any = MagicMock()  # TODO(TYPE): replace Any with concrete type
                    mock_redis.get.return_value = None

                    client = ProductionLLMClient()
                    client.cache = mock_redis

                    result = client._get_cached_response("test_key")

                    assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
