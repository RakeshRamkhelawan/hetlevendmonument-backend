"""
Authenticated Client Fixtures - Structural Solution
===================================================

PROBLEM: async_client_no_bypass is hardcoded to use test_user_with_token
This breaks workflow tests that use workflow_test_user_with_token

SOLUTION: Flexible authenticated client that accepts ANY auth fixture

USAGE:
------

Option 1 - Use default test user:
    async def test_something(authenticated_async_client):
        response = await authenticated_async_client.post(...)

Option 2 - Use custom auth fixture:
    async def test_workflow(authenticated_async_client, workflow_test_user_with_token):
        # authenticated_async_client automatically uses workflow_test_user_with_token
        response = await authenticated_async_client.post(...)

ARCHITECTURE:
------------

This fixture uses FastAPI's dependency override system properly:
1. Accepts auth data from ANY fixture that provides headers/token
2. Overrides get_current_user_id to return the correct user
3. Overrides database dependencies to use test session
4. Cleans up after itself

Author: Claude Code (Structural Fix #2)
Date: 2025-12-25
Issue: Fixes workflow 401 authentication errors
"""

from typing import Any, AsyncGenerator, Dict, Optional

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def create_auth_overrides(
    app: FastAPI, db_session: AsyncSession, auth_data: Dict[str, Any]
) -> None:
    """
    Create dependency overrides for authenticated testing

    Args:
        app: FastAPI application
        db_session: Test database session
        auth_data: Dict with keys: user_id, tenant_id, token, headers

    This is the CORE logic that all authenticated clients should use
    """
    from src.core.auth.dependencies import get_current_user_id
    from src.core.database.database import get_db

    # Database overrides
    async def override_get_db():
        yield db_session

    # Auth overrides - return the user_id from auth fixture
    async def override_get_current_user_id() -> int:
        return auth_data.get("user_id", 1)

    # Apply overrides
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id


def get_auth_fixture_data(request) -> Optional[Dict[str, Any]]:
    """
    Extract auth data from any available auth fixture

    Searches for common auth fixtures in order of preference:
    1. workflow_test_user_with_token
    2. test_user_with_token
    3. admin_user (for integration tests)

    Returns None if no auth fixture found
    """
    auth_fixture_names = [
        "workflow_test_user_with_token",
        "test_user_with_token",
        "admin_user",
        "normal_user",
    ]

    for fixture_name in auth_fixture_names:
        if fixture_name in request.fixturenames:
            try:
                return request.getfixturevalue(fixture_name)
            except Exception:
                continue

    return None
