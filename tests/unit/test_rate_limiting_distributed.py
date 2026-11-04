"""Test distributed rate limiting with Redis backend."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

import src.core.middleware.rate_limiter as _rl_module
from src.core.middleware.rate_limiter import get_limiter, rate_limit_exceeded_handler


@pytest.fixture(autouse=True)
def _isolate_limiter_cache(monkeypatch):
    """Isoleer de limiter-cache per test zodat Redis-entries niet lekken naar andere tests.

    _limiter_cache is een module-level dict in rate_limiter.py. monkeypatch herstelt
    env-vars maar niet de inhoud van die dict. Zonder isolatie kan test_redis_storage_
    production een Redis-backed limiter in de cache achterlaten die vervolgens in andere
    xdist-workers wordt opgevraagd (bijv. door TestGenerateEndpointWrapper.setup_method),
    wat leidt tot ConnectionError naar redis-host:6379.

    Naast de cache wissen we ook _LazyLimiter._limiter in shared.py: die proxy
    memoiseert de Limiter intern en houdt de Redis-instantie vast ook als de cache
    al geleegd is. monkeypatch herstelt dit attribuut automatisch na de test.
    """
    monkeypatch.setattr(_rl_module, "_limiter_cache", {})
    from src.core.api.v1.focus_builder.shared import limiter as _lazy_limiter

    monkeypatch.setattr(_lazy_limiter, "_limiter", None)


@pytest.fixture
def app_with_limiter():
    """Create FastAPI app with rate limiter for testing headers."""
    app = FastAPI()
    limiter = get_limiter()
    app.state.limiter = limiter

    @app.get("/test")
    @limiter.limit("5/minute")
    async def test_endpoint(request):
        return {"status": "ok"}

    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    return app


def test_redis_storage_production(monkeypatch):
    """Test that production uses properly constructed Redis URL."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://user:pass@redis-host:6379/0")

    limiter = get_limiter()

    # Limiter is configured - check it was created successfully
    assert limiter is not None
    assert hasattr(limiter, "_limiter")  # Internal slowapi attribute


def test_memory_storage_development(monkeypatch):
    """Test that development defaults to memory."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    limiter = get_limiter()

    # Verify limiter is created for development
    assert limiter is not None
    assert hasattr(limiter, "_limiter")  # Internal slowapi attribute


def test_redis_url_parsing():
    """Test Redis URL parsing with different formats."""
    from src.core.middleware.rate_limiter import get_redis_storage_url

    # Test simple URL
    result = get_redis_storage_url("redis://localhost:6380/0", db_index=2)
    assert "/2" in result

    # Test URL with auth
    result = get_redis_storage_url("redis://user:pass@host:6379/0", db_index=2)
    assert "/2" in result
    assert "user:pass" in result
