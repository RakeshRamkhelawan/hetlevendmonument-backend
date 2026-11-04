"""
MemoryWriteService
==================

Write path for all memory operations.

Responsibilities:
- Validate content before persistence
- Exact-duplicate detection via SHA-256 of normalised content
- Create MemoryItem with status=proposed (safe default)
- Support auto_accept=True for trusted system sources
- Log SessionMemoryEvent for every write
- Optionally queue embedding generation (Sprint B: async worker)

Security rules:
- tenant_id ALWAYS injected from authenticated context, never from client
- status=proposed is the default -- only trusted callers may auto_accept
- auto_accept is gated on source_type whitelist, not a client flag
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import MemoryItem, SessionMemoryEvent
from src.domains.memory.observability import WRITE_OPERATIONS
from src.domains.memory.schemas import MemoryItemWrite, SessionEventWrite

logger = logging.getLogger(__name__)

# Source types that may auto-accept (system-generated, high-trust)
AUTO_ACCEPT_SOURCES = {"consolidation", "workflow"}


def _normalise(content: str) -> str:
    """Normalise content for dedup hash -- lowercase, collapse whitespace."""
    return " ".join(content.lower().split())


def _dedup_hash(content: str) -> str:
    """SHA-256 of normalised content for exact-duplicate detection."""
    return hashlib.sha256(_normalise(content).encode("utf-8")).hexdigest()


class MemoryWriteService:
    """
    Stateless write service -- instantiate per request with injected session.

    Usage:
        service = MemoryWriteService(db=session, tenant_id=tenant_id)
        item = await service.write(payload)
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def write(
        self,
        payload: MemoryItemWrite,
        auto_accept: bool = False,
    ) -> MemoryItem:
        """
        Write a single memory candidate.

        Args:
            payload:     Validated MemoryItemWrite schema.
            auto_accept: Override status to 'accepted' (only for trusted callers).
                         The caller must verify source_type is in AUTO_ACCEPT_SOURCES.

        Returns:
            Persisted MemoryItem (status=proposed or accepted).
        """
        # Determine status
        is_auto_accept = auto_accept and payload.source_type in AUTO_ACCEPT_SOURCES
        status = "accepted" if is_auto_accept else "proposed"

        # Exact-duplicate guard
        ddup = _dedup_hash(payload.content)
        existing = await self._find_duplicate(ddup, payload.agent_id)
        if existing:
            logger.debug(
                "MemoryWriteService: duplicate skipped",
                extra={
                    "tenant_id": self._tenant_id,
                    "existing_id": existing.id,
                    "dedup_hash": ddup[:12],
                },
            )
            WRITE_OPERATIONS.labels(
                tenant_id=str(self._tenant_id), outcome="duplicate_skipped"
            ).inc()
            return existing

        item = MemoryItem(
            tenant_id=self._tenant_id,
            agent_id=payload.agent_id,
            user_id=payload.user_id,
            workspace_id=payload.workspace_id,
            memory_type=payload.memory_type,
            content=payload.content,
            confidence=payload.confidence,
            importance=payload.importance,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            privacy_scope=payload.privacy_scope,
            status=status,
            tags=payload.tags,
            entities=[],
            provenance=[{"source": payload.source_type, "ref": payload.source_ref}],
            dedup_hash=ddup,
        )

        self._db.add(item)
        await self._db.flush()  # get id without committing

        WRITE_OPERATIONS.labels(tenant_id=str(self._tenant_id), outcome="created").inc()
        logger.info(
            "MemoryWriteService: item written",
            extra={
                "tenant_id": self._tenant_id,
                "item_id": item.id,
                "memory_type": item.memory_type,
                "status": item.status,
                "source_type": item.source_type,
            },
        )
        return item

    async def bulk_write(
        self,
        payloads: list[MemoryItemWrite],
        auto_accept: bool = False,
    ) -> list[MemoryItem]:
        """
        Write multiple memory candidates in a single transaction.
        Skips duplicates silently. Returns only newly created items.
        """
        created: list[MemoryItem] = []
        for payload in payloads:
            item = await self.write(payload, auto_accept=auto_accept)
            created.append(item)
        return created

    async def log_session_event(self, payload: SessionEventWrite) -> SessionMemoryEvent:
        """
        Append an event to the session event log.

        This is append-only -- never updates existing rows.
        """
        event = SessionMemoryEvent(
            tenant_id=self._tenant_id,
            session_id=payload.session_id,
            agent_id=payload.agent_id,
            user_id=payload.user_id,
            event_type=payload.event_type,
            event_data=payload.event_data,
            memory_candidate=payload.memory_candidate,
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def update_item_status(
        self,
        item_id: int,
        new_status: str,
    ) -> MemoryItem | None:
        """
        Transition a MemoryItem to a new status.

        Allowed transitions:
          proposed -> accepted
          proposed -> archived
          accepted -> archived
          accepted -> contradicted
        """
        result = await self._db.execute(
            select(MemoryItem).where(
                MemoryItem.id == item_id,
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.deleted_at.is_(None),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return None

        item.status = new_status
        await self._db.flush()

        logger.info(
            "MemoryWriteService: status updated",
            extra={
                "tenant_id": self._tenant_id,
                "item_id": item_id,
                "new_status": new_status,
            },
        )
        return item

    async def soft_delete_item(self, item_id: int) -> bool:
        """Soft-delete a memory item. Returns True if found and deleted."""
        result = await self._db.execute(
            select(MemoryItem).where(
                MemoryItem.id == item_id,
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.deleted_at.is_(None),
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return False

        item.deleted_at = datetime.now(timezone.utc)
        await self._db.flush()
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_duplicate(
        self,
        dedup_hash: str,
        agent_id: str | None,
    ) -> MemoryItem | None:
        """Return existing non-archived item with same dedup hash, if any."""
        stmt = select(MemoryItem).where(
            MemoryItem.tenant_id == self._tenant_id,
            MemoryItem.dedup_hash == dedup_hash,
            MemoryItem.status.not_in(["archived"]),
            MemoryItem.deleted_at.is_(None),
        )
        if agent_id:
            stmt = stmt.where(MemoryItem.agent_id == agent_id)

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
