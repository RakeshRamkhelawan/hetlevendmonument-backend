"""
Unit tests for Dead Letter Queue (DLQ)

Tests:
- Enqueue failed tasks
- List entries with filtering
- Retry and resolve operations
- Poison pill detection
- Tenant isolation
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.workflow.dead_letter_queue import (
    DeadLetterEntry,
    DeadLetterQueue,
    DLQStatus,
    PoisonPillDetector,
)


class MockSession:
    """Mock AsyncSession for testing."""

    def __init__(self):
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.execute = AsyncMock()
        self.scalars = MagicMock()

    def __call__(self):
        return self


class TestDeadLetterEntry:
    """Tests for DeadLetterEntry model."""

    def test_entry_creation(self):
        """Test creating a DLQ entry."""
        entry = DeadLetterEntry(
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Task failed",
            stack_trace="Traceback...",
            error_type="ValueError",
            retry_count=3,
            max_retries=3,
            status=DLQStatus.PENDING.value,
        )

        assert entry.original_task_id == "task-123"
        assert entry.execution_id == "exec-456"
        assert entry.tenant_id == 1
        assert entry.error_message == "Task failed"
        assert entry.is_poison_pill is True  # retry_count >= 3

    def test_is_poison_pill_detection(self):
        """Test poison pill detection."""
        entry_low = DeadLetterEntry(retry_count=1)
        entry_medium = DeadLetterEntry(retry_count=2)
        entry_high = DeadLetterEntry(retry_count=3)
        entry_very_high = DeadLetterEntry(retry_count=5)

        assert entry_low.is_poison_pill is False
        assert entry_medium.is_poison_pill is False
        assert entry_high.is_poison_pill is True
        assert entry_very_high.is_poison_pill is True

    def test_to_dict(self):
        """Test entry serialization."""
        entry = DeadLetterEntry(
            id=1,
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Error",
            retry_count=2,
            max_retries=3,
            status=DLQStatus.PENDING.value,
            failed_at=datetime.now(timezone.utc),
        )

        data = entry.to_dict()

        assert data["id"] == 1
        assert data["original_task_id"] == "task-123"
        assert data["retry_count"] == 2
        assert "failed_at" in data


class TestDeadLetterQueueEnqueue:
    """Tests for DLQ enqueue operations."""

    @pytest.fixture
    def mock_session(self):
        return MockSession()

    @pytest.fixture
    def dlq(self, mock_session):
        return DeadLetterQueue(mock_session)

    @pytest.mark.asyncio
    async def test_enqueue_creates_entry(self, dlq, mock_session):
        """Test enqueue creates a DLQ entry."""
        entry = await dlq.enqueue(
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Task failed",
            stack_trace="Traceback...",
            error_type="ValueError",
            workflow_id="wf-789",
            retry_count=3,
            max_retries=3,
        )

        assert entry.original_task_id == "task-123"
        assert entry.execution_id == "exec-456"
        assert entry.tenant_id == 1
        assert entry.error_message == "Task failed"
        assert entry.status == DLQStatus.PENDING.value

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_with_metadata(self, dlq, mock_session):
        """Test enqueue with task metadata."""
        metadata = {"task_type": "llm_call", "model": "gemini"}

        entry = await dlq.enqueue(
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Error",
            task_metadata=metadata,
        )

        assert entry.task_metadata is not None


class TestDeadLetterQueueList:
    """Tests for DLQ list operations."""

    @pytest.fixture
    def mock_session(self):
        session = MockSession()
        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result
        return session

    @pytest.fixture
    def dlq(self, mock_session):
        return DeadLetterQueue(mock_session)

    @pytest.mark.asyncio
    async def test_list_entries_basic(self, dlq, mock_session):
        """Test basic list operation."""
        entries = await dlq.list_entries(tenant_id=1)

        assert isinstance(entries, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_entries_with_status_filter(self, dlq, mock_session):
        """Test list with status filter."""
        entries = await dlq.list_entries(
            tenant_id=1,
            status=DLQStatus.PENDING,
        )

        assert isinstance(entries, list)


class TestDeadLetterQueueRetry:
    """Tests for DLQ retry operations."""

    @pytest.fixture
    def mock_session(self):
        session = MockSession()
        return session

    @pytest.fixture
    def dlq(self, mock_session):
        return DeadLetterQueue(mock_session)

    @pytest.mark.asyncio
    async def test_retry_entry_success(self, dlq, mock_session):
        """Test retrying a pending entry."""
        # Setup mock entry
        entry = DeadLetterEntry(
            id=1,
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Error",
            status=DLQStatus.PENDING.value,
            retry_count=2,
        )

        # Mock get_entry to return our entry
        dlq.get_entry = AsyncMock(return_value=entry)

        result = await dlq.retry_entry(entry_id=1, tenant_id=1)

        assert result is True
        assert entry.status == DLQStatus.RETRYING.value
        assert entry.retry_count == 3

    @pytest.mark.asyncio
    async def test_retry_resolved_entry_fails(self, dlq, mock_session):
        """Test retrying a resolved entry fails."""
        entry = DeadLetterEntry(
            id=1,
            status=DLQStatus.RESOLVED.value,
            retry_count=2,
        )

        dlq.get_entry = AsyncMock(return_value=entry)

        result = await dlq.retry_entry(entry_id=1, tenant_id=1)

        assert result is False

    @pytest.mark.asyncio
    async def test_retry_nonexistent_entry(self, dlq, mock_session):
        """Test retrying nonexistent entry."""
        dlq.get_entry = AsyncMock(return_value=None)

        result = await dlq.retry_entry(entry_id=999, tenant_id=1)

        assert result is False


class TestDeadLetterQueueResolve:
    """Tests for DLQ resolve operations."""

    @pytest.fixture
    def mock_session(self):
        session = MockSession()
        return session

    @pytest.fixture
    def dlq(self, mock_session):
        return DeadLetterQueue(mock_session)

    @pytest.mark.asyncio
    async def test_resolve_entry_success(self, dlq, mock_session):
        """Test resolving an entry."""
        entry = DeadLetterEntry(
            id=1,
            original_task_id="task-123",
            execution_id="exec-456",
            tenant_id=1,
            error_message="Error",
            status=DLQStatus.PENDING.value,
        )

        dlq.get_entry = AsyncMock(return_value=entry)

        result = await dlq.resolve_entry(
            entry_id=1,
            tenant_id=1,
            resolved_by=42,
            notes="Fixed the issue",
        )

        assert result is True
        assert entry.status == DLQStatus.RESOLVED.value
        assert entry.resolved_by == 42
        assert entry.resolution_notes == "Fixed the issue"
        assert entry.resolved_at is not None


class TestPoisonPillDetector:
    """Tests for poison pill detection."""

    @pytest.fixture
    def mock_session(self):
        return MockSession()

    @pytest.fixture
    def dlq(self, mock_session):
        return DeadLetterQueue(mock_session)

    @pytest.fixture
    def detector(self, dlq):
        return PoisonPillDetector(dlq, threshold=3)

    @pytest.mark.asyncio
    async def test_check_workflow_no_poison(self, detector, mock_session):
        """Test workflow with no poison pills."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        analysis = await detector.check_workflow("exec-1", 1)

        assert analysis["has_poison_pills"] is False
        assert analysis["poison_pill_count"] == 0

    @pytest.mark.asyncio
    async def test_check_workflow_with_poison(self, detector, mock_session):
        """Test workflow with poison pills."""
        # Mock entries with high retry counts
        entries = [
            DeadLetterEntry(id=1, retry_count=5),
            DeadLetterEntry(id=2, retry_count=4),
            DeadLetterEntry(id=3, retry_count=1),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entries
        mock_session.execute.return_value = mock_result

        analysis = await detector.check_workflow("exec-1", 1)

        assert analysis["has_poison_pills"] is True
        assert analysis["poison_pill_count"] == 2
        assert analysis["total_entries"] == 3

    @pytest.mark.asyncio
    async def test_should_block_workflow(self, detector, mock_session):
        """Test workflow blocking logic."""
        # 3 poison pills out of 4 total (>50%)
        entries = [
            DeadLetterEntry(id=1, retry_count=5),
            DeadLetterEntry(id=2, retry_count=4),
            DeadLetterEntry(id=3, retry_count=4),
            DeadLetterEntry(id=4, retry_count=1),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entries
        mock_session.execute.return_value = mock_result

        should_block = await detector.should_block_workflow("exec-1", 1)

        assert should_block is True  # 3/4 = 75% > 50%


class TestDLQStatus:
    """Tests for DLQStatus enum."""

    def test_status_values(self):
        """Test all status values."""
        assert DLQStatus.PENDING.value == "pending"
        assert DLQStatus.RETRYING.value == "retrying"
        assert DLQStatus.RESOLVED.value == "resolved"
        assert DLQStatus.EXPIRED.value == "expired"
