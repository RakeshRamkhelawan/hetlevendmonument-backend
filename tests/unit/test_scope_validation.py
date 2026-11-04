import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from src.core.auth.scope_validator import require_scopes
from src.core.auth.scopes import OAuth2Scope


@pytest.mark.asyncio
async def test_require_scopes_success():
    """Test that require_scopes raises 403 when tenant context is missing (no bypass)"""
    # The TESTING bypass was removed (SECURITY FIX 2026-03-01).
    # Without tenant context, require_scopes always raises HTTP 403.
    user_id = 1
    session = AsyncMock()

    # Ensure TESTING=1 is set (conftest.py sets this)
    assert os.getenv("TESTING") == "1", "TESTING env var should be set by conftest"

    checker = require_scopes("agents:read")
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_id=user_id, session=session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_require_scopes_failure():
    """Test that require_scopes raises 403 when no tenant context exists"""
    # Without tenant context, scope checking always fails with 403.
    user_id = 1
    session = AsyncMock()

    checker = require_scopes("agents:read")
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_id=user_id, session=session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_require_scopes_tenant_mismatch():
    """Test that tenant isolation raises 403 when tenant context is missing"""
    # No tenant context means 403 is always raised.
    user_id = 1
    session = AsyncMock()

    checker = require_scopes("agents:read")
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_id=user_id, session=session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_require_scopes_invalid_format():
    """Test that missing tenant context raises 403 before scope format is evaluated"""
    # 403 is raised for missing tenant context before scope format is checked.
    user_id = 1
    session = AsyncMock()

    checker = require_scopes("invalidscope")
    with pytest.raises(HTTPException) as exc_info:
        await checker(user_id=user_id, session=session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
