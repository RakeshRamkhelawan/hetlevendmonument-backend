"""
KnowledgeService - Production Implementation
Service laag voor kennisbeheer CRUD operaties zoals gespecificeerd in FASE 3 STAP 3.1.2
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_database_session
from src.core.knowledge.models import KnowledgeEntry

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
    entry_metadata: dict[str, Any] | None = Field(default=None, description="Updated metadata")  # TODO(TYPE): replace Any with concrete type
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
    Implementeert asynchrone CRUD operaties zoals gespecificeerd in plan
    """

    def __init__(self) -> None:
        """Initialize the KnowledgeService"""
        logger.info("KnowledgeService initialized")

    async def create_entry(
        self, entry_data: KnowledgeEntryCreate, session: AsyncSession | None = None
    ) -> KnowledgeEntryResponse:
        """
        Creeer een nieuwe knowledge entry zoals gespecificeerd in plan

        Args:
            entry_data: KnowledgeEntryCreate model met entry data
            session: Optionele database session

        Returns:
            KnowledgeEntryResponse: Created knowledge entry

        Raises:
            SQLAlchemyError: Database operation errors
        """
        try:
            # Get database session
            if session is None:
                session = await get_database_session().__anext__()

            if session is None:
                raise ValueError("Failed to obtain database session")
            assert session is not None  # Type narrowing for Pyright

            # Create new knowledge entry
            new_entry = KnowledgeEntry(
                content=entry_data.content,
                type=entry_data.type,
                entry_metadata=entry_data.entry_metadata,
                confidence_score=entry_data.confidence_score,
            )

            # Add to session and commit
            if session is not None:
                session.add(new_entry)
                await session.commit()
                await session.refresh(new_entry)
            else:
                raise ValueError("Database session is None")

            logger.info(f"Created knowledge entry {new_entry.id} of type '{new_entry.type}'")

            return KnowledgeEntryResponse.model_validate(new_entry)

        except SQLAlchemyError as e:
            logger.error(f"Database error creating knowledge entry: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating knowledge entry: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise

    async def get_entry(
        self, entry_id: int, session: AsyncSession | None = None
    ) -> KnowledgeEntryResponse | None:
        """
        Haal een knowledge entry op via ID zoals gespecificeerd in plan

        Args:
            entry_id: ID van de knowledge entry
            session: Optionele database session

        Returns:
            Optional[KnowledgeEntryResponse]: Knowledge entry of None als niet gevonden
        """
        try:
            # Get database session
            if session is None:
                session = await get_database_session().__anext__()

            if session is None:
                raise ValueError("Failed to obtain database session")

            # Query for knowledge entry
            if session is None:
                raise ValueError("Database session is None")
            stmt = select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                logger.info(f"Retrieved knowledge entry {entry_id}")
                return KnowledgeEntryResponse.model_validate(entry)
            else:
                logger.warning(f"Knowledge entry {entry_id} not found")
                return None

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving knowledge entry {entry_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving knowledge entry {entry_id}: {e}")
            raise

    async def update_entry(
        self,
        entry_id: int,
        update_data: KnowledgeEntryUpdate,
        session: AsyncSession | None = None,
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
            # Get database session
            if session is None:
                session = await get_database_session().__anext__()

            if session is None:
                raise ValueError("Failed to obtain database session")

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
                return await self.get_entry(entry_id, session)

            # Add updated_at timestamp
            update_dict["updated_at"] = datetime.now(timezone.utc)

            # Execute update
            if session is None:
                raise ValueError("Database session is None")
            stmt = update(KnowledgeEntry).where(KnowledgeEntry.id == entry_id).values(**update_dict)
            result = await session.execute(stmt)

            if getattr(result, "rowcount", 0) == 0:
                logger.warning(f"Knowledge entry {entry_id} not found for update")
                return None

            await session.commit()

            logger.info(f"Updated knowledge entry {entry_id}")

            # Return updated entry
            return await self.get_entry(entry_id, session)

        except SQLAlchemyError as e:
            logger.error(f"Database error updating knowledge entry {entry_id}: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating knowledge entry {entry_id}: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise

    async def delete_entry(self, entry_id: int, session: AsyncSession | None = None) -> bool:
        """
        Verwijder een knowledge entry zoals gespecificeerd in plan

        Args:
            entry_id: ID van de knowledge entry
            session: Optionele database session

        Returns:
            bool: True als succesvol verwijderd, False als niet gevonden
        """
        try:
            # Get database session
            if session is None:
                session = await get_database_session().__anext__()

            if session is None:
                raise ValueError("Failed to obtain database session")

            # Execute delete
            if session is None:
                raise ValueError("Database session is None")
            stmt = delete(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
            result = await session.execute(stmt)

            if getattr(result, "rowcount", 0) == 0:
                logger.warning(f"Knowledge entry {entry_id} not found for deletion")
                return False

            await session.commit()

            logger.info(f"Deleted knowledge entry {entry_id}")
            return True

        except SQLAlchemyError as e:
            logger.error(f"Database error deleting knowledge entry {entry_id}: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting knowledge entry {entry_id}: {e}")
            if isinstance(session, AsyncSession):
                await session.rollback()
            raise

    async def list_entries(
        self,
        entry_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
        session: AsyncSession | None = None,
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
            # Get database session
            if session is None:
                session = await get_database_session().__anext__()

            if session is None:
                raise ValueError("Failed to obtain database session")

            # Build query
            if session is None:
                raise ValueError("Database session is None")
            stmt = select(KnowledgeEntry)

            if entry_type:
                stmt = stmt.where(KnowledgeEntry.type == entry_type)

            stmt = stmt.order_by(KnowledgeEntry.created_at.desc()).limit(limit).offset(offset)

            # Execute query
            result = await session.execute(stmt)
            entries = result.scalars().all()

            logger.info(f"Retrieved {len(entries)} knowledge entries (type: {entry_type or 'all'})")

            return [KnowledgeEntryResponse.model_validate(entry) for entry in entries]

        except SQLAlchemyError as e:
            logger.error(f"Database error listing knowledge entries: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing knowledge entries: {e}")
            raise


# Global service instance
_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """Get or create global KnowledgeService instance"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


def create_knowledge_service() -> KnowledgeService:
    """Create new KnowledgeService instance"""
    return KnowledgeService()


__all__ = [
    "KnowledgeService",
    "KnowledgeEntryCreate",
    "KnowledgeEntryUpdate",
    "KnowledgeEntryResponse",
    "get_knowledge_service",
    "create_knowledge_service",
]
