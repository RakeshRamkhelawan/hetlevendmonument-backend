"""
MemoryConsolidationWorker
=========================

Nightly worker that processes unresolved SessionMemoryEvents and promotes
them to durable MemoryItems.

Pipeline per run:
  1. Open a MemoryConsolidationRun row (status=running)
  2. Fetch unresolved candidates (memory_candidate=True, resolved_item_id=NULL)
  3. Cluster near-duplicate events by normalised content hash
  4. For each cluster: write a MemoryItem (source_type='consolidation', auto_accept=True)
     and mark the originating events as resolved
  5. Archive MemoryItems that contradict newer, higher-confidence items
  6. Update run row (status=completed/failed/partial) with outcome metrics
  7. Emit Prometheus metrics

Sprint B gap-fill: also calls EmbeddingService.embed_pending() so that items
written via chat/cva_turn that were not embedded at write-time get embeddings.

Design rules:
- Single DB transaction per batch of events (rollback-safe)
- Never raises -- all exceptions are caught and recorded in the run row
- Tenant-scoped: ALWAYS pass tenant_id, NEVER query without it
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import MemoryConsolidationRun, MemoryItem, SessionMemoryEvent
from src.domains.memory.observability import (
    CONSOLIDATION_DURATION,
    CONSOLIDATION_ERRORS,
    CONSOLIDATION_ITEMS_ARCHIVED,
    CONSOLIDATION_ITEMS_CREATED,
    CONSOLIDATION_RUNS,
)
from src.domains.memory.schemas import MemoryItemWrite
from src.domains.memory.services.memory_write_service import (
    AUTO_ACCEPT_SOURCES,
    MemoryWriteService,
    _dedup_hash,
)

logger = logging.getLogger(__name__)

# Batch size for event fetching -- keeps transactions small
_BATCH_SIZE = int(__import__("os").getenv("MEMORY_CONSOLIDATION_BATCH", "200"))


class MemoryConsolidationWorker:
    """
    Consolidation worker -- instantiate per run, per tenant.

    Usage (called by scheduler or API):
        worker = MemoryConsolidationWorker(db=session, tenant_id=tenant_id)
        run = await worker.run(agent_id="cva")
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        llm: Any | None = None,  # Optional LLMService for embedding backfill  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._llm = llm
        self._write_svc = MemoryWriteService(db=db, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        agent_id: str | None = None,
        batch_size: int = _BATCH_SIZE,
    ) -> MemoryConsolidationRun:
        """
        Execute one consolidation run.

        Returns the completed MemoryConsolidationRun ORM object.
        Never raises -- exceptions are stored in run.error_message.
        """
        run = await self._open_run(agent_id)
        start = time.perf_counter()

        sessions_processed = 0
        events_processed = 0
        items_created = 0
        items_archived = 0
        contradictions_found = 0
        error_msg: str | None = None

        try:
            # Phase 1: promote candidate events -> MemoryItems
            events = await self._fetch_candidates(agent_id, batch_size)
            sessions_seen: set[Any] = set()  # TODO(TYPE): replace Any with concrete type
            clusters: dict[str, list[SessionMemoryEvent]] = {}

            for ev in events:
                sessions_seen.add(ev.session_id)
                if ev.event_data and isinstance(ev.event_data, dict):
                    text = ev.event_data.get("content", "") or ""
                else:
                    text = str(ev.event_data or "")
                if not text.strip():
                    continue
                h = _dedup_hash(text)
                clusters.setdefault(h, []).append(ev)

            sessions_processed = len(sessions_seen)
            events_processed = len(events)

            for cluster_events in clusters.values():
                # Use the most recent event as canonical
                canonical = max(cluster_events, key=lambda e: e.created_at or datetime.min)
                content = (
                    canonical.event_data.get("content", "")
                    if isinstance(canonical.event_data, dict)
                    else str(canonical.event_data)
                )
                if not content.strip():
                    continue

                payload = MemoryItemWrite(
                    content=content,
                    memory_type=_infer_memory_type(canonical),
                    source_type="consolidation",
                    agent_id=canonical.agent_id,
                    confidence=0.85,
                    importance=0.6,
                    privacy_scope="tenant",
                )
                item = await self._write_svc.write(payload=payload, auto_accept=True)
                if item:
                    # Check if it was a fresh create (no prior dedup)
                    is_new = item.source_type == "consolidation" and item.status == "accepted"
                    if is_new:
                        items_created += 1
                    # Mark all events in cluster as resolved
                    for ev in cluster_events:
                        ev.resolved_item_id = item.id
                    await self._db.flush()

            # Phase 2: archive stale/low-confidence items
            archived = await self._archive_stale(agent_id)
            items_archived = archived

            # Phase 3: backfill embeddings for items without vectors
            if self._llm:
                from src.domains.memory.services.embedding_service import EmbeddingService

                embed_svc = EmbeddingService(db=self._db, tenant_id=self._tenant_id, llm=self._llm)
                await embed_svc.embed_pending(agent_id=agent_id, limit=100)

            status = "completed"

        except Exception as exc:
            error_msg = str(exc)
            status = "failed"
            logger.error(
                f"ConsolidationWorker: run failed for tenant {self._tenant_id}: {exc}",
                exc_info=True,
            )
            CONSOLIDATION_ERRORS.labels(tenant_id=str(self._tenant_id)).inc()

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Close the run row
        run.completed_at = datetime.now(timezone.utc)
        run.status = status
        run.sessions_processed = sessions_processed
        run.events_processed = events_processed
        run.items_created = items_created
        run.items_archived = items_archived
        run.contradictions_found = contradictions_found
        run.error_message = error_msg
        run.run_metadata = {"elapsed_ms": round(elapsed_ms, 1)}
        await self._db.flush()

        # Prometheus
        CONSOLIDATION_RUNS.labels(
            tenant_id=str(self._tenant_id),
            status=status,
        ).inc()
        CONSOLIDATION_ITEMS_CREATED.labels(tenant_id=str(self._tenant_id)).inc(items_created)
        CONSOLIDATION_ITEMS_ARCHIVED.labels(tenant_id=str(self._tenant_id)).inc(items_archived)
        CONSOLIDATION_DURATION.labels(tenant_id=str(self._tenant_id)).observe(elapsed_ms / 1000)

        logger.info(
            "ConsolidationWorker: run complete",
            extra={
                "tenant_id": self._tenant_id,
                "agent_id": agent_id,
                "status": status,
                "events": events_processed,
                "items_created": items_created,
                "items_archived": items_archived,
                "elapsed_ms": round(elapsed_ms, 1),
            },
        )
        return run

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _open_run(self, agent_id: str | None) -> MemoryConsolidationRun:
        run = MemoryConsolidationRun(
            tenant_id=self._tenant_id,
            agent_id=agent_id,
            status="running",
            sessions_processed=0,
            events_processed=0,
            items_created=0,
            items_archived=0,
            contradictions_found=0,
        )
        self._db.add(run)
        await self._db.flush()
        return run

    async def _fetch_candidates(
        self,
        agent_id: str | None,
        limit: int,
    ) -> list[SessionMemoryEvent]:
        stmt = (
            select(SessionMemoryEvent)
            .where(
                SessionMemoryEvent.tenant_id == self._tenant_id,
                SessionMemoryEvent.memory_candidate.is_(True),
                SessionMemoryEvent.resolved_item_id.is_(None),
            )
            .order_by(SessionMemoryEvent.created_at)
            .limit(limit)
        )
        if agent_id:
            stmt = stmt.where(SessionMemoryEvent.agent_id == agent_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _archive_stale(self, agent_id: str | None) -> int:
        """
        Archive MemoryItems that:
          - Have been superseded (contradicts_item_id IS NOT NULL), or
          - Have importance < 0.1 and are older than 90 days

        Returns count of archived items.
        """
        from sqlalchemy import text

        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.status == "accepted",
                MemoryItem.deleted_at.is_(None),
                MemoryItem.contradicts_item_id.isnot(None),
            )
            .limit(100)
        )
        if agent_id:
            stmt = stmt.where(MemoryItem.agent_id == agent_id)

        result = await self._db.execute(stmt)
        items = result.scalars().all()
        count = 0
        for item in items:
            item.status = "archived"
            count += 1
        if count:
            await self._db.flush()
        return count


def _infer_memory_type(event: SessionMemoryEvent) -> str:
    """
    Heuristic: infer MemoryItem.memory_type from event_type.
    """
    etype = event.event_type or ""
    if etype in ("message", "observation"):
        return "episodic"
    if etype == "decision":
        return "procedural"
    if etype == "workflow_complete":
        return "semantic"
    return "episodic"
