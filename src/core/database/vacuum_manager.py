"""
SD-6.1: Vacuum Strategy for PostgreSQL
Configures and manages PostgreSQL vacuum operations.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NotRequired, TypedDict, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)


@dataclass
class TableStats:
    """Statistics for a database table."""

    table_name: str
    dead_tuples: int
    live_tuples: int
    last_vacuum: datetime | None
    last_autovacuum: datetime | None
    vacuum_needed: bool


class VacuumResult(TypedDict):
    """Result of a vacuum operation."""

    status: str
    table: str
    full: bool
    analyze: bool
    duration_seconds: float
    error: NotRequired[str]


class AutovacuumSetting(TypedDict):
    """Single autovacuum setting from pg_settings."""

    value: str
    unit: str | None


class BloatRow(TypedDict):
    """One row from the bloat report query."""

    schemaname: str
    table_name: str
    total_size: str
    dead_tuples: int
    live_tuples: int
    bloat_ratio: float


class VacuumManager:
    """
    SD-6.1: PostgreSQL vacuum management.

    Features:
    - Analyze table bloat
    - Run manual vacuum
    - Configure autovacuum settings
    - Monitor vacuum status
    """

    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url)

    async def get_table_stats(self) -> list[TableStats]:
        """Get vacuum-related statistics for all tables."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        schemaname || '.' || relname as table_name,
                        n_dead_tup as dead_tuples,
                        n_live_tup as live_tuples,
                        last_vacuum,
                        last_autovacuum,
                        CASE
                            WHEN n_dead_tup > n_live_tup * 0.2 THEN true
                            ELSE false
                        END as vacuum_needed
                    FROM pg_stat_user_tables
                    ORDER BY n_dead_tup DESC
                """
                )
            )

            stats: list[TableStats] = []
            for row in result.fetchall():
                stats.append(
                    TableStats(
                        table_name=row.table_name,
                        dead_tuples=row.dead_tuples,
                        live_tuples=row.live_tuples,
                        last_vacuum=row.last_vacuum,
                        last_autovacuum=row.last_autovacuum,
                        vacuum_needed=row.vacuum_needed,
                    )
                )

            return stats

    async def vacuum_table(
        self, table_name: str, full: bool = False, analyze: bool = True
    ) -> VacuumResult:
        """
        Run VACUUM on a specific table.

        Args:
            table_name: Name of the table to vacuum
            full: Whether to do VACUUM FULL (locks table)
            analyze: Whether to run ANALYZE after vacuum

        Returns:
            Result dict with status and timing
        """
        start_time = datetime.now(timezone.utc)

        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?", table_name):
            logger.error("invalid table name for vacuum: %s", table_name)
            return VacuumResult(
                status="error",
                table=table_name,
                full=full,
                analyze=analyze,
                duration_seconds=0.0,
                error="invalid table name",
            )

        async with self.engine.connect() as conn:
            # Build vacuum command
            cmd = "VACUUM"
            if full:
                cmd += " FULL"
            if analyze:
                cmd += " ANALYZE"
            cmd += f" {table_name}"

            try:
                await conn.execute(text(cmd))
                await conn.commit()

                duration = (datetime.now(timezone.utc) - start_time).total_seconds()

                logger.info("Vacuum completed on %s in %.2fs", table_name, duration)

                return VacuumResult(
                    status="success",
                    table=table_name,
                    full=full,
                    analyze=analyze,
                    duration_seconds=duration,
                )

            except Exception as e:
                logger.error("Vacuum failed on %s: %s", table_name, e)
                return VacuumResult(
                    status="error",
                    table=table_name,
                    full=full,
                    analyze=analyze,
                    duration_seconds=0.0,
                    error=str(e),
                )

    async def vacuum_all_tables(self, analyze: bool = True) -> list[VacuumResult]:
        """Vacuum all user tables."""
        stats = await self.get_table_stats()
        results: list[VacuumResult] = []
        for stat in stats:
            if stat.vacuum_needed:
                result = await self.vacuum_table(stat.table_name, analyze=analyze)
                results.append(result)

        return results

    async def get_autovacuum_settings(self) -> dict[str, AutovacuumSetting]:
        """Get current autovacuum settings."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                text(
                    """
                    SELECT name, setting, unit
                    FROM pg_settings
                    WHERE name LIKE 'autovacuum%'
                    ORDER BY name
                """
                )
            )

            settings: dict[str, AutovacuumSetting] = {}
            for row in result.fetchall():
                settings[row.name] = {"value": row.setting, "unit": row.unit}

            return settings

    async def get_bloat_report(self) -> list[BloatRow]:
        """Get table bloat estimates."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        schemaname,
                        relname as table_name,
                        pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                        n_dead_tup as dead_tuples,
                        n_live_tup as live_tuples,
                        CASE
                            WHEN n_live_tup > 0
                            THEN round(100.0 * n_dead_tup / n_live_tup, 2)
                            ELSE 0
                        END as bloat_ratio
                    FROM pg_stat_user_tables
                    WHERE n_dead_tup > 100
                    ORDER BY n_dead_tup DESC
                    LIMIT 20
                """
                )
            )

            return cast(list[BloatRow], [dict(row._mapping) for row in result.fetchall()])


async def run_scheduled_vacuum() -> list[VacuumResult]:
    """Run vacuum as a scheduled job."""
    import os

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set")
        return []

    manager = VacuumManager(db_url)

    logger.info("Starting scheduled vacuum...")

    # Get tables that need vacuum
    stats = await manager.get_table_stats()
    tables_needing_vacuum = [s for s in stats if s.vacuum_needed]

    logger.info("Found %d tables needing vacuum", len(tables_needing_vacuum))

    # Run vacuum
    results = await manager.vacuum_all_tables()

    success_count = sum(1 for r in results if r.get("status") == "success")
    logger.info("Vacuum completed: %d/%d tables", success_count, len(results))

    return results


if __name__ == "__main__":
    asyncio.run(run_scheduled_vacuum())
