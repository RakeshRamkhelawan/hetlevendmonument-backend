import asyncio
import os
from typing import AsyncGenerator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Force Testing Environment
os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_integration.db"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-at-least-!!!"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-32-chars-at-least-!!!"

from src.core.api.auth.router import router as auth_router
from src.core.database.database import Base, db_manager


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_engine():
    """Engine met WAL mode en optimalisaties."""
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        # Optimale SQLite instellingen voor concurrentie
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        await conn.execute(text("PRAGMA cache_size=-64000;"))
        await conn.execute(text("PRAGMA foreign_keys=ON;"))

        # Schema aanmaken
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

        # Seed default tenant if needed (assuming ID=1)
        # Hier gaan we ervan uit dat de router/logic tenant_id=1 gebruikt of aanmaakt.
        # Voor nu doen we een basis seed.
        await conn.execute(
            text(
                "INSERT OR IGNORE INTO tenants (id, name, slug, domain, is_active) "
                "VALUES (1, 'Default', 'default', 'default.local', 1)"
            )
        )

    yield engine
    await engine.dispose()

    # Cleanup file
    if os.path.exists("./test_integration.db"):
        try:
            os.remove("./test_integration.db")
            os.remove("./test_integration.db-shm")
            os.remove("./test_integration.db-wal")
        except:
            pass


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Sessie voor tests met expire_on_commit=False."""
    # Inject engine in db_manager
    db_manager.set_engine(db_engine)

    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def auth_test_client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Minimale app voor auth tests."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")

    # Mocking dependencies if necessary, but here we use the real router
    # and we already set the engine in the session fixture which runs before client.

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True
    ) as client:
        yield client
