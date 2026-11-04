"""
Repository layer for DomainPack model
Handles all database operations for domain packs
"""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DomainPack
from .schemas import DomainPackCreate, DomainPackUpdate


class DomainPackRepository:
    """Repository for domain pack database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: int, data: DomainPackCreate) -> DomainPack:
        """
        Create a new domain pack

        Args:
            tenant_id: Current tenant ID
            data: DomainPackCreate schema with data

        Returns:
            Created DomainPack model
        """
        pack = DomainPack(
            tenant_id=tenant_id,
            name=data.name,
            department=data.department,
            version=data.version,
            description=data.description,
            capabilities=data.capabilities,
            input_contracts=data.input_contracts,
            output_contracts=data.output_contracts,
            status=data.status or "active",
        )
        self.db.add(pack)
        await self.db.flush()
        await self.db.refresh(pack)
        return pack

    async def get_by_id(self, tenant_id: int, pack_id: UUID) -> DomainPack | None:
        """
        Get domain pack by ID with tenant filtering

        Args:
            tenant_id: Current tenant ID (for scoping)
            pack_id: Domain pack ID

        Returns:
            DomainPack if found and belongs to tenant, None otherwise
        """
        stmt = select(DomainPack).where(
            and_(DomainPack.id == pack_id, DomainPack.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: int) -> list[DomainPack]:
        """
        List all domain packs for a tenant

        Args:
            tenant_id: Current tenant ID

        Returns: List[Any] of DomainPack objects for this tenant  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(DomainPack)
            .where(DomainPack.tenant_id == tenant_id)
            .order_by(DomainPack.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        tenant_id: int,
        pack_id: UUID,
        data: DomainPackUpdate,
    ) -> DomainPack | None:
        """
        Update a domain pack

        Args:
            tenant_id: Current tenant ID (for scoping)
            pack_id: Domain pack ID to update
            data: DomainPackUpdate schema with new data

        Returns:
            Updated DomainPack or None if not found or wrong tenant
        """
        pack = await self.get_by_id(tenant_id, pack_id)
        if not pack:
            return None

        # Update only provided fields
        if data.department is not None:
            pack.department = data.department
        if data.description is not None:
            pack.description = data.description
        if data.capabilities is not None:
            pack.capabilities = data.capabilities
        if data.input_contracts is not None:
            pack.input_contracts = data.input_contracts
        if data.output_contracts is not None:
            pack.output_contracts = data.output_contracts
        if data.status is not None:
            pack.status = data.status

        await self.db.flush()
        await self.db.refresh(pack)
        return pack

    async def archive(self, tenant_id: int, pack_id: UUID) -> DomainPack | None:
        """
        Archive (deprecate) a domain pack by setting status to 'deprecated'

        Args:
            tenant_id: Current tenant ID (for scoping)
            pack_id: Domain pack ID to archive

        Returns:
            Updated DomainPack or None if not found
        """
        pack = await self.get_by_id(tenant_id, pack_id)
        if not pack:
            return None

        pack.status = "deprecated"
        await self.db.flush()
        await self.db.refresh(pack)
        return pack

    async def search(self, tenant_id: int, query: str) -> list[DomainPack]:
        """
        Search domain packs by name or department

        Args:
            tenant_id: Current tenant ID
            query: Search query string

        Returns: List[Any] of matching DomainPack objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(DomainPack)
            .where(
                and_(
                    DomainPack.tenant_id == tenant_id,
                    or_(
                        DomainPack.name.ilike(f"%{query}%"),
                        DomainPack.department.ilike(f"%{query}%"),
                    ),
                )
            )
            .order_by(DomainPack.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def commit(self) -> None:
        """Commit database transaction"""
        await self.db.commit()

    async def rollback(self) -> None:
        """Rollback database transaction"""
        await self.db.rollback()
