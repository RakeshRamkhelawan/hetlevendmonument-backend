import time
from unittest.mock import Mock, patch

import pytest

from src.core.ratelimit.websocket_limiter import WebSocketLimiter


class TestWebSocketLimiter:
    def test_allow_request(self):
        # Allow 5 requests per 60 seconds
        limiter = WebSocketLimiter(rate_limit=5, time_window=60)
        user_id = "user_123"

        # Should allow 5
        for _ in range(5):
            assert limiter.check_limit(user_id) is True

        # Should block 6th
        assert limiter.check_limit(user_id) is False

    def test_window_reset(self):
        # Allow 2 requests per 1 second
        limiter = WebSocketLimiter(rate_limit=2, time_window=1)
        user_id = "user_reset"

        assert limiter.check_limit(user_id) is True
        assert limiter.check_limit(user_id) is True
        assert limiter.check_limit(user_id) is False

        # Wait for window reset
        time.sleep(1.1)

        # Should allow again
        assert limiter.check_limit(user_id) is True

    def test_cleanup(self):
        limiter = WebSocketLimiter(rate_limit=1, time_window=1)
        user_id = "user_cleanup"
        limiter.check_limit(user_id)

        # Mock time to pretend window expired
        with patch("time.time", return_value=time.time() + 10):
            limiter.cleanup()
            assert user_id not in limiter.buckets
