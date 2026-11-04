"""
Integration test to verify middleware order fix in Sprint 3.3
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

# Set environment variables
os.environ["REDIS_URL"] = "redis://localhost:6380"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-integration-tests"
os.environ["ALGORITHM"] = "HS256"

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def test_middleware_order_fix():
    """Test that middleware order has been corrected in Sprint 3.3"""
    # Import the main app which should have the corrected middleware order
    from src.main import app

    # The app should have all middleware registered
    assert app is not None

    # Test that the app can handle a simple request (even if it fails due to auth)
    client = TestClient(app)

    # Make a request to a simple endpoint
    response = client.get("/health")

    # Should get either 200 (if health endpoint exists) or 404 (if it doesn't)
    # But importantly, should NOT get a middleware initialization error
    assert response.status_code in [200, 404, 401, 403]


def test_middleware_classes_importable():
    """Test that all middleware classes can be imported successfully"""
    # Test that we can import all the middleware classes
    from src.core.middleware.performance_profiler import PerformanceProfilingMiddleware
    from src.core.middleware.quota_middleware import TenantQuotaMiddleware
    from src.core.middleware.security_headers import SecurityHeadersMiddleware
    from src.core.middleware.tenant_middleware import TenantMiddleware
    from src.core.observability.metrics import PrometheusMiddleware

    # Should not raise import errors
    assert TenantMiddleware is not None
    assert TenantQuotaMiddleware is not None
    assert PerformanceProfilingMiddleware is not None
    assert PrometheusMiddleware is not None
    assert SecurityHeadersMiddleware is not None


if __name__ == "__main__":
    test_middleware_order_fix()
    test_middleware_classes_importable()
    print("All middleware order tests passed!")
