"""Dramatiq actor for the physical purge of soft-deleted memory items.

AUDIT-004 (GDPR art. 17): soft-delete alone never erases anything; this actor
performs the actual physical erasure on a daily schedule (registered in
src/workers/scheduler.py). The actor is a thin sync wrapper around
purge_expired_soft_deletes() -- all logic lives in the service module so it
stays directly testable.

Pattern notes:
- Sync wrapper + asyncio.run(): a fresh event loop per call, the thread-safe
  approach for parallel workers (CLAUDE.md valkuil -- never
  asyncio.new_event_loop() + set_event_loop() in an actor; precedent:
  cleanup_council_decisions in src/core/governance/retention_cleanup.py).
- Conditional registration mirrors src/core/actors/gdpr_purge.py, but checks
  dramatiq importability directly instead of importing workflow_worker --
  importing src.workers.workflow_worker from here would create an import
  cycle (workers/actors.py re-exports this module for actor discovery).
"""

import asyncio
import logging
from typing import Any

from src.domains.memory.services.memory_purge_service import purge_expired_soft_deletes

logger = logging.getLogger(__name__)

# Module-level placeholder; overridden conditionally below.
# Pattern matches src/core/actors/gdpr_purge.py exactly.
purge_soft_deleted_memory_items: Any = None  # pyright: ignore

try:
    import dramatiq as _dramatiq_probe  # noqa: F401

    _DRAMATIQ_AVAILABLE = True
except ImportError:
    _DRAMATIQ_AVAILABLE = False


if _DRAMATIQ_AVAILABLE:
    from src.core.tasks.dramatiq_broker import workflow_actor

    @workflow_actor(
        queue_name="cleanup",
        max_retries=3,
        time_limit=600_000,  # 10 minutes
        actor_name="purge_soft_deleted_memory_items",
    )
    def purge_soft_deleted_memory_items() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Daily physical purge of expired soft-deleted memory items (AUDIT-004).

        KRITISCH: every DELETE is tenant-scoped via the per-tenant loop in
        purge_expired_soft_deletes (ADR-005) -- never a cross-tenant DELETE.
        """
        result = asyncio.run(purge_expired_soft_deletes())
        logger.info("memory purge actor completed: %s", result)
        return result

else:
    # Testing mode: dummy sender for test patching.
    class _DummySender:
        def send(self, *args: Any, **kwargs: Any) -> Any:
            logger.debug(
                "Dummy purge_soft_deleted_memory_items.send called: args=%s, kwargs=%s",
                args,
                kwargs,
            )
            return None

    purge_soft_deleted_memory_items = _DummySender()  # pyright: ignore
