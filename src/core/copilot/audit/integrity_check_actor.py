"""
Daily Integrity Check Actor for Council Decisions Hash Chain.

Runs daily to ensure tamper-evident logs remain intact.
Uses Dramatiq + Redis.

Sprint 7, Task H2
"""

import asyncio
import logging

from src.core.tasks.dramatiq_broker import workflow_actor
from sqlalchemy import select

from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.rbac_models import Tenant
from src.core.copilot.audit.chain_verifier import ChainVerifier
from src.core.copilot.council.metrics import HASH_CHAIN_BREAKS_TOTAL

logger = logging.getLogger(__name__)


@workflow_actor(queue_name="maintenance", max_retries=3)
def check_hash_chain_integrity_actor() -> None:
    """Sync wrapper -- thread-safe, geen AsyncIO middleware nodig.

    NOTE: asyncio.run() maakt een fresh event loop per aanroep.
    Gebruik nooit asyncio.new_event_loop()+set_event_loop() in een actor --
    dat is niet thread-safe bij parallelle workers (CLAUDE.md valkuil).
    """
    asyncio.run(_check_hash_chain_integrity_async())


async def _check_hash_chain_integrity_async() -> None:
    """Interne async implementatie -- nooit direct aanroepen."""
    logger.info("Starting global hash chain integrity check.")

    async with db_manager.get_session() as db:
        # Use TenantFilterBypass to iterate over all tenants
        with TenantFilterBypass():
            # Get all active tenants
            stmt = select(Tenant.id).where(Tenant.is_active)
            result = await db.execute(stmt)
            tenant_ids = result.scalars().all()

            verifier = ChainVerifier(db)

            for tenant_id in tenant_ids:
                try:
                    logger.debug("Verifying hash chain for tenant %s", tenant_id)
                    # Using global tenant bypass, but the query inside ChainVerifier
                    # explicitly filters by tenant_id, so it's safe.
                    verification_result = await verifier.verify_tenant_chain(tenant_id)

                    if not verification_result.is_valid:
                        # Log broken links and trigger Prometheus metrics
                        for link in verification_result.broken_links:
                            logger.error(
                                "HASH CHAIN BREAK detected! Tenant: %s, Decision ID: %s, Reason: %s",
                                tenant_id,
                                link.decision_id,
                                link.reason,
                            )
                            # Increment Prometheus counter (which triggers alerts)
                            HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id=str(tenant_id)).inc()

                except Exception as e:
                    logger.error(
                        "Failed to verify chain for tenant %s: %s", tenant_id, e, exc_info=True
                    )

    logger.info("Global hash chain integrity check completed.")
