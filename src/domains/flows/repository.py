import builtins
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.flows.models import Flow, PiecesCacheMetadata


class FlowRepository:
    """
    Repository for accessing flow data with tenant isolation.
    Async implementation using SQLAlchemy 2.0 style.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def get(self, flow_id: int) -> Flow | None:
        """Get a flow by ID, ensuring it belongs to the tenant."""
        result = await self.db.execute(
            select(Flow).filter(Flow.id == flow_id, Flow.tenant_id == self.tenant_id)
        )
        return result.scalars().first()

    async def get_by_ap_id(self, ap_flow_id: str) -> Flow | None:
        """Get flow by ActivePieces ID."""
        result = await self.db.execute(
            select(Flow).filter(
                Flow.activepieces_flow_id == ap_flow_id,
                Flow.tenant_id == self.tenant_id,
            )
        )
        return result.scalars().first()

    async def list(self, skip: int = 0, limit: int = 100) -> list[Flow]:
        """List flows for this tenant."""
        result = await self.db.execute(
            select(Flow)
            .filter(Flow.tenant_id == self.tenant_id)
            .order_by(desc(Flow.updated_at))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Flow:  # TODO(TYPE): replace Any with concrete type
        """Create a new flow."""
        # Ensure tenant_id is set
        data["tenant_id"] = self.tenant_id

        flow = Flow(**data)
        self.db.add(flow)
        await self.db.flush()
        await self.db.refresh(flow)
        return flow

    async def update(
        self,
        flow_id: int,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Flow | None:  # TODO(TYPE): replace Any with concrete type
        """Update an existing flow."""
        # Note: We must await self.get()
        flow = await self.get(flow_id)
        if not flow:
            return None

        for key, value in data.items():
            if hasattr(flow, key):
                setattr(flow, key, value)

        await self.db.flush()
        await self.db.refresh(flow)
        return flow

    async def delete(self, flow_id: int) -> bool:
        """Delete a flow."""
        flow = await self.get(flow_id)
        if not flow:
            return False

        await self.db.delete(flow)
        await self.db.flush()
        return True

    # =========================================================================
    # Pieces Catalog (Tenant-agnostic but read-only usually)
    # =========================================================================

    async def get_pieces(
        self, search: str | None = None, category: str | None = None
    ) -> builtins.list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get pieces from cache."""
        query = select(PiecesCacheMetadata)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (PiecesCacheMetadata.display_name.ilike(search_term))
                | (PiecesCacheMetadata.description.ilike(search_term))
            )

        # Category filtering is illustrative (would need category column)

        result = await self.db.execute(query)
        pieces = result.scalars().all()

        return [
            {
                "name": p.piece_name,
                "displayName": p.display_name,
                "description": p.description,
                "logoUrl": p.logo_url,
                "version": p.piece_version,
            }
            for p in pieces
        ]

    async def get_piece(self, piece_name: str) -> PiecesCacheMetadata | None:
        """Get detailed piece metadata by name."""
        result = await self.db.execute(
            select(PiecesCacheMetadata).filter(PiecesCacheMetadata.piece_name == piece_name)
        )
        return result.scalars().first()

    async def upsert_piece(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Update or insert piece metadata."""
        result = await self.db.execute(
            select(PiecesCacheMetadata).filter(PiecesCacheMetadata.piece_name == data["piece_name"])
        )
        piece = result.scalars().first()

        if piece:
            for key, value in data.items():
                if hasattr(piece, key):
                    setattr(piece, key, value)
        else:
            piece = PiecesCacheMetadata(**data)
            self.db.add(piece)

        await self.db.flush()
