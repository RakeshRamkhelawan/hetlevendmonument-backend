"""
EmbeddingService
================

Generates and stores content embeddings for MemoryItems.

Sprint B implementation: wraps LLMService.get_embeddings() and updates
MemoryItem.content_embedding in-place.  Designed to be called:

  1. Eagerly -- immediately after MemoryWriteService.write() if the caller
     wants synchronous embedding (e.g. during import flows).
  2. Lazily -- from a background task / consolidation worker for bulk updates.

The service never raises; embedding failures are logged and the item is left
with content_embedding=NULL so that retrieval falls back gracefully to FTS/ILIKE.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import MemoryItem

logger = logging.getLogger(__name__)

# Maximum number of items to embed in a single bulk call
_BULK_BATCH_SIZE = int(os.getenv("MEMORY_EMBED_BATCH_SIZE", "50"))


class EmbeddingService:
    """
    Generates embeddings for MemoryItems via the platform's LLMService.

    Usage:
        svc = EmbeddingService(db=session, tenant_id=tenant_id, llm=llm_service)
        await svc.embed_item(item)
        # or
        await svc.embed_pending(agent_id="cva")
    """

    def __init__(self, db: AsyncSession, tenant_id: int, llm: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._db = db
        self._tenant_id = tenant_id
        self._llm = llm  # LLMService instance (has .get_embeddings(text) -> List[float])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed_item(self, item: MemoryItem) -> bool:
        """
        Generate and store an embedding for a single MemoryItem.

        Returns True if the embedding was written, False on failure.
        The session is NOT committed here -- caller controls the transaction.
        """
        try:
            embedding = await self._llm.get_embeddings(item.content)
            if not embedding:
                logger.warning(
                    "EmbeddingService: empty embedding returned",
                    extra={"item_id": item.id},
                )
                return False
            item.content_embedding = embedding
            return True
        except Exception as exc:
            logger.warning(f"EmbeddingService: embed_item failed for item {item.id}: {exc}")
            return False

    async def embed_pending(
        self,
        agent_id: str | None = None,
        limit: int = _BULK_BATCH_SIZE,
    ) -> int:
        """
        Find MemoryItems with NULL embeddings and embed them in batches.

        Returns the count of successfully embedded items.

        Designed for the consolidation worker (Sprint C) or a startup task.
        Each item is flushed individually so partial progress is preserved.
        """
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.content_embedding.is_(None),
                MemoryItem.deleted_at.is_(None),
            )
            .limit(limit)
        )
        if agent_id:
            stmt = stmt.where(MemoryItem.agent_id == agent_id)

        result = await self._db.execute(stmt)
        items: Sequence[MemoryItem] = result.scalars().all()

        succeeded = 0
        for item in items:
            ok = await self.embed_item(item)
            if ok:
                try:
                    await self._db.flush()
                    succeeded += 1
                except Exception as flush_err:
                    logger.warning(
                        f"EmbeddingService: flush failed for item {item.id}: {flush_err}"
                    )

        logger.info(
            "EmbeddingService: embed_pending complete",
            extra={
                "tenant_id": self._tenant_id,
                "agent_id": agent_id,
                "total": len(items),
                "succeeded": succeeded,
            },
        )
        return succeeded

    async def embed_items(self, items: list[MemoryItem]) -> int:
        """
        Embed a list of in-memory MemoryItem objects (already loaded into session).

        Returns count of successfully embedded items.
        Caller controls commit.
        """
        succeeded = 0
        for item in items:
            ok = await self.embed_item(item)
            if ok:
                succeeded += 1
        return succeeded
