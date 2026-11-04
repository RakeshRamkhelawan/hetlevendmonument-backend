"""
Repository layer for ProcedureMetadata model
Handles all database operations for procedure metadata
"""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ProcedureMetadata
from .schemas import ProcedureMetadataCreate, ProcedureMetadataUpdate


class ProcedureMetadataRepository:
    """Repository for procedure metadata database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: UUID, data: ProcedureMetadataCreate) -> ProcedureMetadata:
        """
        Create new procedure metadata

        Args:
            tenant_id: Current tenant ID
            data: ProcedureMetadataCreate schema

        Returns:
            Created ProcedureMetadata model
        """
        metadata = ProcedureMetadata(
            tenant_id=tenant_id,
            flow_id=data.flow_id,
            domain_pack_id=data.domain_pack_id,
            category=data.category,
            description=data.description,
            intent_tags=data.intent_tags,
            prerequisites=data.prerequisites,
            estimated_duration_minutes=data.estimated_duration_minutes,
            is_platform_template=data.is_platform_template,
            procedure_metadata=data.metadata_json,
        )
        self.db.add(metadata)
        await self.db.flush()
        await self.db.refresh(metadata)
        return metadata

    async def get_by_id(self, tenant_id: UUID, metadata_id: UUID) -> ProcedureMetadata | None:
        """
        Get procedure metadata by ID with tenant filtering

        Args:
            tenant_id: Current tenant ID (for scoping)
            metadata_id: Procedure metadata ID

        Returns:
            ProcedureMetadata if found and belongs to tenant, None otherwise
        """
        stmt = select(ProcedureMetadata).where(
            and_(
                ProcedureMetadata.id == metadata_id,
                ProcedureMetadata.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_flow_id(self, tenant_id: UUID, flow_id: UUID) -> ProcedureMetadata | None:
        """
        Get procedure metadata by flow_id with tenant filtering

        Args:
            tenant_id: Current tenant ID (for scoping)
            flow_id: FocusBuilderFlow ID

        Returns:
            ProcedureMetadata if found, None otherwise
        """
        stmt = select(ProcedureMetadata).where(
            and_(
                ProcedureMetadata.flow_id == flow_id,
                ProcedureMetadata.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_domain_pack(
        self, tenant_id: UUID, domain_pack_id: UUID
    ) -> list[ProcedureMetadata]:
        """
        List all procedures in a domain pack

        Args:
            tenant_id: Current tenant ID (for scoping)
            domain_pack_id: Domain pack ID to filter by

        Returns: List[Any] of ProcedureMetadata objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureMetadata)
            .where(
                and_(
                    ProcedureMetadata.tenant_id == tenant_id,
                    ProcedureMetadata.domain_pack_id == domain_pack_id,
                )
            )
            .order_by(ProcedureMetadata.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[ProcedureMetadata]:
        """
        List all procedures for a tenant with pagination

        Args:
            tenant_id: Current tenant ID
            skip: Number of records to skip (pagination)
            limit: Maximum records to return

        Returns: List[Any] of ProcedureMetadata objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureMetadata)
            .where(ProcedureMetadata.tenant_id == tenant_id)
            .order_by(ProcedureMetadata.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search_by_intent_tags(
        self, tenant_id: UUID, tags: list[str]
    ) -> list[ProcedureMetadata]:
        """
        Search procedures by intent tags using PostgreSQL GIN index
        Uses array overlap operator (@>)

        Args:
            tenant_id: Current tenant ID (for scoping)
            tags: List[Any] of tags to search for (ANY match)  # TODO(TYPE): replace Any with concrete type

        Returns: List[Any] of matching ProcedureMetadata objects  # TODO(TYPE): replace Any with concrete type
        """
        if not tags:
            return []

        # Check database dialect for compatibility
        dialect_name = self.db.bind.dialect.name if self.db.bind else "postgresql"

        if dialect_name == "postgresql":
            # Use PostgreSQL array overlap operator (&&) for efficient GIN index search
            stmt = (
                select(ProcedureMetadata)
                .where(
                    and_(
                        ProcedureMetadata.tenant_id == tenant_id,
                        ProcedureMetadata.intent_tags.overlap(tags),
                    )
                )
                .order_by(ProcedureMetadata.created_at.desc())
            )

            result = await self.db.execute(stmt)
            return list(result.scalars().all())
        else:
            # SQLite fallback: Fetch all and filter in Python
            stmt = (
                select(ProcedureMetadata)
                .where(ProcedureMetadata.tenant_id == tenant_id)
                .order_by(ProcedureMetadata.created_at.desc())
            )

            result = await self.db.execute(stmt)
            all_procedures = list(result.scalars().all())

            # Filter by tag overlap in Python
            return [proc for proc in all_procedures if any(tag in proc.intent_tags for tag in tags)]

    async def search_by_category(self, tenant_id: UUID, category: str) -> list[ProcedureMetadata]:
        """
        Search procedures by category

        Args:
            tenant_id: Current tenant ID
            category: Category to search for

        Returns: List[Any] of matching ProcedureMetadata objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureMetadata)
            .where(
                and_(
                    ProcedureMetadata.tenant_id == tenant_id,
                    ProcedureMetadata.category.ilike(f"%{category}%"),
                )
            )
            .order_by(ProcedureMetadata.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        tenant_id: UUID,
        tags: list[str] | None = None,
        category: str | None = None,
        domain_pack_id: UUID | None = None,
        is_platform_template: bool | None = None,
    ) -> list[ProcedureMetadata]:
        """
        Complex search with multiple filters

        Args:
            tenant_id: Current tenant ID
            tags: Intent tags to filter by (any match)
            category: Category to filter by
            domain_pack_id: Domain pack to filter by
            is_platform_template: Filter by template status

        Returns: List[Any] of matching ProcedureMetadata objects  # TODO(TYPE): replace Any with concrete type
        """
        dialect_name = self.db.bind.dialect.name if self.db.bind else "postgresql"
        conditions = [ProcedureMetadata.tenant_id == tenant_id]

        # Tags filtering: Use dialect-specific approach
        tags_filter_in_python = False
        if tags and dialect_name != "postgresql":
            # For SQLite: We'll filter in Python after fetching
            tags_filter_in_python = True
        elif tags:
            # For PostgreSQL: Use array overlap operator
            conditions.append(ProcedureMetadata.intent_tags.overlap(tags))

        if category:
            conditions.append(ProcedureMetadata.category.ilike(f"%{category}%"))

        if domain_pack_id:
            conditions.append(ProcedureMetadata.domain_pack_id == domain_pack_id)

        if is_platform_template is not None:
            conditions.append(ProcedureMetadata.is_platform_template == is_platform_template)

        stmt = (
            select(ProcedureMetadata)
            .where(and_(*conditions))
            .order_by(ProcedureMetadata.created_at.desc())
        )

        result = await self.db.execute(stmt)
        procedures = list(result.scalars().all())

        # Apply tags filter in Python for SQLite
        if tags_filter_in_python:
            procedures = [
                proc for proc in procedures if any(tag in proc.intent_tags for tag in (tags or []))
            ]

        return procedures

    async def update(
        self, tenant_id: UUID, metadata_id: UUID, data: ProcedureMetadataUpdate
    ) -> ProcedureMetadata | None:
        """
        Update procedure metadata

        Args:
            tenant_id: Current tenant ID (for scoping)
            metadata_id: Metadata ID to update
            data: Update data

        Returns:
            Updated ProcedureMetadata or None if not found
        """
        metadata = await self.get_by_id(tenant_id, metadata_id)
        if not metadata:
            return None

        # Update only provided fields
        if data.description is not None:
            metadata.description = data.description
        if data.intent_tags is not None:
            metadata.intent_tags = data.intent_tags
        if data.prerequisites is not None:
            metadata.prerequisites = data.prerequisites
        if data.estimated_duration_minutes is not None:
            metadata.estimated_duration_minutes = data.estimated_duration_minutes
        if data.is_platform_template is not None:
            metadata.is_platform_template = data.is_platform_template
        if data.metadata_json is not None:
            metadata.procedure_metadata = data.metadata_json

        await self.db.flush()
        await self.db.refresh(metadata)
        return metadata

    async def get_count(self, tenant_id: UUID, domain_pack_id: UUID | None = None) -> int:
        """
        Get count of procedures

        Args:
            tenant_id: Current tenant ID
            domain_pack_id: Optional domain pack filter

        Returns:
            Count of matching procedures
        """
        conditions = [ProcedureMetadata.tenant_id == tenant_id]
        if domain_pack_id:
            conditions.append(ProcedureMetadata.domain_pack_id == domain_pack_id)

        stmt = select(func.count()).select_from(ProcedureMetadata).where(and_(*conditions))
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def commit(self) -> None:
        """Commit database transaction"""
        await self.db.commit()

    async def rollback(self) -> None:
        """Rollback database transaction"""
        await self.db.rollback()
