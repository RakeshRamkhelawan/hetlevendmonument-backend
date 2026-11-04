"""Physical purge of soft-deleted memory items (AUDIT-004, GDPR art. 17).

Background: MemoryWriteService.soft_delete_item only sets deleted_at. Before
this module existed, NO task or endpoint ever physically removed the row or
its embedding, so an explicit erasure request could never actually be carried
out (structural non-compliance, not an edge case).

Design notes:
- content_embedding is a column on the same row (models.py), so one physical
  DELETE purges row + embedding together. There is no separate vector store.
- The embedding is a non-anonymisable derivative of personal data; hard DELETE
  is the only correct erasure for Twin memory (unlike conversations, which
  can be anonymised to preserve an audit trail).
- Every DELETE is tenant-scoped: tenant discovery runs under
  TenantFilterBypass (worker processes have no tenant ContextVar, so the
  do_orm_execute hook would otherwise inject WHERE 1=0), followed by a
  per-tenant loop with an explicit WHERE tenant_id -- never a cross-tenant
  DELETE (ADR-005).
- The purge audit entry runs AFTER the purge commit, on its own session,
  under best_effort: an audit failure must never roll back the completed
  purge (precedent: src/core/actors/gdpr_purge.py).
"""

import importlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.utils.best_effort import best_effort
from src.domains.memory.models import MemoryItem

logger = logging.getLogger(__name__)

# Grace period between soft-delete and physical purge. Follows the platform
# convention DSARServiceConfig.soft_delete_grace_period_days = 30
# (src/core/governance/dsar_service.py). Pass grace_period_days explicitly
# to override (tests, jurisdiction-specific policies).
MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS = 30


async def purge_soft_deleted_items(
    db: AsyncSession,
    tenant_id: int,
    *,
    now: datetime | None = None,
    grace_period_days: int = MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS,
) -> int:
    """Physically delete expired soft-deleted memory items for ONE tenant.

    Args:
        db: Active AsyncSession (caller commits).
        tenant_id: Tenant scope -- MANDATORY, never purge cross-tenant.
        now: Reference time (injectable for tests; defaults to UTC now).
        grace_period_days: Days between soft-delete and physical purge.

    Returns:
        Number of physically deleted rows (row + content_embedding column).
    """
    reference = now or datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=grace_period_days)

    result = await db.execute(
        delete(MemoryItem).where(
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.deleted_at.is_not(None),
            MemoryItem.deleted_at < cutoff,
        )
    )
    deleted = cast(CursorResult[RowMapping], result).rowcount or 0
    logger.info(
        "memory purge: tenant=%s deleted=%d cutoff=%s",
        tenant_id,
        deleted,
        cutoff.isoformat(),
    )
    return deleted


async def purge_expired_soft_deletes(
    *,
    now: datetime | None = None,
    grace_period_days: int = MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Purge expired soft-deleted memory items for all tenants, per tenant.

    Discovery query is cross-tenant by necessity (under TenantFilterBypass);
    every DELETE is executed per tenant with an explicit WHERE tenant_id.
    Idempotent: re-running purges 0 rows once the set is empty.

    Returns:
        Summary dict: items_purged, per_tenant, tenants_processed, cutoff,
        grace_period_days.
    """
    reference = now or datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=grace_period_days)

    per_tenant: dict[int, int] = {}

    async with get_db_session() as session:
        with TenantFilterBypass():
            tid_result = await session.execute(
                select(MemoryItem.tenant_id)
                .where(
                    MemoryItem.deleted_at.is_not(None),
                    MemoryItem.deleted_at < cutoff,
                )
                .distinct()
            )
            tenant_ids = list(tid_result.scalars().all())

            for tid in tenant_ids:
                deleted = await purge_soft_deleted_items(
                    session,
                    tid,
                    now=reference,
                    grace_period_days=grace_period_days,
                )
                if deleted:
                    per_tenant[tid] = deleted

            await session.commit()

    summary: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "items_purged": sum(per_tenant.values()),
        "per_tenant": per_tenant,
        "tenants_processed": len(tenant_ids),
        "cutoff": cutoff.isoformat(),
        "grace_period_days": grace_period_days,
    }

    # Audit AFTER the purge commit, on its own session, best-effort: an audit
    # failure must never roll back the completed purge (ADR-019 hash chain;
    # precedent: src/core/actors/gdpr_purge.py). One audit entry per purged
    # tenant -- audit_logs.tenant_id is a real FK, so a synthetic system id
    # could fail the INSERT; a tenant that just had rows purged provably
    # exists. Runs with zero purged rows write no audit entry (consistent
    # with cleanup_council_decisions, which logs only). The explicit flush
    # happens INSIDE best_effort: AuditService.log_action only adds the
    # entry, so without a flush a failing INSERT would escape the guard and
    # abort the session later (observed: Query-invoked autoflush on the next
    # query).
    if per_tenant:
        try:
            async with get_db_session() as audit_db:
                with TenantFilterBypass():
                    async with best_effort("memory purge audit log", db_session=audit_db):
                        # importlib avoids direct ImportFrom
                        # (DSM boundary agent_runtime -> governance)
                        audit_mod = importlib.import_module("src.core.governance.audit")
                        for tid, count in per_tenant.items():
                            await audit_mod.AuditService.log_action(
                                tenant_id=tid,
                                action="memory_purge_executed",
                                resource="memory_items:soft_deleted",
                                user_id=None,
                                details={
                                    "items_purged": count,
                                    "cutoff": cutoff.isoformat(),
                                    "grace_period_days": grace_period_days,
                                },
                                session=audit_db,
                                event_type="gdpr_purge",
                                threat_level="info",
                                client_ip="system",
                                endpoint="purge_soft_deleted_memory_items",
                                description=(
                                    f"Memory purge: {count} soft-deleted items "
                                    f"physically erased for tenant {tid}"
                                ),
                            )
                        await audit_db.flush()
        except Exception as audit_exc:  # pragma: no cover - defensive; best_effort already swallows
            logger.warning(
                "memory purge audit setup failed: %s: %s",
                type(audit_exc).__name__,
                audit_exc,
            )

    logger.info(
        "memory purge completed: items_purged=%d tenants=%d cutoff=%s",
        summary["items_purged"],
        len(per_tenant),
        cutoff.isoformat(),
    )
    return summary
