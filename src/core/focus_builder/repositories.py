from typing import Any, Optional, cast
from collections.abc import Sequence

from loguru import logger
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import get_cache
from src.core.focus_builder.models import FocusBuilderFlow
from src.domains.flows.models import PiecesCacheMetadata as FocusBuilderPieceCache
import builtins

# Cache configuration constants
PIECES_CACHE_KEY = "focus_builder:pieces:all"
PIECES_CACHE_TTL = 3600  # 1 hour
PIECES_SEARCH_CACHE_PREFIX = "focus_builder:pieces:search"
FLOW_CACHE_PREFIX = "focus_builder:flow"


class FlowRepository:
    """
    Repository for FocusBuilderFlow database operations.

    Provides CRUD operations with tenant isolation and optimistic locking.
    """

    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        self.session = session
        self._tenant_id = tenant_id

    async def create(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> FocusBuilderFlow:  # TODO(TYPE): replace Any with concrete type
        """Create a new flow in the database."""
        # Initialize version for optimistic locking
        if "version" not in data:
            data["version"] = 1

        flow = FocusBuilderFlow(**data)
        self.session.add(flow)
        await self.session.flush()
        await self.session.refresh(flow)
        logger.debug(
            "flow_repo_created",
            flow_id=flow.id,
            flow_name=data.get("name"),
            tenant_id=data.get("tenant_id"),
        )
        return flow

    async def get(self, flow_id: int) -> FocusBuilderFlow | None:
        """Get a flow by ID, ensuring it belongs to the tenant."""
        result = await self.session.execute(
            select(FocusBuilderFlow).where(
                and_(
                    FocusBuilderFlow.id == flow_id,
                    FocusBuilderFlow.tenant_id == self._tenant_id,
                )
            )
        )
        flow = result.scalar_one_or_none()
        if flow:
            logger.debug("flow_repo_retrieved", flow_id=flow_id, tenant_id=self._tenant_id)
        else:
            logger.debug(
                "flow_repo_not_found_or_wrong_tenant", flow_id=flow_id, tenant_id=self._tenant_id
            )
        return flow

    async def list(self) -> Sequence[FocusBuilderFlow]:
        """List all flows for the repository's tenant."""
        result = await self.session.execute(
            select(FocusBuilderFlow).where(FocusBuilderFlow.tenant_id == self._tenant_id)
        )
        flows = result.scalars().all()
        logger.debug("flow_repo_listed", tenant_id=self._tenant_id, count=len(flows))
        return flows

    async def update(
        self,
        flow_id: int,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        expected_version: int | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> FocusBuilderFlow | None:
        """
        Update a flow by ID with optional optimistic locking and tenant isolation.

        Args:
            flow_id: ID of the flow to update
            data: Fields to update
            expected_version: If provided, update only if version matches
                              (raises ConflictError if mismatch)

        Returns:
            Updated flow or None if not found (or not owned by tenant)
        """
        # Build WHERE clause with tenant isolation
        conditions = [
            FocusBuilderFlow.id == flow_id,
            FocusBuilderFlow.tenant_id == self._tenant_id,
        ]
        if expected_version is not None:
            conditions.append(FocusBuilderFlow.version == expected_version)
            # Auto-increment version
            data["version"] = expected_version + 1

        stmt = (
            update(FocusBuilderFlow)
            .where(and_(*conditions))
            .values(**data)
            .returning(FocusBuilderFlow)
        )
        result = await self.session.execute(stmt)
        flow = result.scalar_one_or_none()

        if flow:
            logger.debug(
                "flow_repo_updated",
                flow_id=flow_id,
                tenant_id=self._tenant_id,
                updated_fields=list(data.keys()),
                new_version=data.get("version"),
            )
        elif expected_version is not None:
            # Could be not found OR version mismatch
            existing = await self.get(flow_id)
            if existing:
                logger.warning(
                    "flow_repo_version_conflict",
                    flow_id=flow_id,
                    tenant_id=self._tenant_id,
                    expected=expected_version,
                    actual=existing.version,
                )
                raise OptimisticLockError(
                    f"Flow {flow_id} version conflict: "
                    f"expected {expected_version}, got {existing.version}"
                )
            logger.debug("flow_repo_update_not_found", flow_id=flow_id, tenant_id=self._tenant_id)
        else:
            logger.debug("flow_repo_update_not_found", flow_id=flow_id, tenant_id=self._tenant_id)

        return flow

    async def delete(self, flow_id: int) -> bool:
        """Delete a flow by ID, only if it belongs to the tenant."""
        stmt = delete(FocusBuilderFlow).where(
            and_(
                FocusBuilderFlow.id == flow_id,
                FocusBuilderFlow.tenant_id == self._tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        deleted = getattr(result, "rowcount", 0) > 0
        if deleted:
            logger.debug("flow_repo_deleted", flow_id=flow_id, tenant_id=self._tenant_id)
        else:
            logger.debug(
                "flow_repo_delete_not_found_or_wrong_tenant",
                flow_id=flow_id,
                tenant_id=self._tenant_id,
            )
        return deleted

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def batch_create(
        self,
        flows_data: builtins.list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> builtins.list[FocusBuilderFlow]:  # TODO(TYPE): replace Any with concrete type
        """Create multiple flows in a single transaction."""
        created_flows: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for data in flows_data:
            if "version" not in data:
                data["version"] = 1
            flow = FocusBuilderFlow(**data)
            self.session.add(flow)
            created_flows.append(flow)

        await self.session.flush()

        # Refresh to get IDs
        for flow in created_flows:
            await self.session.refresh(flow)

        logger.info("flow_repo_batch_created", count=len(created_flows))
        return created_flows

    async def batch_delete(self, flow_ids: builtins.list[int], tenant_id: int) -> int:
        """
        Delete multiple flows by IDs (with tenant isolation).

        Returns count of deleted flows.
        """
        stmt = delete(FocusBuilderFlow).where(
            and_(
                FocusBuilderFlow.id.in_(flow_ids),
                FocusBuilderFlow.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        deleted_count = getattr(result, "rowcount", 0)
        logger.info(
            "flow_repo_batch_deleted",
            requested=len(flow_ids),
            deleted=deleted_count,
            tenant_id=tenant_id,
        )
        return deleted_count

    async def batch_update_status(
        self, flow_ids: builtins.list[int], tenant_id: int, is_published: bool
    ) -> int:
        """
        Update publish status for multiple flows.

        Returns count of updated flows.
        """
        stmt = (
            update(FocusBuilderFlow)
            .where(
                and_(
                    FocusBuilderFlow.id.in_(flow_ids),
                    FocusBuilderFlow.tenant_id == tenant_id,
                )
            )
            .values(is_published=is_published)
        )
        result = await self.session.execute(stmt)
        updated_count = getattr(result, "rowcount", 0)
        logger.info(
            "flow_repo_batch_status_updated",
            requested=len(flow_ids),
            updated=updated_count,
            is_published=is_published,
            tenant_id=tenant_id,
        )
        return updated_count


class PiecesRepository:
    """
    Repository for FocusBuilderPieceCache database operations.

    Manages the local cache of ActivePieces integration pieces with
    Redis caching layer for performance.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_pieces(self, search: str | None = None) -> list[FocusBuilderPieceCache]:
        """
        Get pieces from cache, optionally filtered by search term.

        Uses Redis cache for full catalog, falls back to DB on miss.
        """
        # Try Redis cache first (only for non-search queries)
        if not search:
            cached = await self._get_cached_pieces()
            if cached is not None:
                return cached

        # Query database
        query = select(FocusBuilderPieceCache)
        if search:
            query = query.where(
                (FocusBuilderPieceCache.display_name.ilike(f"%{search}%"))
                | (FocusBuilderPieceCache.piece_name.ilike(f"%{search}%"))
            )
        result = await self.session.execute(query)
        pieces = list(result.scalars().all())
        logger.debug("pieces_repo_retrieved", count=len(pieces), search=search)

        # Cache full catalog in Redis (only for non-search queries)
        if not search:
            await self._cache_pieces(pieces)

        return pieces

    async def upsert_piece(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> FocusBuilderPieceCache:  # TODO(TYPE): replace Any with concrete type
        """Insert or update a piece in the cache."""
        piece_name = data["piece_name"]
        stmt = select(FocusBuilderPieceCache).where(FocusBuilderPieceCache.piece_name == piece_name)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing piece
            for k, v in data.items():
                setattr(existing, k, v)
            logger.debug("pieces_repo_updated", piece_name=piece_name)
            piece = existing
        else:
            # Create new piece
            piece = FocusBuilderPieceCache(**data)
            self.session.add(piece)
            logger.debug("pieces_repo_created", piece_name=piece_name)

        # Invalidate cache on any modification
        await self._invalidate_cache()

        return piece

    async def get_piece_by_name(self, piece_name: str) -> FocusBuilderPieceCache | None:
        """Get a single piece by name."""
        stmt = select(FocusBuilderPieceCache).where(FocusBuilderPieceCache.piece_name == piece_name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_piece_count(self) -> int:
        """Get total count of cached pieces."""
        from sqlalchemy import func

        stmt = select(func.count(FocusBuilderPieceCache.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    # =========================================================================
    # Redis Caching Layer
    # =========================================================================

    async def _get_cached_pieces(self) -> list[FocusBuilderPieceCache] | None:
        """Retrieve pieces from Redis cache."""
        try:
            cache = await get_cache()
            if not cache.connected:
                return None

            cached_data = await cache.get(PIECES_CACHE_KEY)
            if cached_data is None:
                logger.debug("pieces_cache_miss")
                return None

            # Reconstruct ORM objects from cached dicts
            pieces = [
                FocusBuilderPieceCache(**item)
                for item in cast(list[dict[str, object]], cached_data)
            ]
            logger.debug("pieces_cache_hit", count=len(pieces))
            return pieces

        except Exception as e:
            logger.warning("pieces_cache_read_error", error=str(e))
            return None

    async def _cache_pieces(self, pieces: list[FocusBuilderPieceCache]) -> None:
        """Store pieces in Redis cache."""
        try:
            cache = await get_cache()
            if not cache.connected:
                return

            # Convert ORM objects to dicts for serialization
            pieces_data = [
                {
                    "id": p.id,
                    "piece_name": p.piece_name,
                    "display_name": p.display_name,
                    "logo_url": p.logo_url,
                    "actions": p.actions,
                    "triggers": p.triggers,
                }
                for p in pieces
            ]

            await cache.set(PIECES_CACHE_KEY, pieces_data, ttl=PIECES_CACHE_TTL)
            logger.debug("pieces_cached", count=len(pieces), ttl=PIECES_CACHE_TTL)

        except Exception as e:
            logger.warning("pieces_cache_write_error", error=str(e))

    async def _invalidate_cache(self) -> None:
        """Invalidate pieces cache on data modification."""
        try:
            cache = await get_cache()
            if cache.connected:
                await cache.delete(PIECES_CACHE_KEY)
                await cache.clear_pattern(f"{PIECES_SEARCH_CACHE_PREFIX}:*")
                logger.debug("pieces_cache_invalidated")
        except Exception as e:
            logger.warning("pieces_cache_invalidate_error", error=str(e))


class OptimisticLockError(Exception):
    """Raised when optimistic lock version conflict occurs."""

    pass
