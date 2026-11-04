#!/usr/bin/env python3
"""
Phase 3 Rollout Configuration Script
Sprint 5 -- Production Rollout Automation

Purpose: Apply Phase 3 rollout configuration per stage (internal -> canary -> early_adopters -> GA)
Usage: python scripts/apply_rollout_config.py --stage <stage> [--config <yaml>]

Safety: Requires confirmation for GA rollout
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import yaml
from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
)


class RolloutConfigApplier:
    """Apply Phase 3 rollout configuration to production"""

    def __init__(self, config_file: str, db_url: str):
        """
        Args:
            config_file: Path to phase3_canary.yaml
            db_url: Database connection URL
        """
        self.config_file = Path(config_file)
        self.config = self._load_config()

        # Create async engine
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    def _load_config(self) -> Dict:
        """Load rollout configuration from YAML"""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        with open(self.config_file) as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded configuration from {self.config_file}")
        return config

    async def apply_stage(self, stage: str, dry_run: bool = False) -> bool:
        """
        Apply rollout configuration for specific stage.

        Args:
            stage: Rollout stage (internal, canary, early_adopters, general_availability)
            dry_run: If True, show what would be done without applying

        Returns:
            True if successful
        """
        if stage not in self.config["rollout_stages"]:
            logger.error(f"Invalid stage: {stage}")
            logger.info(f"Available stages: {list(self.config['rollout_stages'].keys())}")
            return False

        stage_config = self.config["rollout_stages"][stage]

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Applying Rollout Stage: {stage.upper()}")
        logger.info(f"{'=' * 60}")

        # Get tenant IDs to enable
        tenant_ids = await self._determine_tenant_ids(stage, stage_config)

        logger.info(f"Target tenants: {len(tenant_ids)} tenants")
        logger.info(f"Duration: {stage_config.get('duration_days', 'permanent')} days")

        if stage_config.get("success_criteria"):
            logger.info("\nSuccess Criteria:")
            for criterion in stage_config["success_criteria"]:
                logger.info(f"  - {criterion['metric']}: {criterion['threshold']}")

        if dry_run:
            logger.warning("\n[SEARCH] DRY RUN MODE - No changes will be applied")
            logger.info(f"Would enable Phase 3 for tenants: {tenant_ids}")
            return True

        # Confirmation for GA
        if stage == "general_availability":
            response = input("\n[WARN]  GA ROLLOUT: Enable Phase 3 for ALL tenants? (yes/no): ")
            if response.lower() != "yes":
                logger.warning("GA rollout cancelled by user")
                return False

        # Apply configuration
        async with self.async_session() as session:
            enabled_count = await self._enable_phase3_for_tenants(session, tenant_ids)
            await session.commit()

        logger.success(f"\n[OK] Phase 3 enabled for {enabled_count} tenants")

        # Log rollout event
        await self._log_rollout_event(stage, tenant_ids)

        # Display monitoring info
        self._display_monitoring_info(stage_config)

        return True

    async def _determine_tenant_ids(self, stage: str, stage_config: Dict) -> Set[int]:
        """
        Determine which tenant IDs should have Phase 3 enabled.

        Args:
            stage: Rollout stage name
            stage_config: Stage configuration dict

        Returns:
            Set of tenant IDs
        """
        tenant_ids: Set[int] = set()

        # Explicit tenant list
        if stage_config.get("enabled_tenant_ids"):
            tenant_ids.update(stage_config["enabled_tenant_ids"])

        # Percentage-based selection
        if stage_config.get("percentage", 0) > 0:
            percentage = stage_config["percentage"] / 100.0
            async with self.async_session() as session:
                all_tenant_ids = await self._get_all_tenant_ids(session, stage_config)
                count = int(len(all_tenant_ids) * percentage)
                tenant_ids.update(all_tenant_ids[:count])

        # Selection criteria
        if stage_config.get("selection_criteria"):
            async with self.async_session() as session:
                criteria_tenants = await self._apply_selection_criteria(
                    session, stage_config["selection_criteria"]
                )
                tenant_ids.update(criteria_tenants)

        # Tenant overrides
        overrides = self.config.get("tenant_overrides", {})
        for tenant_key, override_config in overrides.items():
            if override_config.get("phase3_enabled"):
                tenant_id = int(tenant_key.split("_")[1])  # Extract ID from "tenant_500"
                tenant_ids.add(tenant_id)

        return tenant_ids

    async def _get_all_tenant_ids(self, session: AsyncSession, stage_config: Dict) -> List[int]:
        """Get all active tenant IDs, respecting exclusion criteria"""
        query = """
            SELECT id FROM tenants
            WHERE is_active = true
            ORDER BY id
        """

        result = await session.execute(text(query))
        all_ids = [row[0] for row in result.fetchall()]

        # Apply exclusions
        if stage_config.get("selection_criteria"):
            criteria = stage_config["selection_criteria"]
            if criteria.get("exclude_enterprise"):
                # Exclude enterprise tier (hypothetical - adjust based on your schema)
                all_ids = [tid for tid in all_ids if tid < 1000]  # Example logic

        return all_ids

    async def _apply_selection_criteria(self, session: AsyncSession, criteria: Dict) -> List[int]:
        """Apply selection criteria to filter tenants"""
        # This is a simplified implementation
        # In production, you'd query based on actual criteria

        query = "SELECT id FROM tenants WHERE is_active = true"

        if criteria.get("min_active_users"):
            # Cast to int to prevent SQL injection via config value tampering.
            # SQLAlchemy text() does not support bind params for inline numeric
            # expressions in subqueries, so integer coercion is the correct guard.
            min_users = int(criteria["min_active_users"])
            query += f" AND (SELECT COUNT(*) FROM users WHERE tenant_id = tenants.id AND is_active = true) >= {min_users}"  # nosec B608

        result = await session.execute(text(query))
        return [row[0] for row in result.fetchall()]

    async def _enable_phase3_for_tenants(self, session: AsyncSession, tenant_ids: Set[int]) -> int:
        """
        Enable Phase 3 feature flag for specified tenants.

        Args:
            session: Database session
            tenant_ids: Set of tenant IDs to enable

        Returns:
            Number of tenants enabled
        """
        count = 0

        for tenant_id in tenant_ids:
            # Insert or update feature flag
            await session.execute(
                text(
                    """
                INSERT INTO feature_flags (tenant_id, feature_name, is_enabled, created_at, updated_at)
                VALUES (:tenant_id, 'phase3.capability_agents', true, NOW(), NOW())
                ON CONFLICT (tenant_id, feature_name)
                DO UPDATE SET is_enabled = true, updated_at = NOW()
            """
                ),
                {"tenant_id": tenant_id},
            )

            count += 1
            logger.debug(f"Enabled Phase 3 for tenant {tenant_id}")

        return count

    async def _log_rollout_event(self, stage: str, tenant_ids: Set[int]):
        """Log rollout event for metrics"""
        async with self.async_session() as session:
            await session.execute(
                text(
                    """
                INSERT INTO rollout_events (stage, tenant_count, tenant_ids, timestamp)
                VALUES (:stage, :count, :ids, NOW())
            """
                ),
                {
                    "stage": stage,
                    "count": len(tenant_ids),
                    "ids": list(tenant_ids)[:100],  # Store first 100 for audit
                },
            )
            await session.commit()

        logger.info(f"Rollout event logged: {stage} ({len(tenant_ids)} tenants)")

    def _display_monitoring_info(self, stage_config: Dict):
        """Display monitoring dashboard info"""
        logger.info(f"\n{'=' * 60}")
        logger.info("[CHART] MONITORING")
        logger.info(f"{'=' * 60}")

        monitoring = stage_config.get("monitoring", {})

        if monitoring.get("dashboard"):
            logger.info(f"Dashboard: {monitoring['dashboard']}")

        if monitoring.get("alert_channels"):
            channels = ", ".join(monitoring["alert_channels"])
            logger.info(f"Alerts: {channels}")

        logger.info("\nNext Steps:")
        logger.info("1. Monitor Grafana dashboard for errors")
        logger.info("2. Watch alert channels for incidents")
        logger.info("3. Review daily/weekly reports")
        logger.info(f"{'=' * 60}\n")

    async def rollback_stage(self, stage: str) -> bool:
        """
        Rollback Phase 3 for a specific stage.

        Args:
            stage: Stage to rollback

        Returns:
            True if successful
        """
        logger.warning(f"\n[WARN]  ROLLBACK: Disabling Phase 3 for stage '{stage}'")

        stage_config = self.config["rollout_stages"].get(stage)
        if not stage_config:
            logger.error(f"Invalid stage: {stage}")
            return False

        tenant_ids = await self._determine_tenant_ids(stage, stage_config)

        async with self.async_session() as session:
            # Disable feature flags
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

            await session.commit()

        logger.success(f"[OK] Phase 3 disabled for {len(tenant_ids)} tenants")
        return True

    async def status(self) -> Dict:
        """Get current rollout status"""
        async with self.async_session() as session:
            result = await session.execute(
                text(
                    """
                SELECT
                    COUNT(*) FILTER (WHERE is_enabled = true) as enabled_count,
                    COUNT(*) as total_flags
                FROM feature_flags
                WHERE feature_name = 'phase3.capability_agents'
            """
                )
            )

            row = result.fetchone()
            enabled_count = row[0] if row else 0
            total_flags = row[1] if row else 0

            # Get total tenants
            total_tenants_result = await session.execute(
                text("SELECT COUNT(*) FROM tenants WHERE is_active = true")
            )
            total_tenants = total_tenants_result.scalar() or 0

        percentage = (enabled_count / total_tenants * 100) if total_tenants > 0 else 0

        status = {
            "enabled_tenants": enabled_count,
            "total_tenants": total_tenants,
            "percentage": round(percentage, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info("\n[CHART] Phase 3 Rollout Status")
        logger.info(f"{'=' * 40}")
        logger.info(f"Enabled: {enabled_count}/{total_tenants} tenants ({percentage:.1f}%)")
        logger.info(f"{'=' * 40}\n")

        return status


async def main():
    parser = argparse.ArgumentParser(description="Apply Phase 3 rollout configuration")
    parser.add_argument(
        "--stage",
        required=True,
        choices=["internal", "canary", "early_adopters", "general_availability"],
        help="Rollout stage to apply",
    )
    parser.add_argument(
        "--config",
        default="config/rollout/phase3_canary.yaml",
        help="Path to rollout config YAML (default: config/rollout/phase3_canary.yaml)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without applying changes",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the specified stage",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current rollout status",
    )

    args = parser.parse_args()

    # Get database URL
    import os

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("No database URL provided (use --db-url or DATABASE_URL env var)")
        sys.exit(1)

    # Safety: Prevent accidental production use without confirmation
    if "production" in db_url.lower() and not args.dry_run:
        response = input("[WARN]  Production database detected. Continue? (yes/no): ")
        if response.lower() != "yes":
            logger.warning("Cancelled by user")
            sys.exit(0)

    try:
        applier = RolloutConfigApplier(config_file=args.config, db_url=db_url)

        if args.status:
            await applier.status()
        elif args.rollback:
            success = await applier.rollback_stage(args.stage)
            sys.exit(0 if success else 1)
        else:
            success = await applier.apply_stage(args.stage, dry_run=args.dry_run)
            sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
