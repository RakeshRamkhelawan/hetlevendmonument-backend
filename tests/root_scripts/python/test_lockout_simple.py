"""Quick test to see actual error from lockout endpoint."""

import asyncio
import os
import sys
from pathlib import Path

# Set testing mode
os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["JWT_SECRET"] = "test-jwt-secret"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def test_lockout():
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.core.database.database import Base, get_async_session
    from src.main import create_app
    from tests.fixtures.auth import UserFactory
    from tests.fixtures.database import async_engine

    # Create test database
    engine = await anext(async_engine())

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Create test user
        factory = UserFactory(session)
        user = await factory.create_user(email="test@example.com", password="password")
        await session.commit()

        # Create app
        app = create_app()

        # Override session
        async def override_session():
            yield session

        app.dependency_overrides[get_async_session] = override_session

        # Make request
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Try bad password
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "wrong"},
            )
            print("\n=== First attempt (wrong password) ===")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")

            # Try correct password
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "password"},
            )
            print("\n=== Second attempt (correct password) ===")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_lockout())
