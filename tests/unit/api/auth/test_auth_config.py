"""Unit tests for src.core.api.auth.auth_config."""

from slowapi import Limiter

from src.core.api.auth.auth_config import auth_limiter
from src.core.middleware.rate_limiter import _limiter_cache, get_limiter


def test_auth_limiter_instance_and_configuration() -> None:
    """Verify that auth_limiter is a configured slowapi Limiter instance."""
    assert isinstance(auth_limiter, Limiter)
    assert getattr(auth_limiter, "_headers_enabled", False) is True
    assert getattr(auth_limiter, "enabled", True) is True
    assert len(getattr(auth_limiter, "_default_limits", [])) == 1




def test_auth_limiter_is_cached_singleton_for_auth_service() -> None:
    """Verify that auth_limiter is cached under the 'auth' service key."""
    assert "auth" in _limiter_cache
    assert _limiter_cache["auth"] is auth_limiter
    assert get_limiter(service_name="auth") is auth_limiter
