"""Direct test of get_user_by_email to isolate the issue"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


async def test_get_user():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:LocalProdPassword123!@local-prod-postgres:5432/sanskritisetu",
        echo=True,
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Import auth service
        from src.core.auth.auth_service import AuthService

        auth_service = AuthService()

        print("🔍 Attempting to fetch user: admin@sanskritisetu.org")
        user = await auth_service.get_user_by_email(session, "admin@sanskritisetu.org")

        if user:
            print(f"✅ User found: {user.email} (tenant_id={user.tenant_id})")
        else:
            print("❌ User NOT found")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_get_user())
