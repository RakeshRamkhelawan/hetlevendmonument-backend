"""
tests/fixtures/mocks.py - External Service Mocks

Provides mock fixtures for external services to ensure tests are isolated
and don't make real network calls.

MOCKED SERVICES:
- Redis (caching)
- Email service (SMTP)
- LLM/Gemini (AI responses)
- HTTP clients (external APIs)

KEY PRINCIPLES:
1. All external calls are mocked by default
2. Mocks capture calls for assertions
3. Mocks return predictable responses
4. Easy to customize mock behavior per test

Created: 2025-12-06
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# REDIS MOCK
# ============================================================================


class MockRedisClient:
    """In-memory Redis mock with full API compatibility."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._ttls: Dict[str, int] = {}
        self.call_log: List[Dict[str, Any]] = []

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        self.call_log.append({"method": "get", "key": key})
        return self._cache.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        """Set value in cache with optional TTL."""
        self.call_log.append({"method": "set", "key": key, "value": value, "ex": ex})
        self._cache[key] = value
        if ex:
            self._ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        self.call_log.append({"method": "delete", "key": key})
        if key in self._cache:
            del self._cache[key]
            return 1
        return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return key in self._cache

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on existing key."""
        if key in self._cache:
            self._ttls[key] = seconds
            return True
        return False

    async def incr(self, key: str) -> int:
        """Increment integer value."""
        current = int(self._cache.get(key, 0))
        self._cache[key] = str(current + 1)
        return current + 1

    async def flushdb(self):
        """Clear all data."""
        self._cache.clear()
        self._ttls.clear()

    # Expose cache for assertions
    @property
    def cache(self) -> Dict[str, Any]:
        return self._cache


@pytest.fixture
def mock_redis_client():
    """
    Provide mock Redis client.

    Usage:
        def test_caching(mock_redis_client):
            await mock_redis_client.set("key", "value")
            assert mock_redis_client.cache["key"] == "value"
    """
    return MockRedisClient()


@pytest.fixture
def mock_redis(mock_redis_client):
    """Alias for backward compatibility."""
    return mock_redis_client


# ============================================================================
# ============================================================================
# EMAIL SERVICE MOCK
# ============================================================================


class MockEmailService:
    """Mock email service that captures sent emails."""

    def __init__(self):
        self.sent_emails: List[Dict[str, Any]] = []
        self.should_fail: bool = False
        self.fail_message: str = "Email send failed"

    async def send_email(
        self, to: str, subject: str, body: str, html: Optional[str] = None, **kwargs
    ) -> bool:
        """Send email (mock)."""
        if self.should_fail:
            raise Exception(self.fail_message)

        self.sent_emails.append(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "html": html,
                **kwargs,
            }
        )
        return True

    async def send_welcome_email(self, to: str, name: str = "User") -> bool:
        """Send welcome email."""
        return await self.send_email(
            to=to,
            subject="Welcome to SanskritiSetu",
            body=f"Welcome {name}!",
        )

    async def send_password_reset(self, to: str, reset_link: str) -> bool:
        """Send password reset email."""
        return await self.send_email(
            to=to,
            subject="Password Reset Request",
            body=f"Reset your password: {reset_link}",
        )

    async def send_verification_email(self, to: str, verification_code: str) -> bool:
        """Send email verification."""
        return await self.send_email(
            to=to,
            subject="Verify Your Email",
            body=f"Your verification code: {verification_code}",
        )

    def set_fail_mode(self, should_fail: bool, message: str = "Email send failed"):
        """Configure mock to fail on send."""
        self.should_fail = should_fail
        self.fail_message = message

    def get_last_email(self) -> Optional[Dict[str, Any]]:
        """Get the most recently sent email."""
        return self.sent_emails[-1] if self.sent_emails else None

    def clear(self):
        """Clear all sent emails."""
        self.sent_emails.clear()


@pytest.fixture
def mock_email_service():
    """Provide mock email service."""
    return MockEmailService()


@pytest.fixture
def mock_email(mock_email_service):
    """Alias for backward compatibility."""
    return mock_email_service


# ============================================================================
# LLM/GEMINI MOCK
# ============================================================================


class MockLLMClient:
    """Mock LLM client for AI response testing."""

    def __init__(self):
        self.responses: List[str] = ["Mocked LLM response for testing"]
        self.response_index: int = 0
        self.call_log: List[Dict[str, Any]] = []
        self.should_fail: bool = False

    async def generate_content(self, prompt: str, **kwargs) -> MagicMock:
        """Generate content (mock)."""
        self.call_log.append({"method": "generate_content", "prompt": prompt, **kwargs})

        if self.should_fail:
            raise Exception("LLM generation failed")

        response_text = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        # Return mock response object matching Gemini API
        mock_response = MagicMock()
        mock_response.text = response_text
        mock_response.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text=response_text)]))
        ]
        return mock_response

    async def generate_content_async(self, prompt: str, **kwargs):
        """Async generate content."""
        return await self.generate_content(prompt, **kwargs)

    def set_responses(self, responses: List[str]):
        """Set custom responses for testing."""
        self.responses = responses
        self.response_index = 0

    def set_fail_mode(self, should_fail: bool):
        """Configure mock to fail."""
        self.should_fail = should_fail


@pytest.fixture
def mock_gemini_client():
    """Provide mock Gemini/LLM client."""
    return MockLLMClient()


@pytest.fixture
def mock_llm(mock_gemini_client):
    """Alias for backward compatibility."""
    return mock_gemini_client


# ============================================================================
# HTTP CLIENT MOCK
# ============================================================================


class MockHTTPClient:
    """Mock HTTP client for external API calls."""

    def __init__(self):
        self.responses: Dict[str, Dict[str, Any]] = {}  # URL -> response
        self.call_log: List[Dict[str, Any]] = []
        self.default_response = {"status": 200, "json": {}}

    async def get(self, url: str, **kwargs) -> MagicMock:
        """Mock GET request."""
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> MagicMock:
        """Mock POST request."""
        return await self._request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> MagicMock:
        """Mock PUT request."""
        return await self._request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> MagicMock:
        """Mock DELETE request."""
        return await self._request("DELETE", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> MagicMock:
        """Execute mock request."""
        self.call_log.append({"method": method, "url": url, **kwargs})

        response_data = self.responses.get(url, self.default_response)

        mock_response = MagicMock()
        mock_response.status_code = response_data.get("status", 200)
        mock_response.json.return_value = response_data.get("json", {})
        mock_response.text = response_data.get("text", "")
        mock_response.raise_for_status = MagicMock()

        if response_data.get("status", 200) >= 400:
            mock_response.raise_for_status.side_effect = Exception(
                f"HTTP {response_data['status']}"
            )

        return mock_response

    def set_response(self, url: str, status: int = 200, json: Dict = None, text: str = ""):
        """Configure response for specific URL."""
        self.responses[url] = {"status": status, "json": json or {}, "text": text}


@pytest.fixture
def mock_http_client():
    """Provide mock HTTP client."""
    return MockHTTPClient()


# ============================================================================
# AUTO-PATCH FIXTURES
# ============================================================================


@pytest.fixture(autouse=False)
def patch_external_services(
    mock_redis_client,
    mock_email_service,
    mock_gemini_client,
):
    """
    Patch all external services automatically.

    Usage:
        @pytest.mark.usefixtures("patch_external_services")
        class TestMyFeature:
            def test_something(self):
                # All external services are mocked
                pass
    """
    with (
        patch("src.core.cache.redis_client", mock_redis_client),
        patch("src.core.email.email_service", mock_email_service),
        patch("src.core.llm.gemini_client", mock_gemini_client),
    ):
        yield


@pytest.fixture
def mock_datetime():
    """
    Mock datetime for time-sensitive tests.

    Usage:
        def test_expiry(mock_datetime):
            mock_datetime.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
    """
    with patch("datetime.datetime") as mock_dt:
        from datetime import datetime

        mock_dt.now.return_value = datetime(2025, 12, 6, 12, 0, 0)
        mock_dt.utcnow.return_value = datetime(2025, 12, 6, 12, 0, 0)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        yield mock_dt
