"""
Tests for Canvas Revision Manager.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.canvas.ot_engine import Operation, OperationType
from src.domains.canvas.revision_manager import Revision, RevisionManager, SyncState


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_operation():
    """Create a sample operation."""
    return Operation(
        type=OperationType.UPDATE_BLOCK,
        target_id=uuid4(),
        data={"text": "Hello World"},
    )


@pytest.fixture
def revision_manager_with_mocks(mock_db):
    """Create revision manager with mocked dependencies."""
    return RevisionManager(db=mock_db)


class TestRevision:
    """Test Revision dataclass."""

    def test_revision_creation(self, sample_operation):
        """Test basic revision creation."""
        revision = Revision(
            revision_number=1,
            operation=sample_operation,
            client_id="client-123",
            timestamp=datetime.now(timezone.utc),
        )

        assert revision.revision_number == 1
        assert revision.client_id == "client-123"
        assert revision.operation.type == OperationType.UPDATE_BLOCK

    def test_revision_with_transformation(self, sample_operation):
        """Test revision with transformation metadata."""
        revision = Revision(
            revision_number=2,
            operation=sample_operation,
            client_id="client-123",
            timestamp=datetime.now(timezone.utc),
            transformed_from=1,
            transformation_log=["Transformed against server op 1"],
        )

        assert revision.transformed_from == 1
        assert len(revision.transformation_log) == 1


class TestSyncState:
    """Test SyncState dataclass."""

    def test_sync_state_creation(self):
        """Test sync state creation."""
        canvas_id = uuid4()
        state = SyncState(
            client_id="client-123",
            canvas_id=canvas_id,
            last_revision=5,
        )

        assert state.client_id == "client-123"
        assert state.canvas_id == canvas_id
        assert state.last_revision == 5
        assert state.pending_operations == []

    def test_sync_state_with_pending(self, sample_operation):
        """Test sync state with pending operations."""
        state = SyncState(
            client_id="client-123",
            canvas_id=uuid4(),
            last_revision=5,
            pending_operations=[sample_operation],
        )

        assert len(state.pending_operations) == 1


class TestRevisionManagerAddOperation:
    """Test adding operations."""

    async def test_add_operation_increments_revision(self, mock_db, sample_operation):
        """Adding operation returns new revision number."""
        # Mock the database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing operations
        mock_db.execute.return_value = mock_result

        manager = RevisionManager(db=mock_db)

        # Mock the database commit
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await manager.add_operation(
            canvas_id=uuid4(),
            operation=sample_operation,
            client_id="client-123",
        )

        assert result >= 1  # Should return a valid revision number

    async def test_add_transformed_operation(self, mock_db, sample_operation):
        """Add operation with transformation metadata."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        manager = RevisionManager(db=mock_db)

        result = await manager.add_operation(
            canvas_id=uuid4(),
            operation=sample_operation,
            client_id="client-123",
            transformed_from=1,
            transformation_log=["Merged field changes"],
        )

        assert result >= 1


class TestRevisionManagerGetOperations:
    """Test getting operations from history."""

    async def test_get_operations_since_revision(self, mock_db):
        """Get operations after a specific revision."""
        canvas_id = uuid4()

        # Create mock operations from DB
        mock_ops = [
            MagicMock(
                revision=3,
                operation_type="update_block",
                operation_data={"text": "Rev 3"},
                client_id="client-1",
            ),
            MagicMock(
                revision=4,
                operation_type="update_block",
                operation_data={"text": "Rev 4"},
                client_id="client-2",
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_ops
        mock_db.execute.return_value = mock_result

        manager = RevisionManager(db=mock_db)
        operations = await manager.get_operations_since(
            canvas_id=canvas_id,
            revision=2,
        )

        assert len(operations) == 2
        mock_db.execute.assert_called_once()

    async def test_get_empty_operations(self, mock_db):
        """Get operations when none exist."""
        canvas_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        manager = RevisionManager(db=mock_db)
        operations = await manager.get_operations_since(
            canvas_id=canvas_id,
            revision=10,
        )

        assert len(operations) == 0


class TestRevisionManagerClientState:
    """Test client sync state management."""

    async def test_register_client(self, mock_db):
        """Register a new client sync state."""
        canvas_id = uuid4()
        client_id = "client-abc"

        manager = RevisionManager(db=mock_db)

        manager.register_client(
            client_id=client_id,
            canvas_id=canvas_id,
        )

        # Update to revision 5
        manager.update_client_revision(client_id, 5)

        state = manager._client_states.get(client_id)
        assert state is not None
        assert state.client_id == client_id
        assert state.canvas_id == canvas_id
        assert state.last_revision == 5

    async def test_update_client_sync(self, mock_db):
        """Update existing client sync state."""
        canvas_id = uuid4()
        client_id = "client-abc"

        manager = RevisionManager(db=mock_db)

        # Register first
        manager.register_client(
            client_id=client_id,
            canvas_id=canvas_id,
        )
        manager.update_client_revision(client_id, 5)

        # Update
        manager.update_client_revision(client_id, 10)

        state = manager._client_states.get(client_id)
        assert state.last_revision == 10

    async def test_unregister_client(self, mock_db):
        """Unregister a client."""
        canvas_id = uuid4()
        client_id = "client-abc"

        manager = RevisionManager(db=mock_db)

        manager.register_client(
            client_id=client_id,
            canvas_id=canvas_id,
        )
        manager.update_client_revision(client_id, 5)

        assert client_id in manager._client_states

        manager.unregister_client(client_id)

        assert client_id not in manager._client_states


class TestRevisionManagerCache:
    """Test revision cache functionality."""

    def test_cache_operations(self, mock_db, sample_operation):
        """Test in-memory revision caching."""
        canvas_id = uuid4()
        manager = RevisionManager(db=mock_db)

        revision = Revision(
            revision_number=1,
            operation=sample_operation,
            client_id="client-123",
            timestamp=datetime.now(timezone.utc),
        )

        # Add to cache directly
        if canvas_id not in manager._revision_cache:
            manager._revision_cache[canvas_id] = []
        manager._revision_cache[canvas_id].append(revision)

        # Retrieve from cache
        cached = manager._revision_cache.get(canvas_id, [])
        assert len(cached) == 1
        assert cached[0].revision_number == 1

    def test_cache_multiple_revisions(self, mock_db):
        """Test cache with multiple revisions."""
        canvas_id = uuid4()
        manager = RevisionManager(db=mock_db)

        # Add multiple revisions
        for i in range(5):
            revision = Revision(
                revision_number=i,
                operation=Operation(
                    type=OperationType.UPDATE_BLOCK,
                    target_id=uuid4(),
                    data={},
                ),
                client_id="client-123",
                timestamp=datetime.now(timezone.utc),
            )
            if canvas_id not in manager._revision_cache:
                manager._revision_cache[canvas_id] = []
            manager._revision_cache[canvas_id].append(revision)

        assert len(manager._revision_cache[canvas_id]) == 5


class TestRevisionManagerGetLatestRevision:
    """Test getting latest revision number."""

    async def test_get_latest_revision(self, mock_db):
        """Get latest revision for canvas."""
        canvas_id = uuid4()

        mock_op = MagicMock(revision=42)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_op
        mock_db.execute.return_value = mock_result

        manager = RevisionManager(db=mock_db)
        result = await manager.get_latest_revision(canvas_id)

        assert result == 42

    async def test_get_latest_revision_empty(self, mock_db):
        """Get latest revision when no operations exist."""
        canvas_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        manager = RevisionManager(db=mock_db)
        result = await manager.get_latest_revision(canvas_id)

        assert result == 0
