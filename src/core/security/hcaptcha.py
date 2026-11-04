"""hCaptcha bot-protection service (ADR-029 P1-3)."""

from __future__ import annotations

import logging
import os


import httpx

from src.core.exceptions.foundation import CaptchaFailedError

logger = logging.getLogger(__name__)

# Standard hCaptcha dummy test keys from hcaptcha documentation
_HCAPTCHA_TEST_TOKENS = {
    "10000000-aaaa-bbbb-cccc-000000000001",
    "dummy-hcaptcha-token",
    "test-hcaptcha-token",
    "test-token",
}

_HCAPTCHA_VERIFY_URL = "https://api.hcaptcha.com/siteverify"


async def verify_hcaptcha(token: str | None, remote_ip: str | None = None) -> bool:
    """Verify an hCaptcha token against the hCaptcha siteverify API.

    In development/testing environments or when HCAPTCHA_SECRET_KEY is not configured,
    verification gracefully passes unless an invalid token is explicitly supplied.
    """
    secret_key = os.getenv("HCAPTCHA_SECRET_KEY")
    env = os.getenv("ENVIRONMENT", "").lower()
    is_testing = os.getenv("TESTING", "").lower() in ("1", "true", "yes") or env in (
        "test",
        "testing",
    )
    is_production = env in ("production", "prod") and not is_testing

    # Production: Fail closed on missing/dummy secret key, missing token, or test token
    if is_production:
        if not secret_key or secret_key.startswith("0x00000000"):
            logger.error(
                "hCaptcha verification failed: HCAPTCHA_SECRET_KEY is missing or dummy in production"
            )
            return False
        if not token:
            logger.warning("hCaptcha verification failed: missing token in production")
            return False
        if token in _HCAPTCHA_TEST_TOKENS:
            logger.warning("hCaptcha verification failed: test token rejected in production")
            return False

    # Development / Testing bypass:
    if not secret_key or secret_key.startswith("0x00000000") or is_testing:
        if token in _HCAPTCHA_TEST_TOKENS or not token:
            return True
        if not secret_key or secret_key.startswith("0x00000000"):
            return True

    if not token:
        logger.warning("hCaptcha verification failed: missing token")
        return False

    if token in _HCAPTCHA_TEST_TOKENS:
        return True

    try:
        data = {
            "secret": secret_key,
            "response": token,
        }
        if remote_ip:
            data["remoteip"] = remote_ip

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(_HCAPTCHA_VERIFY_URL, data=data)
            resp.raise_for_status()
            res_json: dict[str, object] = resp.json()
            success = bool(res_json.get("success", False))
            if not success:
                logger.warning(
                    "hCaptcha verification rejected: error-codes=%s",
                    res_json.get("error-codes", []),
                )
            return success
    except Exception as exc:
        logger.error("hCaptcha verification API error: %s", exc)
        return False


async def require_hcaptcha(token: str | None, remote_ip: str | None = None) -> None:
    """Helper that calls verify_hcaptcha and raises CaptchaFailedError on failure."""
    is_valid = await verify_hcaptcha(token, remote_ip)
    if not is_valid:
        raise CaptchaFailedError()
