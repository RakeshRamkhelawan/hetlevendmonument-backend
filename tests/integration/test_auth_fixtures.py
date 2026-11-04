"""
PRODUCTION FIXTURES: Real JWT tokens + Real database users

These fixtures create authenticated test users with real JWT tokens.
NO MOCKS - everything is production code.

Usage in tests:
    @pytest.mark.integration
    async def test_something(integration_client, auth_headers, auth_token_and_user):
        # auth_headers is ready to use: {"Authorization": "Bearer <real_jwt>"}
        response = await integration_client.get("/api/endpoint", headers=auth_headers)
        assert response.status_code == 200
"""

from typing import Any, Dict, Tuple

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(scope="function")
async def auth_token_and_user(
    postgres_session: AsyncSession,
) -> Tuple[str, Dict[str, Any]]:
    """
    PRODUCTION FIXTURE: Create real test user in database and generate JWT token

    Returns:
        Tuple[token, user_data]: (JWT Bearer token, user info dict)

    Usage:
        token, user_data = auth_token_and_user
        assert user_data["tenant_id"] == 1
    """
    from sqlalchemy import select

    from src.core.models.rbac_models import Tenant, User
    from src.core.security.security_manager import get_security_manager

    # Ensure default tenant exists
    result = await postgres_session.execute(select(Tenant).where(Tenant.id == 1))
    tenant = result.scalar_one_or_none()
    if not tenant:
        tenant = Tenant(id=1, name="default_tenant")
        postgres_session.add(tenant)
        await postgres_session.flush()

    # Create test user in database
    test_user = User(
        email="test_integration@example.com",
        full_name="Integration Test User",
        hashed_password="dummy",
        tenant_id=1,
        role="user",
    )
    postgres_session.add(test_user)
    await postgres_session.flush()

    # Generate REAL JWT token (not dummy string!)
    security_manager = get_security_manager()
    token = security_manager.generate_token(user_id=f"test_user_{test_user.id}")

    await postgres_session.commit()

    return token, {
        "id": test_user.id,
        "email": test_user.email,
        "tenant_id": test_user.tenant_id,
    }


@pytest_asyncio.fixture(scope="function")
async def auth_headers(auth_token_and_user: Tuple[str, Dict]) -> Dict[str, str]:
    """
    PRODUCTION FIXTURE: Return Authorization headers with Bearer token

    Usage:
        response = await client.get("/api/endpoint", headers=auth_headers)
    """
    token, _ = auth_token_and_user
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def auth_user_data(auth_token_and_user: Tuple[str, Dict]) -> Dict[str, Any]:
    """
    PRODUCTION FIXTURE: Return user data associated with JWT token

    Usage:
        assert auth_user_data["tenant_id"] == 1
    """
    _, user_data = auth_token_and_user
    return user_data
