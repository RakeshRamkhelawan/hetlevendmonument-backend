import base64
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.core.auth.dependencies import get_current_user_id
from src.core.config.unified_config import config


def make_expired_token() -> str:
    import jwt as _jwt

    payload = {"sub": "1", "exp": int(time.time()) - 60}
    return _jwt.encode(payload, config.jwt_secret_key, algorithm="HS256")


# --- REGRESSION TESTS (document existing guarantee, should already pass) ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_paths_reject_expired_token():
    """All verification paths must reject expired tokens."""
    expired = make_expired_token()
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token=expired, session=db)
    assert exc_info.value.status_code == 401


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_paths_reject_alg_none_attack():
    """The alg=none attack must be rejected by all paths."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(
        b"="
    )
    payload_b = base64.urlsafe_b64encode(
        json.dumps({"sub": "1", "exp": int(time.time()) + 3600}).encode()
    ).rstrip(b"=")
    none_token = f"{header.decode()}.{payload_b.decode()}."
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token=none_token, session=db)
    assert exc_info.value.status_code == 401


# --- RED-FIRST TDD TEST (may FAIL before the fix, must PASS after) ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_token_returns_401_not_500():
    """A wrong-signature token must produce 401, never 500.

    The three-path fallback can cause a 500 if any intermediate path raises
    an unhandled exception instead of returning None cleanly.
    """
    import jwt as _jwt

    wrong_secret_token = _jwt.encode(
        {"sub": "1", "exp": int(time.time()) + 3600},
        "completely-wrong-secret-that-is-at-least-32-chars-long",
        algorithm="HS256",
    )
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token=wrong_secret_token, session=db)
    # Must be 401, not 500 (500 = unhandled exception leaked through)
    assert exc_info.value.status_code == 401
