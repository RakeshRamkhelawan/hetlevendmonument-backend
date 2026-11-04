"""
KnowledgeService - Production Implementation (Sync Version)
Service laag voor kennisbeheer CRUD operaties zoals gespecificeerd in FASE 3 STAP 3.1.2
Aangepast voor sync database operaties met bestaande database connection
"""

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Removed sync Session import - using async sessions only
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from src.core.database.database import db_manager
from src.core.knowledge.models import KnowledgeEntry  # Phase 6 Task 6: Migrated to domain module

logger = logging.getLogger(__name__)


class KnowledgeEntryCreate(BaseModel):
    """Pydantic model voor het aanmaken van knowledge entries"""

    model_config = ConfigDict(use_enum_values=True)

    content: str = Field(description="Knowledge content text")
    type: str = Field(description="Type/category of knowledge")
    entry_metadata: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Additional metadata as JSON"
    )
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence score between 0 and 1"
    )


class KnowledgeEntryUpdate(BaseModel):
    """Pydantic model voor het updaten van knowledge entries"""

    model_config = ConfigDict(use_enum_values=True)

    content: str | None = Field(default=None, description="Updated knowledge content")
    type: str | None = Field(default=None, description="Updated type/category")
    entry_metadata: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Updated metadata"
    )  # TODO(TYPE): replace Any with concrete type
    confidence_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Updated confidence score"
    )


class KnowledgeEntryResponse(BaseModel):
    """Pydantic model voor knowledge entry responses"""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    content: str
    type: str
    entry_metadata: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    confidence_score: float
    created_at: datetime
    updated_at: datetime


class KnowledgeService:
    """
    KnowledgeService voor FASE 3 kennisbeheer systeem
    Implementeert CRUD operaties zoals gespecificeerd in plan (sync versie)
    """

    def __init__(self, tenant_id: int | None = None) -> None:
        """Initialize the KnowledgeService"""
        self.tenant_id = tenant_id
        logger.info("KnowledgeService initialized")

    async def create_entry(self, entry_data: KnowledgeEntryCreate) -> KnowledgeEntryResponse:
        """
        Create a new knowledge entry (ASYNC-FIRST ARCHITECTURE)

        Args:
            entry_data: KnowledgeEntryCreate model met entry data

        Returns:
            KnowledgeEntryResponse: Created knowledge entry

        Raises:
            SQLAlchemyError: Database operation errors
        """
        from src.core.database.session import get_db_session
        from src.core.knowledge.models import KnowledgeEntry  # Phase 6 Task 6

        try:
            async with get_db_session() as async_session:
                # Create new knowledge entry
                new_entry = KnowledgeEntry(
                    content=entry_data.content,
                    type=entry_data.type,
                    entry_metadata=entry_data.entry_metadata,
                    confidence_score=entry_data.confidence_score,
                )

                # Add to session and commit
                async_session.add(new_entry)
                await async_session.commit()
                await async_session.refresh(new_entry)

                logger.info(f"Created knowledge entry {new_entry.id} of type '{new_entry.type}'")
                return KnowledgeEntryResponse.model_validate(new_entry)

        except SQLAlchemyError as e:
            logger.error(f"Database error creating knowledge entry: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating knowledge entry: {e}")
            raise
        # Fallback to satisfy type checker - should never reach here
        raise RuntimeError("Unexpected code path in create_entry")

    # Removed _create_entry_internal - using async create_entry only

    async def get_entry(self, entry_id: int) -> KnowledgeEntryResponse | None:
        """
        Haal een knowledge entry op via ID zoals gespecificeerd in plan

        Args:
            entry_id: ID van de knowledge entry

        Returns:
            Optional[KnowledgeEntryResponse]: Knowledge entry of None als niet gevonden
        """
        try:
            async with db_manager.get_session() as session:
                return await self._get_entry_internal(entry_id, session)

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving knowledge entry {entry_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving knowledge entry {entry_id}: {e}")
            raise

    async def _get_entry_internal(
        self,
        entry_id: int,
        session: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> KnowledgeEntryResponse | None:
        """Internal method for getting entry with session"""
        # Query for knowledge entry -- always filter by tenant when available (ADR-005)
        stmt = select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        if self.tenant_id is not None:
            stmt = stmt.where(KnowledgeEntry.tenant_id == self.tenant_id)
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry:
            logger.info(f"Retrieved knowledge entry {entry_id}")
            return KnowledgeEntryResponse.model_validate(entry)
        else:
            logger.warning(f"Knowledge entry {entry_id} not found")
            return None

    async def update_entry(
        self, entry_id: int, update_data: KnowledgeEntryUpdate
    ) -> KnowledgeEntryResponse | None:
        """
        Update een knowledge entry zoals gespecificeerd in plan

        Args:
            entry_id: ID van de knowledge entry
            update_data: KnowledgeEntryUpdate model met update data
            session: Optionele database session

        Returns:
            Optional[KnowledgeEntryResponse]: Updated knowledge entry of None als niet gevonden
        """
        try:
            async with db_manager.get_session() as session:
                return await self._update_entry_internal(entry_id, update_data, session)

        except SQLAlchemyError as e:
            logger.error(f"Database error updating knowledge entry {entry_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating knowledge entry {entry_id}: {e}")
            raise

    async def _update_entry_internal(
        self,
        entry_id: int,
        update_data: KnowledgeEntryUpdate,
        session: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> KnowledgeEntryResponse | None:
        """Internal method for updating entry with session"""
        # Build update dictionary (only non-None values)
        update_dict: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if update_data.content is not None:
            update_dict["content"] = update_data.content
        if update_data.type is not None:
            update_dict["type"] = update_data.type
        if update_data.entry_metadata is not None:
            update_dict["entry_metadata"] = update_data.entry_metadata
        if update_data.confidence_score is not None:
            update_dict["confidence_score"] = update_data.confidence_score

        if not update_dict:
            logger.warning(f"No fields to update for knowledge entry {entry_id}")
            return await self._get_entry_internal(entry_id, session)

        # Add updated_at timestamp
        update_dict["updated_at"] = datetime.now(timezone.utc)

        # Execute update
        stmt = update(KnowledgeEntry).where(KnowledgeEntry.id == entry_id).values(**update_dict)
        result = await session.execute(stmt)

        if getattr(result, "rowcount", 0) == 0:
            logger.warning(f"Knowledge entry {entry_id} not found for update")
            return None

        await session.commit()

        logger.info(f"Updated knowledge entry {entry_id}")

        # Return updated entry
        return await self._get_entry_internal(entry_id, session)

    async def delete_entry(self, entry_id: int) -> bool:
        """
        Verwijder een knowledge entry zoals gespecificeerd in plan

        Args:
            entry_id: ID van de knowledge entry
            session: Optionele database session

        Returns:
            bool: True als succesvol verwijderd, False als niet gevonden
        """
        try:
            async with db_manager.get_session() as session:
                return await self._delete_entry_internal(entry_id, session)

        except SQLAlchemyError as e:
            logger.error(f"Database error deleting knowledge entry {entry_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting knowledge entry {entry_id}: {e}")
            raise

    async def _delete_entry_internal(
        self,
        entry_id: int,
        session: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Internal method for deleting entry with session"""
        # Execute delete
        stmt = delete(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        result = await session.execute(stmt)

        if getattr(result, "rowcount", 0) == 0:
            logger.warning(f"Knowledge entry {entry_id} not found for deletion")
            return False

        await session.commit()

        logger.info(f"Deleted knowledge entry {entry_id}")
        return True

    async def list_entries(
        self, entry_type: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[KnowledgeEntryResponse]:
        """
        Lijst alle knowledge entries met optionele filtering

        Args:
            entry_type: Optioneel filter op entry type
            limit: Maximum aantal entries (default 100)
            offset: Offset voor paginering (default 0)
            session: Optionele database session

        Returns:
            List[KnowledgeEntryResponse]: List[Any] van knowledge entries  # TODO(TYPE): replace Any with concrete type
        """
        try:
            async with db_manager.get_session() as session:
                return await self._list_entries_internal(entry_type, limit, offset, session)

        except SQLAlchemyError as e:
            logger.error(f"Database error listing knowledge entries: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing knowledge entries: {e}")
            raise

    async def _list_entries_internal(
        self,
        entry_type: str | None,
        limit: int,
        offset: int,
        session: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> list[KnowledgeEntryResponse]:
        """Internal method for listing entries with session - OPTIMIZED for TAAK 3.2 composite indexes"""
        # Build query - OPTIMIZED to use idx_knowledge_created_type composite index
        stmt = select(KnowledgeEntry)

        if entry_type:
            # Uses idx_knowledge_created_type composite index (created_at, type)
            stmt = stmt.where(KnowledgeEntry.type == entry_type)

        # Order by created_at DESC to leverage idx_knowledge_created_type index
        stmt = stmt.order_by(KnowledgeEntry.created_at.desc()).limit(limit).offset(offset)

        # Execute query
        result = await session.execute(stmt)
        entries = result.scalars().all()

        logger.info(f"Retrieved {len(entries)} knowledge entries (type: {entry_type or 'all'})")

        return [KnowledgeEntryResponse.model_validate(entry) for entry in entries]

    async def get_knowledge_by_type_optimized(
        self, entry_type: str, limit: int = 50, min_confidence: float = 0.0
    ) -> list[KnowledgeEntryResponse]:
        """
        TAAK 3.2: Optimized knowledge retrieval by type with confidence filtering
        Uses idx_knowledge_type_confidence composite index for maximum performance

        Args:
            entry_type: Type of knowledge to retrieve
            limit: Maximum number of entries (default 50)
            min_confidence: Minimum confidence score (default 0.0)

        Returns:
            List[KnowledgeEntryResponse]: Ordered by confidence score DESC
        """
        try:
            async with db_manager.get_session() as session:
                # OPTIMIZED query using idx_knowledge_type_confidence composite index
                stmt = (
                    select(KnowledgeEntry)
                    .where(KnowledgeEntry.type == entry_type)
                    .where(KnowledgeEntry.confidence_score >= min_confidence)
                    .order_by(KnowledgeEntry.confidence_score.desc())
                    .limit(limit)
                )

                result = await session.execute(stmt)
                entries = result.scalars().all()

                logger.info(
                    f"Retrieved {len(entries)} optimized knowledge entries for type '{entry_type}' with min confidence {min_confidence}"
                )
                return [KnowledgeEntryResponse.model_validate(entry) for entry in entries]

        except SQLAlchemyError as e:
            logger.error(f"Database error in optimized knowledge retrieval: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in optimized knowledge retrieval: {e}")
            raise

    async def get_recent_knowledge_optimized(
        self, hours: int = 24, entry_type: str | None = None, limit: int = 100
    ) -> list[KnowledgeEntryResponse]:
        """
        TAAK 3.2: Optimized recent knowledge retrieval
        Uses idx_knowledge_created_type composite index for time-based queries

        Args:
            hours: Number of hours back to search (default 24)
            entry_type: Optional type filter
            limit: Maximum number of entries (default 100)

        Returns:
            List[KnowledgeEntryResponse]: Recent knowledge ordered by created_at DESC
        """
        from datetime import datetime, timedelta

        try:
            async with db_manager.get_session() as session:
                # Calculate cutoff time
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

                # OPTIMIZED query using idx_knowledge_created_type composite index
                stmt = select(KnowledgeEntry).where(KnowledgeEntry.created_at >= cutoff)

                if entry_type:
                    # Uses idx_knowledge_created_type composite index (created_at, type)
                    stmt = stmt.where(KnowledgeEntry.type == entry_type)

                stmt = stmt.order_by(KnowledgeEntry.created_at.desc()).limit(limit)

                result = await session.execute(stmt)
                entries = result.scalars().all()

                logger.info(
                    f"Retrieved {len(entries)} recent knowledge entries from last {hours} hours (type: {entry_type or 'all'})"
                )
                return [KnowledgeEntryResponse.model_validate(entry) for entry in entries]

        except SQLAlchemyError as e:
            logger.error(f"Database error in recent knowledge retrieval: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in recent knowledge retrieval: {e}")
            raise

    async def search_knowledge_optimized(
        self,
        entry_type: str,
        min_confidence: float = 0.5,
        hours_back: int | None = None,
        limit: int = 50,
    ) -> list[KnowledgeEntryResponse]:
        """
        TAAK 3.2: Optimized comprehensive knowledge search
        Uses idx_knowledge_search composite index (type, created_at, confidence_score)

        Args:
            entry_type: Type of knowledge to search
            min_confidence: Minimum confidence score (default 0.5)
            hours_back: Optional time limit in hours
            limit: Maximum number of entries (default 50)

        Returns:
            List[KnowledgeEntryResponse]: Comprehensive search results
        """
        from datetime import datetime, timedelta

        try:
            async with db_manager.get_session() as session:
                # OPTIMIZED query using idx_knowledge_search composite index
                # (type, created_at, confidence_score) - perfect for this query pattern
                stmt = (
                    select(KnowledgeEntry)
                    .where(KnowledgeEntry.type == entry_type)
                    .where(KnowledgeEntry.confidence_score >= min_confidence)
                )

                if hours_back:
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                    stmt = stmt.where(KnowledgeEntry.created_at >= cutoff)

                # Order by confidence DESC, then by created_at DESC
                stmt = stmt.order_by(
                    KnowledgeEntry.confidence_score.desc(),
                    KnowledgeEntry.created_at.desc(),
                ).limit(limit)

                result = await session.execute(stmt)
                entries = result.scalars().all()

                logger.info(
                    f"Optimized search returned {len(entries)} knowledge entries for type '{entry_type}' with min confidence {min_confidence}"
                )
                return [KnowledgeEntryResponse.model_validate(entry) for entry in entries]

        except SQLAlchemyError as e:
            logger.error(f"Database error in optimized knowledge search: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in optimized knowledge search: {e}")
            raise


# Global service instance
_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """Get or create global KnowledgeService instance"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


def create_knowledge_service(
    db_session: Any = None,
    tenant_id: int | None = None,
) -> KnowledgeService:
    """Create new KnowledgeService instance with tenant isolation (ADR-005)."""
    return KnowledgeService(tenant_id=tenant_id)


__all__ = [
    "KnowledgeService",
    "KnowledgeEntryCreate",
    "KnowledgeEntryUpdate",
    "KnowledgeEntryResponse",
    "get_knowledge_service",
    "create_knowledge_service",
]
