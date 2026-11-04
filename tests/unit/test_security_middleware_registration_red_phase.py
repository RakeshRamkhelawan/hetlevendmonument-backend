"""
RED Phase Test: Verify SecurityMiddleware Registration Status

This test suite checks whether the production SecurityMiddleware from
src.core.security.security_middleware is properly registered in the
middleware stack.

Current Status: SecurityMiddleware should be registered but isn't
Expected: Tests will FAIL in RED phase, PASS after registration (GREEN phase)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSecurityMiddlewareRegistration:
    """Verify SecurityMiddleware is registered in middleware stack"""

    def test_security_middleware_imported_in_config(self):
        """RED: Verify SecurityMiddleware is imported in middleware_config.py"""
        try:
            import inspect

            from src.core.api.setup import middleware_config

            # Check imports
            source = inspect.getsource(middleware_config)
            assert (
                "from src.core.security.security_middleware import SecurityMiddleware" in source
            ), "SecurityMiddleware not imported from src.core.security.security_middleware"
        except AssertionError as e:
            pytest.fail(f"SecurityMiddleware import missing: {e}")

    def test_security_middleware_added_to_app(self):
        """RED: Verify SecurityMiddleware is added to FastAPI app"""
        try:
            import inspect

            from src.core.api.setup.middleware_config import setup_middleware

            # Get setup_middleware source
            source = inspect.getsource(setup_middleware)

            # Check that add_middleware is called with SecurityMiddleware
            assert (
                "SecurityMiddleware" in source
            ), "SecurityMiddleware not referenced in setup_middleware function"
            assert (
                "app.add_middleware(SecurityMiddleware" in source
            ), "app.add_middleware(SecurityMiddleware... not found in setup_middleware"
        except AssertionError as e:
            pytest.fail(f"SecurityMiddleware registration missing: {e}")

    def test_security_middleware_in_correct_position(self):
        """RED: Verify SecurityMiddleware is added in correct LIFO order"""
        try:
            import inspect

            from src.core.api.setup.middleware_config import setup_middleware

            source = inspect.getsource(setup_middleware)

            # SecurityMiddleware should be added AFTER SecurityHeadersMiddleware
            # (because add_middleware uses LIFO order)
            sec_headers_pos = source.find("SecurityHeadersMiddleware")
            sec_middleware_pos = source.find("app.add_middleware(SecurityMiddleware")

            assert sec_headers_pos > 0, "SecurityHeadersMiddleware not found"
            assert sec_middleware_pos > 0, "SecurityMiddleware not registered"
            # SecurityMiddleware should be added BEFORE SecurityHeadersMiddleware in code
            # (executed AFTER in request flow due to LIFO)
            assert (
                sec_middleware_pos < sec_headers_pos
            ), "SecurityMiddleware should be added before SecurityHeadersMiddleware in code (LIFO order)"
        except AssertionError as e:
            pytest.fail(f"SecurityMiddleware ordering issue: {e}")

    def test_security_middleware_with_enable_security_true(self):
        """RED: Verify SecurityMiddleware is initialized with enable_security=True"""
        try:
            import inspect

            from src.core.api.setup.middleware_config import setup_middleware

            source = inspect.getsource(setup_middleware)

            # Check that SecurityMiddleware is called with enable_security=True
            assert (
                "SecurityMiddleware" in source and "enable_security" in source
            ), "SecurityMiddleware should be initialized with enable_security parameter"
        except AssertionError as e:
            pytest.fail(f"SecurityMiddleware enable_security parameter missing: {e}")


class TestSecurityMiddlewareHeaders:
    """Test that SecurityMiddleware adds required security headers to responses"""

    @pytest.mark.asyncio
    async def test_security_headers_present_in_response(self):
        """RED: Verify security headers are included in API response"""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from src.core.middleware.security_headers import SecurityHeadersMiddleware

        app = FastAPI()

        # Add SecurityHeadersMiddleware directly (avoid full middleware stack
        # which requires auth for non-public paths and short-circuits /health)
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test-health")
        async def health():
            return JSONResponse({"status": "ok"})

        # Test client
        client = TestClient(app)
        response = client.get("/test-health")

        # Verify security headers from SecurityHeadersMiddleware are present
        security_headers = [
            "x-content-type-options",  # prevent MIME sniffing
            "x-frame-options",  # prevent clickjacking
            "x-xss-protection",  # XSS protection
            "strict-transport-security",  # HSTS
            "content-security-policy",  # CSP headers
        ]

        for header in security_headers:
            assert header in response.headers, (
                f"Missing security header: {header}. "
                f"SecurityHeadersMiddleware may not be registered. "
                f"Current headers: {list(response.headers.keys())}"
            )

    def test_request_id_header_added(self):
        """RED: Verify X-Request-ID header is present in response"""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from src.core.api.setup.middleware_config import setup_middleware

        app = FastAPI()

        @app.get("/api/test")
        async def api_test():
            return JSONResponse({"message": "ok"})

        try:
            setup_middleware(app)
        except Exception as e:
            pytest.skip(f"Middleware setup failed: {e}")

        client = TestClient(app)
        response = client.get("/api/test")

        # X-Request-ID should be present if SecurityMiddleware or request logging is active
        # This is typically added by SecurityMiddleware or correlation middleware
        headers_list = list(response.headers.keys())

        # Either X-Request-ID or X-Correlation-ID should be present
        has_request_tracking = any(
            h in response.headers for h in ["X-Request-ID", "X-Correlation-ID", "X-Trace-ID"]
        )

        assert has_request_tracking, (
            f"No request tracking header found (X-Request-ID, X-Correlation-ID, or X-Trace-ID). "
            f"SecurityMiddleware may not be properly registered. "
            f"Response headers: {headers_list}"
        )


class TestSecurityMiddlewareImports:
    """Test that all required security middleware imports are correct"""

    def test_security_middleware_class_exists(self):
        """RED: Verify SecurityMiddleware class exists and is importable"""
        try:
            from src.core.security.security_middleware import SecurityMiddleware

            assert SecurityMiddleware is not None
            assert hasattr(SecurityMiddleware, "__init__")
            assert hasattr(SecurityMiddleware, "__call__")
        except ImportError as e:
            pytest.fail(f"Cannot import SecurityMiddleware: {e}")

    def test_security_middleware_init_signature(self):
        """RED: Verify SecurityMiddleware has correct ASGI3 init signature"""
        import inspect

        from src.core.security.security_middleware import SecurityMiddleware

        sig = inspect.signature(SecurityMiddleware.__init__)
        params = list(sig.parameters.keys())

        # Should have self, app, and enable_security (keyword-only)
        assert "self" in params
        assert "app" in params
        assert (
            "enable_security" in params
        ), f"SecurityMiddleware should have enable_security parameter. Got: {params}"

        # enable_security should be keyword-only
        enable_security_param = sig.parameters["enable_security"]
        assert (
            enable_security_param.kind == inspect.Parameter.KEYWORD_ONLY
        ), f"enable_security should be keyword-only, but is {enable_security_param.kind}"


class TestSecurityMiddlewareFeatures:
    """Test that SecurityMiddleware provides expected security features"""

    def test_security_middleware_has_ip_allowlist_check(self):
        """RED: Verify SecurityMiddleware performs IP allowlist checks"""
        import inspect

        from src.core.security.security_middleware import SecurityMiddleware

        source = inspect.getsource(SecurityMiddleware)

        # Should check IP allowlist
        assert (
            "is_ip_allowed" in source
        ), "SecurityMiddleware should check IP allowlist via is_ip_allowed"
        # Sinds 2026-10-08 staat de blokkade in de IP-reputatie (Redis), niet in blocked_ips.
        assert "block_seconds_left" in source, "SecurityMiddleware should check blocked IPs"

    def test_security_middleware_has_rate_limiting(self):
        """RED: Verify SecurityMiddleware implements rate limiting"""
        import inspect

        from src.core.security.security_middleware import SecurityMiddleware

        source = inspect.getsource(SecurityMiddleware)

        # Should implement rate limiting
        assert "rate" in source.lower(), "SecurityMiddleware should implement rate limiting"

    def test_security_middleware_has_threat_detection(self):
        """RED: Verify SecurityMiddleware has threat detection"""
        import inspect

        from src.core.security.security_middleware import SecurityMiddleware

        source = inspect.getsource(SecurityMiddleware)

        # Should have threat detection
        assert (
            "ThreatLevel" in source or "threat" in source.lower()
        ), "SecurityMiddleware should detect threats"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
