#!/usr/bin/env python3
"""
Phase 3 Emergency Rollback Script
Sprint 5 -- Production Safety

Purpose: Quickly disable Phase 3 for all or specific tenants in emergency situations
Usage:
  # Graceful rollback for single tenant
  python scripts/rollback_phase3.py --tenant 123 --graceful

  # Emergency rollback for all tenants
  python scripts/rollback_phase3.py --emergency --all-tenants --force-fail-in-flight

Safety: Requires explicit confirmation for --emergency mode
"""

import argparse
import asyncio
import sys
from datetime import datetime
from typing import List, Optional, Set

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<red><bold>{time:HH:mm:ss}</bold></red> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
)


class Phase3Rollback:
    """Emergency rollback handler for Phase 3"""

    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def graceful_rollback(
        self, tenant_ids: Optional[List[int]] = None, all_tenants: bool = False
    ) -> bool:
        """
        Graceful rollback: Wait for in-flight executions to complete.

        Args:
            tenant_ids: Specific tenants to rollback (None = all)
            all_tenants: If True, rollback all tenants

        Returns:
            True if successful
        """
        logger.info("[U+0001F504] GRACEFUL ROLLBACK: Waiting for in-flight executions...")

        async with self.async_session() as session:
            # Get target tenants
            if all_tenants:
                tenant_ids = await self._get_all_phase3_tenants(session)
            elif not tenant_ids:
                logger.error("No tenants specified. Use --tenant or --all-tenants")
                return False

            logger.info(f"Target: {len(tenant_ids)} tenants")

            # Disable feature flags (prevents NEW executions)
            await self._disable_feature_flags(session, tenant_ids)
            await session.commit()
            logger.success("[OK] Feature flags disabled (no new executions)")

            # Wait for in-flight executions
            max_wait = 300  # 5 minutes
            interval = 5
            elapsed = 0

            while elapsed < max_wait:
                in_flight_count = await self._count_in_flight_executions(session, tenant_ids)

                if in_flight_count == 0:
                    logger.success("[OK] All in-flight executions completed")
                    break

                logger.info(
                    f"[WAIT] Waiting for {in_flight_count} in-flight executions... ({elapsed}s/{max_wait}s)"
                )
                await asyncio.sleep(interval)
                elapsed += interval

            if elapsed >= max_wait:
                logger.warning(
                    f"[WARN]  Timeout: {in_flight_count} executions still running after {max_wait}s"
                )
                logger.warning("Consider using --force-fail-in-flight for emergency")

            # Log rollback
            await self._log_rollback(session, tenant_ids, mode="graceful")
            await session.commit()

        logger.success(f"[OK] Graceful rollback complete for {len(tenant_ids)} tenants")
        return True

    async def emergency_rollback(
        self, tenant_ids: Optional[List[int]] = None, force_fail_in_flight: bool = False
    ) -> bool:
        """
        Emergency rollback: Immediately disable Phase 3, optionally fail in-flight executions.

        Args:
            tenant_ids: Specific tenants (None = all)
            force_fail_in_flight: If True, cancel running executions

        Returns:
            True if successful
        """
        logger.error("[ALERT] EMERGENCY ROLLBACK INITIATED")

        # Confirmation
        response = input("\n[WARN]  This will IMMEDIATELY disable Phase 3. Continue? (yes/no): ")
        if response.lower() != "yes":
            logger.warning("Emergency rollback cancelled")
            return False

        async with self.async_session() as session:
            # Get target tenants
            if not tenant_ids:
                tenant_ids = await self._get_all_phase3_tenants(session)

            logger.error(f"[ALERT] Emergency rollback for {len(tenant_ids)} tenants")

            # Disable feature flags
            await self._disable_feature_flags(session, tenant_ids)
            logger.success("[OK] Feature flags disabled")

            # Force-fail in-flight executions
            if force_fail_in_flight:
                failed_count = await self._force_fail_executions(session, tenant_ids)
                logger.warning(f"[WARN]  Force-failed {failed_count} in-flight executions")

            # Log rollback
            await self._log_rollback(
                session, tenant_ids, mode="emergency", force_failed=force_fail_in_flight
            )
            await session.commit()

        logger.success("[OK] Emergency rollback complete")

        # Display next steps
        logger.info("\n[LIST] NEXT STEPS:")
        logger.info("1. Investigate root cause (check logs, metrics, alerts)")
        logger.info("2. Notify stakeholders (#incidents channel)")
        logger.info("3. Create incident report")
        logger.info("4. Fix underlying issue before re-enabling")

        return True

    async def verify_rollback(self, tenant_ids: Optional[List[int]] = None) -> bool:
        """Verify that Phase 3 is fully disabled"""
        logger.info("[SEARCH] Verifying rollback...")

        async with self.async_session() as session:
            if not tenant_ids:
                tenant_ids = await self._get_all_tenants(session)

            # Check feature flags
            enabled_count = await self._count_enabled_flags(session, tenant_ids)

            # Check in-flight executions
            in_flight_count = await self._count_in_flight_executions(session, tenant_ids)

            # Check recent executions (last 60 seconds)
            recent_count = await self._count_recent_executions(session, tenant_ids, seconds=60)

        logger.info("\n[CHART] Rollback Verification")
        logger.info(f"{'='*40}")
        logger.info(f"Feature flags enabled: {enabled_count}")
        logger.info(f"In-flight executions: {in_flight_count}")
        logger.info(f"Recent executions (60s): {recent_count}")
        logger.info(f"{'='*40}")

        success = enabled_count == 0 and in_flight_count == 0 and recent_count == 0

        if success:
            logger.success("[OK] Rollback verified: Phase 3 fully disabled")
        else:
            logger.error("[FAIL] Rollback incomplete: Phase 3 still partially active")

        return success

    async def _get_all_phase3_tenants(self, session: AsyncSession) -> List[int]:
        """Get all tenants with Phase 3 enabled"""
        result = await session.execute(
            text(
                """
            SELECT DISTINCT tenant_id
            FROM feature_flags
            WHERE feature_name = 'phase3.capability_agents' AND is_enabled = true
        """
            )
        )
        return [row[0] for row in result.fetchall()]

    async def _get_all_tenants(self, session: AsyncSession) -> List[int]:
        """Get all active tenant IDs"""
        result = await session.execute(text("SELECT id FROM tenants WHERE is_active = true"))
        return [row[0] for row in result.fetchall()]

    async def _disable_feature_flags(self, session: AsyncSession, tenant_ids: List[int]):
        """Disable Phase 3 feature flags for tenants"""
        for tenant_id in tenant_ids:
            await session.execute(
                text(
                    """
                UPDATE feature_flags
                SET is_enabled = false, updated_at = NOW()
                WHERE tenant_id = :tenant_id AND feature_name = 'phase3.capability_agents'
            """
                ),
                {"tenant_id": tenant_id},
            )

    async def _count_in_flight_executions(
        self, session: AsyncSession, tenant_ids: List[int]
    ) -> int:
        """Count running executions for Phase 3"""
        result = await session.execute(
            text(
                """
            SELECT COUNT(*)
            FROM procedure_executions
            WHERE tenant_id = ANY(:tenant_ids)
              AND status IN ('running', 'pending')
              AND agent_type IN ('planner', 'retriever', 'executor', 'compliance', 'reviewer')
        """
            ),
            {"tenant_ids": tenant_ids},
        )

        return result.scalar() or 0

    async def _force_fail_executions(self, session: AsyncSession, tenant_ids: List[int]) -> int:
        """Force-fail in-flight executions"""
        result = await session.execute(
            text(
                """
            UPDATE procedure_executions
            SET status = 'failed',
                error_message = 'Emergency rollback: Phase 3 disabled',
                ended_at = NOW()
            WHERE tenant_id = ANY(:tenant_ids)
              AND status IN ('running', 'pending')
              AND agent_type IN ('planner', 'retriever', 'executor', 'compliance', 'reviewer')
        """
            ),
            {"tenant_ids": tenant_ids},
        )

        return result.rowcount

    async def _count_enabled_flags(self, session: AsyncSession, tenant_ids: List[int]) -> int:
        """Count enabled feature flags"""
        result = await session.execute(
            text(
                """
            SELECT COUNT(*)
            FROM feature_flags
            WHERE tenant_id = ANY(:tenant_ids)
              AND feature_name = 'phase3.capability_agents'
              AND is_enabled = true
        """
            ),
            {"tenant_ids": tenant_ids},
        )

        return result.scalar() or 0

    async def _count_recent_executions(
        self, session: AsyncSession, tenant_ids: List[int], seconds: int
    ) -> int:
        """Count executions started in last N seconds"""
        result = await session.execute(
            text(
                """
            SELECT COUNT(*)
            FROM procedure_executions
            WHERE tenant_id = ANY(:tenant_ids)
              AND agent_type IN ('planner', 'retriever', 'executor', 'compliance', 'reviewer')
              AND started_at >= NOW() - INTERVAL ':seconds seconds'
        """
            ),
            {"tenant_ids": tenant_ids, "seconds": seconds},
        )

        return result.scalar() or 0

    async def _log_rollback(
        self,
        session: AsyncSession,
        tenant_ids: List[int],
        mode: str,
        force_failed: bool = False,
    ):
        """Log rollback event"""
        await session.execute(
            text(
                """
            INSERT INTO rollback_events (mode, tenant_ids, tenant_count, force_failed, timestamp)
            VALUES (:mode, :tenant_ids, :tenant_count, :force_failed, NOW())
        """
            ),
            {
                "mode": mode,
                "tenant_ids": tenant_ids[:100],  # First 100 for audit
                "tenant_count": len(tenant_ids),
                "force_failed": force_failed,
            },
        )


async def main():
    parser = argparse.ArgumentParser(description="Phase 3 emergency rollback")
    parser.add_argument(
        "--tenant",
        type=int,
        action="append",
        dest="tenant_ids",
        help="Specific tenant ID to rollback (can be repeated)",
    )
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="Rollback ALL tenants with Phase 3 enabled",
    )
    parser.add_argument(
        "--graceful",
        action="store_true",
        help="Graceful rollback (wait for in-flight executions)",
    )
    parser.add_argument(
        "--emergency",
        action="store_true",
        help="Emergency rollback (immediate disable)",
    )
    parser.add_argument(
        "--force-fail-in-flight",
        action="store_true",
        help="Force-fail in-flight executions (use with --emergency)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify that rollback is complete",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (default: from DATABASE_URL env var)",
    )

    args = parser.parse_args()

    # Get database URL
    import os

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL provided")
        sys.exit(1)

    # Validate arguments
    if not (args.graceful or args.emergency or args.verify):
        logger.error("Specify rollback mode: --graceful, --emergency, or --verify")
        parser.print_help()
        sys.exit(1)

    if args.force_fail_in_flight and not args.emergency:
        logger.error("--force-fail-in-flight requires --emergency mode")
        sys.exit(1)

    try:
        rollback = Phase3Rollback(db_url=db_url)

        if args.verify:
            success = await rollback.verify_rollback(tenant_ids=args.tenant_ids)
            sys.exit(0 if success else 1)

        elif args.graceful:
            success = await rollback.graceful_rollback(
                tenant_ids=args.tenant_ids, all_tenants=args.all_tenants
            )
            sys.exit(0 if success else 1)

        elif args.emergency:
            success = await rollback.emergency_rollback(
                tenant_ids=args.tenant_ids,
                force_fail_in_flight=args.force_fail_in_flight,
            )
            sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
