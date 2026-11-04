"""
Comprehensive tests for src/core/middleware/rate_limiter.py
Coverage target: 100% of rate limiting middleware
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.core.middleware.rate_limiter import get_limiter, rate_limit_exceeded_handler
import src.core.middleware.rate_limiter as _rl_mod


@pytest.fixture(autouse=True)
def _clear_limiter_cache():
    _rl_mod._limiter_cache.clear()
    yield
    _rl_mod._limiter_cache.clear()


class TestGetLimiter:
    """Test get_limiter function"""

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_creates_instance(self, mock_limiter_class):
        """Test get_limiter creates Limiter instance"""
        mock_limiter = Mock()
        mock_limiter_class.return_value = mock_limiter

        limiter = get_limiter()

        assert limiter == mock_limiter
        mock_limiter_class.assert_called_once()

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_default_limits(self, mock_limiter_class):
        """Test get_limiter sets default limits"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]
        assert call_kwargs["default_limits"] == ["100/minute"]

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_storage_uri(self, mock_limiter_class):
        """Test get_limiter uses in-memory storage"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]
        assert call_kwargs["storage_uri"] == "memory://"

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_strategy(self, mock_limiter_class):
        """Test get_limiter uses fixed-window strategy"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]
        assert call_kwargs["strategy"] == "fixed-window"

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_headers_enabled(self, mock_limiter_class):
        """Test get_limiter enables headers"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]
        assert call_kwargs["headers_enabled"] is True

    @patch("src.core.middleware.rate_limiter.Limiter")
    @patch("src.core.middleware.rate_limiter.get_remote_address")
    def test_get_limiter_key_func(self, mock_get_remote, mock_limiter_class):
        """Test get_limiter uses get_remote_address as key function"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]
        assert call_kwargs["key_func"] == mock_get_remote


class TestRateLimitExceededHandler:
    """Test rate_limit_exceeded_handler function"""

    @pytest.mark.asyncio
    async def test_handler_returns_429_status(self):
        """Test handler returns 429 status code"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_handler_returns_json_response(self):
        """Test handler returns JSONResponse"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        assert isinstance(response, JSONResponse)

    @pytest.mark.asyncio
    async def test_handler_includes_error_message(self):
        """Test handler includes error in response body"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        # Access body content
        assert response.body is not None
        import json

        content = json.loads(response.body)
        assert content["error"] == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_handler_includes_detail_message(self):
        """Test handler includes detail in response body"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)
        # The handler returns an informative message with limit and window
        assert "Maximum" in content["detail"]
        assert "requests per" in content["detail"]

    @pytest.mark.asyncio
    async def test_handler_includes_limit_info(self):
        """Test handler includes limit information"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)
        assert content["limit"] == "100 per 1 minute"

    @pytest.mark.asyncio
    async def test_handler_includes_retry_after_header(self):
        """Test handler includes Retry-After header"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        assert "retry-after" in response.headers
        assert response.headers["retry-after"] == "60"

    @pytest.mark.asyncio
    async def test_handler_with_different_limit_detail(self):
        """Test handler with different rate limit detail"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "50 per 1 hour"

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)
        assert content["limit"] == "50 per 1 hour"
        assert response.status_code == 429


class TestIntegration:
    """Test integration scenarios"""

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_limiter_configuration_complete(self, mock_limiter_class):
        """Test limiter has all required configuration"""
        get_limiter()

        call_kwargs = mock_limiter_class.call_args[1]

        # Verify all critical parameters are set
        assert "key_func" in call_kwargs
        assert "default_limits" in call_kwargs
        assert "storage_uri" in call_kwargs
        assert "strategy" in call_kwargs
        assert "headers_enabled" in call_kwargs

    @pytest.mark.asyncio
    async def test_handler_response_structure_complete(self):
        """Test handler response has all required fields"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = "100 per 1 minute"

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)

        # Verify all required fields present
        assert "error" in content
        assert "detail" in content
        assert "limit" in content
        assert "retry-after" in response.headers


class TestEdgeCases:
    """Test edge cases"""

    @pytest.mark.asyncio
    async def test_handler_with_empty_detail(self):
        """Test handler with empty detail string"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = ""

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)
        assert content["limit"] == ""
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_handler_with_none_detail(self):
        """Test handler with None detail"""
        request = Mock(spec=Request)
        exc = Mock(spec=RateLimitExceeded)
        exc.detail = None

        response = await rate_limit_exceeded_handler(request, exc)

        import json

        content = json.loads(response.body)
        assert content["limit"] == "None"

    @patch("src.core.middleware.rate_limiter.Limiter")
    def test_get_limiter_multiple_calls(self, mock_limiter_class):
        """Test calling get_limiter multiple times returns the same cached instance"""
        mock_limiter1 = Mock()
        mock_limiter_class.return_value = mock_limiter1

        limiter1 = get_limiter()
        limiter2 = get_limiter()

        # get_limiter caches per service_name -- same instance is returned
        assert limiter1 == mock_limiter1
        assert limiter2 == mock_limiter1
        assert mock_limiter_class.call_count == 1
