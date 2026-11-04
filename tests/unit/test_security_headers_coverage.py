"""
Comprehensive tests for src/core/middleware/security_headers.py
Coverage target: 100% of security headers middleware
"""

from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.core.middleware.security_headers import SecurityHeadersMiddleware


class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware class"""

    @pytest.mark.asyncio
    async def test_dispatch_adds_x_frame_options(self):
        """Test dispatch adds X-Frame-Options header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "x-frame-options" in result.headers
        assert result.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_dispatch_adds_x_content_type_options(self):
        """Test dispatch adds X-Content-Type-Options header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "x-content-type-options" in result.headers
        assert result.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_dispatch_adds_strict_transport_security(self):
        """Test dispatch adds Strict-Transport-Security header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "strict-transport-security" in result.headers
        hsts = result.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

    @pytest.mark.asyncio
    async def test_dispatch_adds_content_security_policy(self):
        """Test dispatch adds Content-Security-Policy header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "content-security-policy" in result.headers
        csp = result.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp

    @pytest.mark.asyncio
    async def test_dispatch_adds_x_xss_protection(self):
        """Test dispatch adds X-XSS-Protection header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "x-xss-protection" in result.headers
        assert result.headers["x-xss-protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_dispatch_adds_referrer_policy(self):
        """Test dispatch adds Referrer-Policy header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "referrer-policy" in result.headers
        assert result.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_dispatch_adds_permissions_policy(self):
        """Test dispatch adds Permissions-Policy header"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "permissions-policy" in result.headers
        policy = result.headers["permissions-policy"]
        assert "geolocation=()" in policy
        assert "microphone=()" in policy
        assert "camera=()" in policy
        assert "payment=()" in policy

    @pytest.mark.asyncio
    async def test_dispatch_calls_next_middleware(self):
        """Test dispatch calls next middleware"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_returns_response(self):
        """Test dispatch returns response from call_next"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response(content="test content", status_code=200)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_preserves_existing_headers(self):
        """Test dispatch preserves existing response headers"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        response.headers["Custom-Header"] = "custom-value"
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "custom-header" in result.headers
        assert result.headers["custom-header"] == "custom-value"


class TestCSPDirectives:
    """Test Content-Security-Policy directives"""

    @pytest.mark.asyncio
    async def test_csp_allows_self_scripts(self):
        """Test CSP allows same-origin scripts"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        csp = result.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    @pytest.mark.asyncio
    async def test_csp_allows_inline_scripts(self):
        """Test CSP allows inline scripts for FastAPI docs"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        csp = result.headers["content-security-policy"]
        assert "'unsafe-inline'" in csp

    @pytest.mark.asyncio
    async def test_csp_blocks_frame_ancestors(self):
        """Test CSP blocks frame ancestors"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        csp = result.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in csp

    @pytest.mark.asyncio
    async def test_csp_allows_data_images(self):
        """Test CSP allows data URIs for images"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        csp = result.headers["content-security-policy"]
        assert "img-src 'self' data: https:" in csp


class TestHSTSConfiguration:
    """Test Strict-Transport-Security configuration"""

    @pytest.mark.asyncio
    async def test_hsts_one_year_max_age(self):
        """Test HSTS max-age is 1 year (31536000 seconds)"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        hsts = result.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts

    @pytest.mark.asyncio
    async def test_hsts_includes_subdomains(self):
        """Test HSTS applies to subdomains"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        hsts = result.headers["strict-transport-security"]
        assert "includeSubDomains" in hsts

    @pytest.mark.asyncio
    async def test_hsts_preload_enabled(self):
        """Test HSTS preload is enabled"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        hsts = result.headers["strict-transport-security"]
        assert "preload" in hsts


class TestAllSecurityHeaders:
    """Test all security headers are present"""

    @pytest.mark.asyncio
    async def test_all_required_headers_present(self):
        """Test all OWASP recommended headers are present"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response()
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        required_headers = [
            "x-frame-options",
            "x-content-type-options",
            "strict-transport-security",
            "content-security-policy",
            "x-xss-protection",
            "referrer-policy",
            "permissions-policy",
        ]

        for header in required_headers:
            assert header in result.headers, f"Missing required header: {header}"


class TestEdgeCases:
    """Test edge cases"""

    @pytest.mark.asyncio
    async def test_dispatch_with_error_response(self):
        """Test dispatch adds headers even on error responses"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response(status_code=500)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result.status_code == 500
        assert "x-frame-options" in result.headers

    @pytest.mark.asyncio
    async def test_dispatch_with_redirect_response(self):
        """Test dispatch adds headers on redirect responses"""
        middleware = SecurityHeadersMiddleware(app=Mock())
        request = Mock(spec=Request)
        response = Response(status_code=302)
        response.headers["Location"] = "/redirect"
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result.status_code == 302
        assert "x-frame-options" in result.headers
        assert "location" in result.headers

    @pytest.mark.asyncio
    async def test_middleware_initialization(self):
        """Test middleware can be initialized"""
        app = Mock()
        middleware = SecurityHeadersMiddleware(app)

        assert middleware.app == app
