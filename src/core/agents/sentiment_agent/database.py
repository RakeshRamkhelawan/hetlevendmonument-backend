"""
Sentiment Agent Database - Uses centralized database manager
Eliminates duplicate engine initialization
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

# NOTE: ADR-034 Cat B Stap 3D -- subdomain database-module, feitelijk adapter.
# import-linter Contract 7 ignore_imports gedocumenteerd. Backlog: SP-AGT-005.
from src.core.database.database import db_manager

logger = logging.getLogger(__name__)


async def initialize_database() -> bool:
    """
    DEPRECATED: Use centralized database manager
    Maintained for backward compatibility
    """
    logger.warning("Sentiment agent database initialization deprecated - using centralized manager")
    return await db_manager.initialize()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session using centralized database manager
    """
    async with db_manager.get_session() as session:
        yield session


async def close_database() -> None:
    """
    DEPRECATED: Use centralized database manager
    Maintained for backward compatibility
    """
    logger.warning("Sentiment agent database close deprecated - using centralized manager")
    await db_manager.close()
