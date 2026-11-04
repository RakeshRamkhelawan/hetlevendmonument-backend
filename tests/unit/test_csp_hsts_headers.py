"""
Test CSP and HSTS Header Configuration
TDD RED PHASE: These tests should FAIL initially
"""

import os
from unittest.mock import patch

import pytest


class TestSecurityHeaders:
    """TDD RED PHASE: Test CSP and HSTS header configuration"""

    def test_csp_header_strict_in_production(self):
        """RED: Production CSP should be restrictive"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            csp = SecurityHeadersConfig.get_csp_header()

            # Should NOT allow unsafe-eval in production
            assert "unsafe-eval" not in csp, "Production should not allow unsafe-eval"

            # Should have frame-ancestors none
            assert "frame-ancestors 'none'" in csp, "Should prevent framing"

            # Should upgrade insecure requests
            assert "upgrade-insecure-requests" in csp, "Should upgrade HTTP to HTTPS"

    def test_csp_header_permissive_in_development(self):
        """RED: Development CSP should allow localhost"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            csp = SecurityHeadersConfig.get_csp_header()

            # Development can use unsafe-eval (for hot reload)
            assert "unsafe-eval" in csp, "Development should allow unsafe-eval"

            # Should allow localhost connections
            assert "localhost" in csp or "127.0.0.1" in csp, "Should allow localhost"

    def test_hsts_only_in_production_with_https(self):
        """RED: HSTS should only be set in production with HTTPS"""
        # Production + HTTPS = HSTS enabled
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "HTTPS_ENABLED": "true"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            hsts = SecurityHeadersConfig.get_hsts_header()

            assert hsts != "", "HSTS should be set in production"
            assert "max-age=31536000" in hsts, "Should have 1 year max-age"
            assert "includeSubDomains" in hsts, "Should include subdomains"
            assert "preload" in hsts, "Should be preloadable"

    def test_no_hsts_in_development(self):
        """RED: Development should NOT have HSTS"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            hsts = SecurityHeadersConfig.get_hsts_header()

            assert hsts == "", "HSTS should be empty in development"

    def test_no_hsts_without_https(self):
        """RED: HSTS should not be set without HTTPS"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "HTTPS_ENABLED": "false"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            hsts = SecurityHeadersConfig.get_hsts_header()

            assert hsts == "", "HSTS should be empty without HTTPS"

    def test_all_security_headers_included(self):
        """RED: get_all_headers should include all required headers"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            from src.core.middleware.security_headers import SecurityHeadersConfig

            headers = SecurityHeadersConfig.get_all_headers()

            required_headers = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "X-XSS-Protection",
                "Referrer-Policy",
                "Permissions-Policy",
                "Content-Security-Policy",
            ]

            for header in required_headers:
                assert header in headers, f"Missing required header: {header}"

    def test_x_content_type_options_nosniff(self):
        """RED: X-Content-Type-Options must be nosniff"""
        from src.core.middleware.security_headers import SecurityHeadersConfig

        headers = SecurityHeadersConfig.get_all_headers()

        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_deny(self):
        """RED: X-Frame-Options must be DENY"""
        from src.core.middleware.security_headers import SecurityHeadersConfig

        headers = SecurityHeadersConfig.get_all_headers()

        assert headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection_enabled(self):
        """RED: X-XSS-Protection must be enabled"""
        from src.core.middleware.security_headers import SecurityHeadersConfig

        headers = SecurityHeadersConfig.get_all_headers()

        assert headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy_strict(self):
        """RED: Referrer-Policy should be strict"""
        from src.core.middleware.security_headers import SecurityHeadersConfig

        headers = SecurityHeadersConfig.get_all_headers()

        assert "Referrer-Policy" in headers
        assert "strict-origin" in headers["Referrer-Policy"]


# Run tests - SHOULD FAIL initially
# pytest tests/unit/test_csp_hsts_headers.py -v
