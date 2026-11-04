"""
System Startup Checks.
Verifies critical infrastructure validity before application traffic is accepted.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session

logger = logging.getLogger(__name__)


async def check_database_schema(session: AsyncSession) -> bool:
    """
    Verify that critical tables exist in the database.
    Prevents 'Ghost Table' issues where code expects a table that Alembic skipped.
    """
    CRITICAL_TABLES = [
        "users",
        "tenants",
        "roles",
        "audit_logs",  # The culprit of previous 500 errors
        "workflow_templates",
    ]

    logger.info("Running Startup Schema Check...")

    try:
        # Use raw SQL to check table existence in PostgreSQL
        # (Inspector is synchronous and tricky with AsyncSession, raw SQL is reliable here)
        missing_tables: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for table in CRITICAL_TABLES:
            query = text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table)"
            )
            result = await session.execute(query, {"table": table})
            exists = result.scalar()

            if not exists:
                missing_tables.append(table)

        if missing_tables:
            logger.critical(f"[FAIL] CRITICAL STARTUP ERROR: Missing Database Tables: {missing_tables}")
            logger.critical("Run 'alembic upgrade head' or check for schema drift.")
            return False

        logger.info("[OK] Schema Check Passed: All critical tables present.")
        return True

    except Exception as e:
        logger.error(f"[FAIL] Schema Check Failed to Execute: {e}")
        return False


async def run_startup_checks() -> None:
    """
    Orchestrate all startup checks.
    """
    try:
        # We need a dedicated session for checks
        async with get_db_session() as session:
            if not await check_database_schema(session):
                # In strict mode, we might want to sys.exit(1) here
                logger.error("Startup checks failed! Application may be unstable.")

    except Exception as e:
        logger.error(f"Startup check runner crashed: {e}")
