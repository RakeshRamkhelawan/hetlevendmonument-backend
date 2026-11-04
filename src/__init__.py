# SanskritiSetu Backend AI Package
# Note: Workers module is loaded lazily to prevent import errors during Docker build
# when REDIS_URL environment variable is not yet available.
from typing import Any


def get_workers() -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Lazy import workers module.

    Prevents import errors when REDIS_URL is not set (e.g., during Docker build).

    Returns:
        module: The workers module
    """
    from . import workers

    return workers


__all__ = ["get_workers"]
