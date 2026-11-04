"""Autonomous domain dependencies (ADR-033 Laag 1)."""

from src.core.database.redis import get_redis_client as get_redis_client

__all__ = ["get_redis_client"]
