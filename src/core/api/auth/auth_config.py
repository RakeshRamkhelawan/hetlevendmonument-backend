"""Shared auth rate limiter (used by all auth sub-routers)."""

from src.core.middleware.rate_limiter import get_limiter

auth_limiter = get_limiter(service_name="auth")
