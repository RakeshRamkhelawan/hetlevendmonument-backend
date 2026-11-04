"""Quick debug test to see what the 500 error is."""

import asyncio
import os
import sys

# Set test mode
os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file:memdb?mode=memory&cache=shared&uri=true"


async def main():
    from tests.fixtures.api import test_client
    from tests.fixtures.auth import test_tenant, test_user
    from tests.fixtures.database import async_engine, db_session

    # Create fixtures
    engine = await async_engine().__anext__()
    session = await db_session(engine).__anext__()
    tenant = await test_tenant(session).__anext__()
    user = await test_user(session, tenant).__anext__()

    print(f"Test user created: {user['email']}")

    # Create client
    async with await test_client(session).__anext__() as client:
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": user["email"], "password": "password"},
        )

        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")

        if response.status_code == 500:
            try:
                print(f"JSON: {response.json()}")
            except:
                pass


if __name__ == "__main__":
    asyncio.run(main())
