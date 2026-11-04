"""
Utility for non-critical async operations that must never block the main request path.

Non-critical operations (audit logs, metric emissions, notification sends) should
NEVER cause a 500 when they fail -- the primary operation has already succeeded.

Usage:
    from src.core.utils.best_effort import best_effort

    # Wrap any secondary operation that must not propagate exceptions:
    async with best_effort("consent audit log", db_session=db):
        db.add(audit_entry)
        await db.commit()
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def best_effort(
    operation: str,
    db_session: AsyncSession | None = None,
) -> AsyncGenerator[None, None]:
    """
    Context manager that catches all exceptions from secondary/optional operations.

    On failure:
    - Logs the exception with full traceback (so it is never silently swallowed)
    - Rolls back the DB session if provided (keeps session clean for the caller)
    - Does NOT re-raise (the primary operation is unaffected)

    Args:
        operation: Human-readable name for logging ("consent audit log", etc.)
        db_session: Optional SQLAlchemy AsyncSession to roll back on failure.
    """
    try:
        yield
    except Exception as exc:
        logger.error(
            "[best_effort] %s failed -- %s: %s",
            operation,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        if db_session is not None:
            try:
                await db_session.rollback()
            except Exception as rb_exc:
                logger.warning(
                    "[best_effort] rollback after %s also failed: %s",
                    operation,
                    rb_exc,
                )
