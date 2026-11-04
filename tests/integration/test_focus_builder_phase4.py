"""
Phase 4 Integration Tests: Caching, Batch Operations, and Optimistic Locking

Tests for FocusBuilder performance and concurrency features implemented in Phase 4.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.focus_builder.models import FocusBuilderFlow
from src.domains.flows.models import PiecesCacheMetadata as FocusBuilderPieceCache
from src.core.focus_builder.repositories import (
    FlowRepository,
    OptimisticLockError,
    PiecesRepository,
)


@pytest.fixture
async def db_session(postgres_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Use shared PostgreSQL fixture from conftest (tables already created)."""
    yield postgres_session


@pytest.fixture
def flow_repo(db_session: AsyncSession) -> FlowRepository:
    """Create FlowRepository instance."""
    return FlowRepository(db_session, tenant_id=1)


@pytest.fixture
def pieces_repo(db_session: AsyncSession) -> PiecesRepository:
    """Create PiecesRepository instance."""
    return PiecesRepository(db_session)


@pytest.fixture
def mock_cache() -> MagicMock:
    """Mock Redis cache for testing cache behavior."""
    cache = MagicMock()
    cache.connected = True
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.clear_pattern = AsyncMock(return_value=1)
    return cache


# =============================================================================
# Optimistic Locking Tests (TEST-03)
# =============================================================================


class TestOptimisticLocking:
    """Tests for optimistic locking on flow updates."""

    @pytest.mark.asyncio
    async def test_update_with_correct_version(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Update succeeds when expected version matches."""
        # Create flow
        flow = await flow_repo.create(
            {
                "name": "Test Flow",
                "tenant_id": 1,
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )
        await db_session.commit()

        initial_version = flow.version
        assert initial_version == 1

        # Update with correct version
        updated = await flow_repo.update(flow.id, {"name": "Updated Flow"}, expected_version=1)
        await db_session.commit()

        assert updated is not None
        assert updated.name == "Updated Flow"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_with_wrong_version_raises_error(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Update raises OptimisticLockError when version mismatch."""
        # Create flow
        flow = await flow_repo.create(
            {
                "name": "Test Flow",
                "tenant_id": 1,
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )
        await db_session.commit()

        # Try to update with wrong version
        with pytest.raises(OptimisticLockError) as exc_info:
            await flow_repo.update(
                flow.id,
                {"name": "Should Fail"},
                expected_version=99,  # Wrong version
            )

        assert "version conflict" in str(exc_info.value).lower()
        assert "expected 99" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_concurrent_updates_one_fails(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Simulate concurrent updates - second one fails."""
        # Create flow
        flow = await flow_repo.create(
            {
                "name": "Original",
                "tenant_id": 1,
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )
        await db_session.commit()
        flow_id = flow.id

        # First update succeeds (version 1 -> 2)
        await flow_repo.update(flow_id, {"name": "First Update"}, expected_version=1)
        await db_session.commit()

        # Second update fails (still using version 1)
        with pytest.raises(OptimisticLockError):
            await flow_repo.update(
                flow_id,
                {"name": "Second Update"},
                expected_version=1,  # Stale version
            )

    @pytest.mark.asyncio
    async def test_update_without_version_always_succeeds(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Update without expected_version skips version check."""
        flow = await flow_repo.create(
            {
                "name": "Test Flow",
                "tenant_id": 1,
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )
        await db_session.commit()

        # Update without version check
        updated = await flow_repo.update(flow.id, {"name": "No Version Check"})
        await db_session.commit()

        assert updated is not None
        assert updated.name == "No Version Check"


# =============================================================================
# Batch Operations Tests (TEST-02)
# =============================================================================


class TestBatchOperations:
    """Tests for batch CRUD operations."""

    @pytest.mark.asyncio
    async def test_batch_create_multiple_flows(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Create multiple flows in single transaction."""
        flows_data = [
            {
                "name": f"Batch Flow {i}",
                "tenant_id": 1,
                "react_flow_graph": {"nodes": [], "edges": []},
            }
            for i in range(5)
        ]

        created = await flow_repo.batch_create(flows_data)
        await db_session.commit()

        assert len(created) == 5
        for i, flow in enumerate(created):
            assert flow.id is not None
            assert flow.name == f"Batch Flow {i}"
            assert flow.version == 1

    @pytest.mark.asyncio
    async def test_batch_delete_with_tenant_isolation(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Batch delete only affects flows in specified tenant."""
        # Create flows in tenant 1
        t1_flows = await flow_repo.batch_create(
            [
                {"name": "T1 Flow 1", "tenant_id": 1, "react_flow_graph": {}},
                {"name": "T1 Flow 2", "tenant_id": 1, "react_flow_graph": {}},
            ]
        )
        # Create flow in tenant 2
        t2_flow = await flow_repo.create(
            {
                "name": "T2 Flow",
                "tenant_id": 2,
                "react_flow_graph": {},
            }
        )
        await db_session.commit()

        t1_ids = [f.id for f in t1_flows]

        # Delete tenant 1 flows
        deleted_count = await flow_repo.batch_delete(t1_ids, tenant_id=1)
        await db_session.commit()

        assert deleted_count == 2

        # Verify tenant 2 flow still exists (use fresh repo with tenant 2)
        t2_repo = FlowRepository(db_session, tenant_id=2)
        t2_exists = await t2_repo.get(t2_flow.id)
        assert t2_exists is not None

    @pytest.mark.asyncio
    async def test_batch_delete_wrong_tenant_deletes_nothing(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Batch delete with wrong tenant_id deletes nothing."""
        flow = await flow_repo.create(
            {
                "name": "Protected Flow",
                "tenant_id": 1,
                "react_flow_graph": {},
            }
        )
        await db_session.commit()

        # Try delete with wrong tenant
        deleted_count = await flow_repo.batch_delete([flow.id], tenant_id=999)
        await db_session.commit()

        assert deleted_count == 0

        # Flow still exists
        exists = await flow_repo.get(flow.id)
        assert exists is not None

    @pytest.mark.asyncio
    async def test_batch_update_status(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Batch update publish status for multiple flows."""
        flows = await flow_repo.batch_create(
            [{"name": f"Flow {i}", "tenant_id": 1, "react_flow_graph": {}} for i in range(3)]
        )
        await db_session.commit()

        flow_ids = [f.id for f in flows]

        # Publish all
        updated = await flow_repo.batch_update_status(flow_ids, tenant_id=1, is_published=True)
        await db_session.commit()

        assert updated == 3

        # Verify all published
        for fid in flow_ids:
            f = await flow_repo.get(fid)
            assert f is not None
            assert f.is_published is True


# =============================================================================
# Caching Tests (TEST-01)
# =============================================================================


class TestPiecesCaching:
    """Tests for Redis caching in PiecesRepository."""

    @pytest.mark.asyncio
    async def test_cache_miss_queries_database(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession, mock_cache: MagicMock
    ) -> None:
        """On cache miss, repository queries database."""
        # Insert piece directly
        piece = FocusBuilderPieceCache(
            piece_name="test-piece",
            display_name="Test Piece",
            logo_url=None,
            actions={},
            triggers={},
        )
        db_session.add(piece)
        await db_session.commit()

        with patch("src.core.focus_builder.repositories.get_cache") as mock_get:
            mock_cache.get = AsyncMock(return_value=None)  # Cache miss
            mock_get.return_value = mock_cache

            pieces = await pieces_repo.get_pieces()

            assert len(pieces) == 1
            assert pieces[0].piece_name == "test-piece"
            mock_cache.get.assert_called_once()
            mock_cache.set.assert_called_once()  # Should cache result

    @pytest.mark.asyncio
    async def test_cache_hit_skips_database(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession, mock_cache: MagicMock
    ) -> None:
        """On cache hit, repository returns cached data without DB query."""
        cached_data = [
            {
                "id": 1,
                "piece_name": "cached-piece",
                "display_name": "Cached Piece",
                "logo_url": None,
                "actions": {},
                "triggers": {},
            }
        ]

        with patch("src.core.focus_builder.repositories.get_cache") as mock_get:
            mock_cache.get = AsyncMock(return_value=cached_data)
            mock_get.return_value = mock_cache

            pieces = await pieces_repo.get_pieces()

            assert len(pieces) == 1
            assert pieces[0].piece_name == "cached-piece"
            mock_cache.set.assert_not_called()  # No need to re-cache

    @pytest.mark.asyncio
    async def test_upsert_invalidates_cache(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession, mock_cache: MagicMock
    ) -> None:
        """Upserting a piece invalidates the cache."""
        with patch("src.core.focus_builder.repositories.get_cache") as mock_get:
            mock_get.return_value = mock_cache

            await pieces_repo.upsert_piece(
                {
                    "piece_name": "new-piece",
                    "display_name": "New Piece",
                }
            )
            await db_session.commit()

            mock_cache.delete.assert_called()
            mock_cache.clear_pattern.assert_called()

    @pytest.mark.asyncio
    async def test_search_bypasses_cache(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession, mock_cache: MagicMock
    ) -> None:
        """Search queries bypass cache and hit database."""
        piece = FocusBuilderPieceCache(
            piece_name="searchable-piece",
            display_name="Searchable Piece",
        )
        db_session.add(piece)
        await db_session.commit()

        with patch("src.core.focus_builder.repositories.get_cache") as mock_get:
            mock_get.return_value = mock_cache

            pieces = await pieces_repo.get_pieces(search="searchable")

            assert len(pieces) == 1
            # Cache should NOT be checked for search queries
            mock_cache.get.assert_not_called()


# =============================================================================
# End-to-End Flow Lifecycle (TEST-04)
# =============================================================================


class TestFlowLifecycle:
    """End-to-end tests for flow lifecycle with Phase 4 features."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_versioning(
        self, flow_repo: FlowRepository, db_session: AsyncSession
    ) -> None:
        """Test complete flow lifecycle tracking versions."""
        # Create
        flow = await flow_repo.create(
            {
                "name": "Lifecycle Flow",
                "tenant_id": 1,
                "react_flow_graph": {
                    "nodes": [{"id": "1", "type": "trigger"}],
                    "edges": [],
                },
            }
        )
        await db_session.commit()
        assert flow.version == 1

        # Update 1
        updated1 = await flow_repo.update(flow.id, {"name": "Updated Once"}, expected_version=1)
        await db_session.commit()
        assert updated1 is not None
        assert updated1.version == 2

        # Update 2
        updated2 = await flow_repo.update(flow.id, {"is_published": True}, expected_version=2)
        await db_session.commit()
        assert updated2 is not None
        assert updated2.version == 3
        assert updated2.is_published is True

        # Delete
        deleted = await flow_repo.delete(flow.id)
        await db_session.commit()
        assert deleted is True

        # Verify gone
        gone = await flow_repo.get(flow.id)
        assert gone is None

    @pytest.mark.asyncio
    async def test_piece_count(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession
    ) -> None:
        """Test piece count method."""
        # Initially empty
        count = await pieces_repo.get_piece_count()
        assert count == 0

        # Add pieces
        for i in range(3):
            await pieces_repo.upsert_piece(
                {
                    "piece_name": f"piece-{i}",
                    "display_name": f"Piece {i}",
                }
            )
        await db_session.commit()

        count = await pieces_repo.get_piece_count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_piece_by_name(
        self, pieces_repo: PiecesRepository, db_session: AsyncSession
    ) -> None:
        """Test get single piece by name."""
        await pieces_repo.upsert_piece(
            {
                "piece_name": "specific-piece",
                "display_name": "Specific Piece",
                "actions": {"action1": {}},
            }
        )
        await db_session.commit()

        piece = await pieces_repo.get_piece_by_name("specific-piece")
        assert piece is not None
        assert piece.display_name == "Specific Piece"

        # Non-existent
        missing = await pieces_repo.get_piece_by_name("nonexistent")
        assert missing is None
