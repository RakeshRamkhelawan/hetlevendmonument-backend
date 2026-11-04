"""
Database Health Check Utility

Provides lightweight connectivity checks for health monitoring
(Kubernetes/Docker liveness probes).

Part of SD-1.2 implementation.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def check_db_connection(db_session: AsyncSession) -> bool:
    """
    Verify database connectivity with a lightweight query.

    Args:
        db_session: Async SQLAlchemy session

    Returns:
        True if database is reachable, False otherwise
    """
    try:
        await db_session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_db_stats(db_session: AsyncSession) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get basic database statistics for monitoring.

    Args:
        db_session: Async SQLAlchemy session

    Returns:
        Dictionary with database stats
    """
    try:
        result = await db_session.execute(text("SELECT version()"))
        version = result.scalar()
        return {"connected": True, "version": version}
    except Exception as _health:
        return {"connected": False, "error": str(_health)}
