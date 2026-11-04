"""
Database Session Context Managers
Provides async context managers for database operations

CRITICAL: Multi-tenant implementation requires this for proper session management
"""

from contextlib import asynccontextmanager, contextmanager
from typing import Any
from collections.abc import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession



@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI-compatible async generator for database sessions.

    Yields an AsyncSession from the shared session factory.
    Properly commits on success, rolls back on error.
    """
    from src.core.database.database import db_manager

    if not db_manager.async_session_maker:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")

    async with db_manager.async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
