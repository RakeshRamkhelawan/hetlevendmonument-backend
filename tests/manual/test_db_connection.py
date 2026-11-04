"""Test database connectivity from backend container"""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine


async def test_db():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:LocalProdPassword123!@local-prod-postgres:5432/sanskritisetu"
    )
    async with engine.connect() as conn:
        from sqlalchemy import text

        result = await conn.execute(text("SELECT COUNT(*) FROM users"))
        count = result.scalar()
        print(f"✅ Database connection OK - Users count: {count}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_db())
