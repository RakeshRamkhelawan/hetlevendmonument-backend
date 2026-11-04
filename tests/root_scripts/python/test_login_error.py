"""Diagnostic test to see login endpoint errors."""

import asyncio
import sys

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from tests.fixtures import api as api_fixtures
from tests.fixtures import auth as auth_fixtures


async def main():
    """Run diagnostic test."""
    # Create fixtures manually
    db_session = await auth_fixtures.db_session()
    test_tenant = await auth_fixtures.test_tenant(db_session)
    test_user = await auth_fixtures.test_user(db_session, test_tenant)
    test_client = await api_fixtures.test_client()

    print(f"Test user email: {test_user['email']}")
    print(f"Test user id: {test_user['id']}")

    # Try login
    response = await test_client.post(
        "/api/v1/auth/login",
        data={"username": test_user["email"], "password": "password"},
    )

    print(f"\nStatus code: {response.status_code}")
    print(f"Response text: {response.text}")
    print(
        f"Response json: {response.json() if response.headers.get('content-type') == 'application/json' else 'Not JSON'}"
    )


if __name__ == "__main__":
    asyncio.run(main())
