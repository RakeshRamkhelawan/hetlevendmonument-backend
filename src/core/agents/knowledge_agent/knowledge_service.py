"""
Asynchrone Knowledge Service
Beheert de logica voor interactie met knowledge_entries in de database.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.knowledge.models import KnowledgeEntry

logger = logging.getLogger(__name__)


class KnowledgeEntryCreate(BaseModel):
    content: str
    type: str = "general"
    entry_metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    confidence_score: float = 1.0


class KnowledgeService:
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def create_entry(self, entry_data: KnowledgeEntryCreate) -> KnowledgeEntry:
        """Creeert een nieuwe knowledge entry in de database."""
        try:
            logger.info("Poging tot het creeren van een nieuwe knowledge entry.")
            db_entry = KnowledgeEntry(
                content=entry_data.content,
                type=entry_data.type,
                entry_metadata=entry_data.entry_metadata,
                confidence_score=entry_data.confidence_score,
            )
            self.session.add(db_entry)
            await self.session.commit()
            await self.session.refresh(db_entry)
            logger.info(f"Knowledge entry succesvol gecreeerd met ID: {db_entry.id}")
            return db_entry
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Fout bij het creeren van knowledge entry: {e}", exc_info=True)
            raise

    async def get_entry(self, entry_id: UUID) -> KnowledgeEntry | None:
        """Haalt een knowledge entry op basis van ID, gefilterd op tenant (ADR-005)."""
        result = await self.session.execute(
            select(KnowledgeEntry).filter(
                KnowledgeEntry.id == entry_id,
                KnowledgeEntry.tenant_id == self.tenant_id,
            )
        )
        return result.scalars().first()
