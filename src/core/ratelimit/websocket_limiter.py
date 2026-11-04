import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class WebSocketLimiter:
    """
    Simple Token Bucket Rate Limiter for WebSockets.
    In-memory storage (not distributed). Suitable for single-instance deployments.
    """

    def __init__(self, rate_limit: int = 5, time_window: int = 60) -> None:
        """
        Args:
            rate_limit: Max requests allowed in time_window.
            time_window: Window size in seconds.
        """
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.tokens_per_sec = rate_limit / time_window

        # Storage: {user_id: {'tokens': float, 'last_update': float}}
        self.buckets: dict[str, dict[str, float]] = {}

    def check_limit(self, user_id: str) -> bool:
        """
        Check if user is allowed to proceed. Consumes 1 token if allowed.
        Returns: True if allowed, False if limit exceeded.
        """
        now = time.time()

        if user_id not in self.buckets:
            self.buckets[user_id] = {
                "tokens": float(self.rate_limit),
                "last_update": now,
            }

        bucket = self.buckets[user_id]

        # Replenish tokens
        elapsed = now - bucket["last_update"]
        new_tokens = elapsed * self.tokens_per_sec
        bucket["tokens"] = min(self.rate_limit, bucket["tokens"] + new_tokens)
        bucket["last_update"] = now

        # Consume token
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True

        logger.warning(f"Rate limit exceeded for user {user_id}")
        return False

    def cleanup(self) -> None:
        """Remove stale buckets (optional, for memory management)"""
        now = time.time()
        stale_users: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for user_id, bucket in self.buckets.items():
            if (now - bucket["last_update"]) > self.time_window:
                stale_users.append(user_id)

        for uid in stale_users:
            del self.buckets[uid]
