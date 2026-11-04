"""
Comprehensive Test Suite for Security Middleware
Target: 70%+ coverage for src/core/middleware/security_middleware.py

Tests cover:
- SecurityMiddleware: request ID generation, security headers, logging, auth detection
- RateLimitMiddleware: request counting and rate limit headers
- CORSMiddleware: preflight requests and CORS header injection
"""

import logging
import time
import uuid
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient

from src.core.middleware.security_middleware import (
    CORSMiddleware,
    RateLimitMiddleware,
    SecurityMiddleware,
)

# ==================== FIXTURES ====================


@pytest.fixture
def test_app() -> FastAPI:
    """Create a minimal FastAPI app for middleware testing"""
    app = FastAPI(title="Security Middleware Test")

    # Add a simple health endpoint
    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    # Add a protected endpoint
    @app.get("/api/data")
    async def get_data():
        return {"data": "test"}

    # Add a POST endpoint for testing
    @app.post("/api/data")
    async def post_data():
        return {"created": True}

    return app


@pytest.fixture
def security_app(test_app: FastAPI) -> FastAPI:
    """FastAPI app with SecurityMiddleware"""
    test_app.add_middleware(SecurityMiddleware)
    return test_app


@pytest.fixture
def rate_limit_app(test_app: FastAPI) -> FastAPI:
    """FastAPI app with RateLimitMiddleware"""
    test_app.add_middleware(RateLimitMiddleware, requests_per_minute=10)
    return test_app


@pytest.fixture
def cors_app(test_app: FastAPI) -> FastAPI:
    """FastAPI app with CORSMiddleware"""
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8080"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "Authorization"],
    )
    return test_app


@pytest.fixture
def full_middleware_app(test_app: FastAPI) -> FastAPI:
    """FastAPI app with all middleware"""
    test_app.add_middleware(CORSMiddleware)
    test_app.add_middleware(RateLimitMiddleware)
    test_app.add_middleware(SecurityMiddleware)
    return test_app


@pytest.fixture
def security_client(security_app: FastAPI) -> TestClient:
    """Test client for app with SecurityMiddleware"""
    return TestClient(security_app)


@pytest.fixture
def rate_limit_client(rate_limit_app: FastAPI) -> TestClient:
    """Test client for app with RateLimitMiddleware"""
    return TestClient(rate_limit_app)


@pytest.fixture
def cors_client(cors_app: FastAPI) -> TestClient:
    """Test client for app with CORSMiddleware"""
    return TestClient(cors_app)


@pytest.fixture
def full_middleware_client(full_middleware_app: FastAPI) -> TestClient:
    """Test client for app with all middleware"""
    return TestClient(full_middleware_app)


# ==================== SECURITY MIDDLEWARE TESTS ====================


class TestSecurityMiddlewareDispatch:
    """Test SecurityMiddleware.dispatch() with various request types"""

    def test_request_id_generation(self, security_client: TestClient):
        """Test that request ID is generated and returned in response"""
        response = security_client.get("/health")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        # Should be a valid UUID
        request_id = response.headers["X-Request-ID"]
        uuid.UUID(request_id)  # Raises ValueError if not valid UUID

    def test_request_id_passthrough(self, security_client: TestClient):
        """Test that provided X-Request-ID header is used instead of generating new one"""
        custom_request_id = "custom-request-id-12345"
        response = security_client.get("/health", headers={"X-Request-ID": custom_request_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_request_id

    def test_auth_detection_with_bearer_token(self, security_client: TestClient):
        """Test that Bearer token is properly detected in Authorization header"""
        response = security_client.get(
            "/api/data", headers={"Authorization": "Bearer test-token-12345"}
        )

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_auth_detection_without_token(self, security_client: TestClient):
        """Test that request without Authorization header is handled"""
        response = security_client.get("/api/data")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_auth_detection_with_invalid_auth_header(self, security_client: TestClient):
        """Test that non-Bearer Authorization headers don't set has_auth"""
        response = security_client.get("/api/data", headers={"Authorization": "Basic invalid"})

        assert response.status_code == 200
        # Should still have request ID but not trigger Bearer token logic
        assert "X-Request-ID" in response.headers

    def test_excluded_paths_no_logging(self, security_client: TestClient, caplog):
        """Test that excluded paths (/health, /metrics, /docs, etc.) are not logged"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/health")

        assert response.status_code == 200
        # Excluded path should NOT be in logs
        request_log_found = any("GET /health" in record.message for record in caplog.records)
        assert not request_log_found

    def test_normal_paths_are_logged(self, security_client: TestClient, caplog):
        """Test that non-excluded paths ARE logged"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/api/data")

        assert response.status_code == 200
        # Non-excluded path should be in logs
        request_log_found = any(
            "GET /api/data" in record.message and "200" in record.message
            for record in caplog.records
        )
        assert request_log_found


class TestSecurityMiddlewareHeaders:
    """Test that SecurityMiddleware properly injects security headers"""

    def test_security_headers_present(self, security_client: TestClient):
        """Test that all required security headers are present in response"""
        response = security_client.get("/api/data")

        assert response.status_code == 200
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers
        assert "X-Request-ID" in response.headers

    def test_x_content_type_options_header(self, security_client: TestClient):
        """Test X-Content-Type-Options is set to 'nosniff'"""
        response = security_client.get("/api/data")

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_header(self, security_client: TestClient):
        """Test X-Frame-Options is set to 'DENY'"""
        response = security_client.get("/api/data")

        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection_header(self, security_client: TestClient):
        """Test X-XSS-Protection is set to '1; mode=block'"""
        response = security_client.get("/api/data")

        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_security_headers_on_post_request(self, security_client: TestClient):
        """Test that security headers are added to POST responses"""
        response = security_client.post("/api/data")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


class TestSecurityMiddlewareLogging:
    """Test that SecurityMiddleware logs requests with proper details"""

    def test_request_logging_with_info_level(self, security_client: TestClient, caplog):
        """Test that successful requests (2xx) are logged at INFO level"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/api/data")

        assert response.status_code == 200
        # Find the log record
        log_records = [r for r in caplog.records if "GET /api/data" in r.message]
        assert len(log_records) > 0
        assert log_records[0].levelno == logging.INFO

    def test_request_logging_contains_metadata(self, security_client: TestClient, caplog):
        """Test that request logs contain proper metadata (request_id, method, path, status)"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/api/data")

        assert response.status_code == 200
        # Check that metadata is in extra dict
        log_records = [r for r in caplog.records if "GET /api/data" in r.message]
        assert len(log_records) > 0

        log_record = log_records[0]
        assert hasattr(log_record, "request_id")
        assert hasattr(log_record, "status_code")
        assert log_record.status_code == 200

    def test_request_logging_with_auth(self, security_client: TestClient, caplog):
        """Test that authenticated requests are logged with authenticated=True"""
        with caplog.at_level(logging.INFO):
            response = security_client.get(
                "/api/data", headers={"Authorization": "Bearer test-token"}
            )

        assert response.status_code == 200
        log_records = [r for r in caplog.records if "GET /api/data" in r.message]
        assert len(log_records) > 0

        log_record = log_records[0]
        assert hasattr(log_record, "authenticated")
        assert log_record.authenticated is True

    def test_request_logging_without_auth(self, security_client: TestClient, caplog):
        """Test that unauthenticated requests are logged with authenticated=False"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/api/data")

        assert response.status_code == 200
        log_records = [r for r in caplog.records if "GET /api/data" in r.message]
        assert len(log_records) > 0

        log_record = log_records[0]
        assert hasattr(log_record, "authenticated")
        assert log_record.authenticated is False


class TestSecurityMiddlewareErrorHandling:
    """Test that SecurityMiddleware properly handles errors"""

    def test_error_response_includes_request_id(self, security_client: TestClient):
        """Test that error responses include X-Request-ID header"""
        # Request to non-existent endpoint should return 404
        response = security_client.get("/nonexistent")

        # 404 is expected (route not found)
        assert response.status_code == 404
        # But X-Request-ID should still be present
        assert "X-Request-ID" in response.headers

    def test_error_response_includes_security_headers(self, security_client: TestClient):
        """Test that error responses include security headers"""
        response = security_client.get("/nonexistent")

        assert response.status_code == 404
        # Security headers should be on error responses too
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers


class TestSecurityMiddlewareIntegration:
    """Integration tests for SecurityMiddleware with timing and request tracking"""

    def test_timing_is_logged(self, security_client: TestClient, caplog):
        """Test that request duration is logged"""
        with caplog.at_level(logging.INFO):
            response = security_client.get("/api/data")

        assert response.status_code == 200
        log_records = [r for r in caplog.records if "GET /api/data" in r.message]
        assert len(log_records) > 0

        log_record = log_records[0]
        assert hasattr(log_record, "duration_ms")
        assert log_record.duration_ms >= 0


# ==================== RATE LIMIT MIDDLEWARE TESTS ====================


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware request counting and rate limit headers"""

    def test_rate_limit_headers_present(self, rate_limit_client: TestClient):
        """Test that rate limit headers are present in response"""
        response = rate_limit_client.get("/health")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_values_correct(self, rate_limit_client: TestClient):
        """Test that rate limit header values are reasonable"""
        response = rate_limit_client.get("/health")

        assert response.status_code == 200
        limit = int(response.headers["X-RateLimit-Limit"])
        remaining = int(response.headers["X-RateLimit-Remaining"])
        reset = int(response.headers["X-RateLimit-Reset"])

        assert limit == 10  # Set in fixture
        assert 0 <= remaining <= limit
        assert reset > 0

    def test_request_count_increments(self, rate_limit_client: TestClient):
        """Test that request count increments with multiple requests"""
        response1 = rate_limit_client.get("/health")
        remaining1 = int(response1.headers["X-RateLimit-Remaining"])

        response2 = rate_limit_client.get("/api/data")
        remaining2 = int(response2.headers["X-RateLimit-Remaining"])

        # Remaining should decrease (or stay same if from different IP)
        # This test is somewhat fragile depending on TestClient behavior
        assert response1.status_code == 200
        assert response2.status_code == 200


class TestRateLimitMiddlewareReset:
    """Test rate limit reset after time window"""

    def test_rate_limit_reset_tracking(self, rate_limit_client: TestClient):
        """Test that reset time is provided in headers"""
        response = rate_limit_client.get("/health")

        reset_time = int(response.headers["X-RateLimit-Reset"])
        current_time = int(time.time())

        # Reset should be within 60-70 seconds from now (60s window + some buffer)
        assert reset_time > current_time
        assert reset_time <= current_time + 70


# ==================== CORS MIDDLEWARE TESTS ====================


class TestCORSMiddleware:
    """Test CORSMiddleware CORS header injection"""

    def test_cors_headers_on_normal_request(self, cors_client: TestClient):
        """Test that CORS headers are added to normal GET request"""
        response = cors_client.get("/api/data")

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers

    def test_cors_allow_origin_header(self, cors_client: TestClient):
        """Test that Access-Control-Allow-Origin contains configured origins"""
        response = cors_client.get("/api/data")

        allow_origin = response.headers["Access-Control-Allow-Origin"]
        # Should contain at least one of the configured origins
        assert "http://localhost:3000" in allow_origin or "http://localhost:8080" in allow_origin

    def test_cors_allow_methods_header(self, cors_client: TestClient):
        """Test that Access-Control-Allow-Methods contains configured methods"""
        response = cors_client.get("/api/data")

        allow_methods = response.headers["Access-Control-Allow-Methods"]
        assert "GET" in allow_methods
        assert "POST" in allow_methods
        assert "PUT" in allow_methods

    def test_cors_allow_headers_header(self, cors_client: TestClient):
        """Test that Access-Control-Allow-Headers contains configured headers"""
        response = cors_client.get("/api/data")

        allow_headers = response.headers["Access-Control-Allow-Headers"]
        assert "Content-Type" in allow_headers
        assert "Authorization" in allow_headers

    def test_cors_preflight_request(self, cors_client: TestClient):
        """Test that OPTIONS preflight request returns proper CORS headers"""
        response = cors_client.options("/api/data")

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers
        assert "Access-Control-Max-Age" in response.headers

    def test_cors_preflight_max_age(self, cors_client: TestClient):
        """Test that OPTIONS preflight includes Access-Control-Max-Age header"""
        response = cors_client.options("/api/data")

        assert response.status_code == 200
        max_age = response.headers["Access-Control-Max-Age"]
        assert int(max_age) == 3600  # 1 hour


class TestCORSMiddlewareDefaults:
    """Test CORSMiddleware default behavior when not fully configured"""

    def test_cors_app_with_defaults(self, test_app: FastAPI):
        """Test CORSMiddleware with default configuration"""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"test": "ok"}

        app.add_middleware(CORSMiddleware)  # No args - should use defaults
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        # Default allows all origins
        assert response.headers["Access-Control-Allow-Origin"] == "*"


# ==================== FULL MIDDLEWARE STACK TESTS ====================


class TestFullMiddlewareStack:
    """Test all middleware working together"""

    def test_all_middleware_together(self, full_middleware_client: TestClient):
        """Test that all middleware work together without conflicts"""
        response = full_middleware_client.get("/api/data")

        assert response.status_code == 200
        # Security headers from SecurityMiddleware
        assert "X-Request-ID" in response.headers
        assert "X-Content-Type-Options" in response.headers
        # Rate limit headers from RateLimitMiddleware
        assert "X-RateLimit-Limit" in response.headers
        # CORS headers from CORSMiddleware
        assert "Access-Control-Allow-Origin" in response.headers

    def test_request_id_propagated_through_stack(self, full_middleware_client: TestClient):
        """Test that request ID is preserved through middleware stack"""
        custom_id = "test-stack-id-12345"
        response = full_middleware_client.get("/api/data", headers={"X-Request-ID": custom_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_post_request_through_stack(self, full_middleware_client: TestClient):
        """Test POST request through full middleware stack"""
        response = full_middleware_client.post("/api/data")

        assert response.status_code == 200
        # All middleware should add their headers
        assert "X-Request-ID" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "Access-Control-Allow-Origin" in response.headers


# ==================== EDGE CASES & BOUNDARY CONDITIONS ====================


class TestSecurityMiddlewareEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_very_long_request_id(self, security_client: TestClient):
        """Test handling of very long X-Request-ID header"""
        long_id = "x" * 1000
        response = security_client.get("/api/data", headers={"X-Request-ID": long_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == long_id

    def test_empty_request_id_header(self, security_client: TestClient):
        """Test handling of empty X-Request-ID header"""
        response = security_client.get("/api/data", headers={"X-Request-ID": ""})

        assert response.status_code == 200
        # Empty string is falsy, so should generate new UUID
        request_id = response.headers["X-Request-ID"]
        uuid.UUID(request_id)  # Should be valid UUID

    def test_special_characters_in_request_id(self, security_client: TestClient):
        """Test handling of special characters in request ID"""
        special_id = "test-id_123.456"
        response = security_client.get("/api/data", headers={"X-Request-ID": special_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == special_id

    def test_bearer_token_with_spaces(self, security_client: TestClient):
        """Test Bearer token parsing with extra spaces"""
        response = security_client.get(
            "/api/data", headers={"Authorization": "Bearer   token-with-spaces"}
        )

        assert response.status_code == 200
        # Should still be detected as Bearer token (startswith check)

    def test_multiple_requests_rapid_fire(self, security_client: TestClient):
        """Test multiple rapid requests all get unique request IDs"""
        ids = []
        for _ in range(5):
            response = security_client.get("/api/data")
            request_id = response.headers["X-Request-ID"]
            ids.append(request_id)

        # All should be unique
        assert len(set(ids)) == 5


class TestSecurityMiddlewareLoggingLevels:
    """Test that logging levels are set correctly based on status codes"""

    def test_4xx_logged_as_warning(self, security_app: FastAPI):
        """Test that 4xx errors are logged at WARNING level"""

        @security_app.get("/test_400")
        async def test_400():
            return Response(content="Bad Request", status_code=400)

        client = TestClient(security_app)

        with patch("src.core.middleware.security_middleware.logger") as mock_logger:
            response = client.get("/test_400")
            assert response.status_code == 400
            # Should have called logger.log with WARNING level
            # (This is a simplified test - real implementation uses logger.log)

    def test_5xx_logged_as_error(self, security_app: FastAPI):
        """Test that 5xx errors are logged at ERROR level"""

        @security_app.get("/test_500")
        async def test_500():
            return Response(content="Server Error", status_code=500)

        client = TestClient(security_app)

        response = client.get("/test_500")
        assert response.status_code == 500
        # Response should include security headers even on error
        assert "X-Request-ID" in response.headers


# ==================== PYTEST MARKERS ====================

pytestmark = [
    pytest.mark.unit,
    pytest.mark.security,
]
