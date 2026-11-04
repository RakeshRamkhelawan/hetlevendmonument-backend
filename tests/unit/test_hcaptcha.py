"""Unit tests for hCaptcha bot protection service (ADR-029 P1-3)."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from src.core.security.hcaptcha import verify_hcaptcha, require_hcaptcha
from src.core.exceptions.foundation import CaptchaFailedError


@pytest.mark.asyncio
async def test_hcaptcha_test_token_success():
    """Known test tokens always pass."""
    assert await verify_hcaptcha("10000000-aaaa-bbbb-cccc-000000000001") is True
    assert await verify_hcaptcha("dummy-hcaptcha-token") is True


@pytest.mark.asyncio
async def test_hcaptcha_missing_token_when_secret_set(monkeypatch):
    """Missing token fails when secret is configured and not in test bypass."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "real-secret-key-12345")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert await verify_hcaptcha(None) is False
    assert await verify_hcaptcha("") is False


@pytest.mark.asyncio
async def test_hcaptcha_api_verification_success(monkeypatch):
    """Successful API response returns True."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "real-secret-key-12345")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.json.return_value = {"success": True}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        assert await verify_hcaptcha("some-user-token", remote_ip="1.2.3.4") is True


@pytest.mark.asyncio
async def test_hcaptcha_api_verification_failure(monkeypatch):
    """Unsuccessful API response returns False."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "real-secret-key-12345")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        assert await verify_hcaptcha("bad-token", remote_ip="1.2.3.4") is False


@pytest.mark.asyncio
async def test_require_hcaptcha_raises_exception(monkeypatch):
    """require_hcaptcha raises CaptchaFailedError on failure."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "real-secret-key-12345")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(CaptchaFailedError) as exc_info:
        await require_hcaptcha(None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "CAPTCHA_FAILED"


@pytest.mark.asyncio
async def test_hcaptcha_production_fails_closed_when_secret_missing(monkeypatch):
    """In production, missing secret key must fail closed (return False)."""
    monkeypatch.delenv("HCAPTCHA_SECRET_KEY", raising=False)
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert await verify_hcaptcha("any-token") is False
    assert await verify_hcaptcha(None) is False


@pytest.mark.asyncio
async def test_hcaptcha_production_fails_closed_when_secret_is_dummy(monkeypatch):
    """In production, dummy secret key (0x000...) must fail closed."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "0x0000000000000000000000000000000000000000")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert await verify_hcaptcha("any-token") is False


@pytest.mark.asyncio
async def test_hcaptcha_production_rejects_test_token(monkeypatch):
    """In production, dummy test tokens are not allowed."""
    monkeypatch.setenv("HCAPTCHA_SECRET_KEY", "real-secret-key-12345")
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert await verify_hcaptcha("10000000-aaaa-bbbb-cccc-000000000001") is False
