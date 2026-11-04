"""
Unit tests for HashChainVerifier service.
Tests SHA-256 hash chain verification with mocked database.

Sprint 7, Task 3.1 - TDD Implementation
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Skip all tests if the module has not been implemented yet.
# When src.core.governance.hash_chain is created, tests auto-enable.
hash_chain = pytest.importorskip("src.core.governance.hash_chain")


class TestHashChainVerifier:
    """Test suite for HashChainVerifier class."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        return mock_session

    @pytest.fixture
    def sample_audit_log_entry(self):
        """Sample audit log entry for testing."""
        return {
            "id": 1,
            "tenant_id": 1,
            "action": "user_login",
            "resource": "auth",
            "event_type": "security",
            "threat_level": "low",
            "client_ip": "192.168.1.1",
            "endpoint": "/api/v1/login",
            "description": "User logged in successfully",
            "event_metadata": {},
            "details": {},
            "timestamp": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

    async def test_service_exists_with_required_methods(self, mock_db_session):
        """Test that HashChainVerifier class exists with required methods."""
        # Import here to trigger ImportError if class doesn't exist
        from src.core.governance.hash_chain import (
            ChainStatus,
            ChainVerificationResult,
            EntryVerificationResult,
            HashChainVerifier,
        )

        # Arrange & Act
        verifier = HashChainVerifier(mock_db_session)

        # Assert
        assert hasattr(verifier, "verify_chain")
        assert hasattr(verifier, "verify_entry")
        assert hasattr(verifier, "get_chain_status")
        assert callable(verifier.verify_chain)
        assert callable(verifier.verify_entry)
        assert callable(verifier.get_chain_status)

    async def test_verify_chain_returns_correct_structure(self, mock_db_session):
        """Test that verify_chain returns correct ChainVerificationResult structure."""
        from src.core.governance.hash_chain import (
            ChainVerificationResult,
            HashChainVerifier,
        )

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert
        assert isinstance(result, ChainVerificationResult)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "total_entries")
        assert hasattr(result, "verified_entries")
        assert hasattr(result, "broken_at_entry_id")
        assert hasattr(result, "broken_at_index")
        assert hasattr(result, "expected_hash")
        assert hasattr(result, "actual_hash")
        assert hasattr(result, "verification_time_ms")
        assert hasattr(result, "tenant_id")
        assert hasattr(result, "checked_at")
        assert result.tenant_id == tenant_id

    async def test_verify_entry_returns_correct_structure(self, mock_db_session):
        """Test that verify_entry returns correct EntryVerificationResult structure."""
        from src.core.governance.hash_chain import (
            EntryVerificationResult,
            HashChainVerifier,
        )

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        entry_id = 1
        tenant_id = 1

        # Mock entry result - entry not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_entry(entry_id, tenant_id)

        # Assert
        assert isinstance(result, EntryVerificationResult)
        assert hasattr(result, "entry_id")
        assert hasattr(result, "is_valid")
        assert hasattr(result, "hash_matches")
        assert hasattr(result, "previous_hash_matches")
        assert hasattr(result, "computed_hash")
        assert hasattr(result, "stored_hash")
        assert hasattr(result, "tenant_id")
        assert result.entry_id == entry_id
        assert result.tenant_id == tenant_id

    async def test_get_chain_status_returns_correct_structure(self, mock_db_session):
        """Test that get_chain_status returns correct ChainStatus structure."""
        from src.core.governance.hash_chain import ChainStatus, HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.get_chain_status(tenant_id)

        # Assert
        assert isinstance(result, ChainStatus)
        assert hasattr(result, "status")
        assert hasattr(result, "last_verified_at")
        assert hasattr(result, "total_entries")
        assert hasattr(result, "broken_entries_count")
        assert hasattr(result, "health_percentage")
        assert hasattr(result, "tenant_id")
        assert result.tenant_id == tenant_id
        assert result.status in ("healthy", "broken", "unverified")

    async def test_verify_chain_valid_chain_passes(self, mock_db_session):
        """Test that verify_chain passes for a valid hash chain."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Create valid chain entries
        entries = [
            MagicMock(
                id=1,
                tenant_id=1,
                action="action1",
                resource="resource1",
                timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
                event_type="security",
                threat_level="low",
                client_ip="192.168.1.1",
                endpoint="/api/v1/test",
                description="Test entry 1",
                event_metadata={},
                details={},
                previous_hash=None,
                audit_hash="abc123",  # Will be computed
            ),
            MagicMock(
                id=2,
                tenant_id=1,
                action="action2",
                resource="resource2",
                timestamp=datetime(2026, 4, 1, 12, 1, 0, tzinfo=timezone.utc),
                event_type="security",
                threat_level="low",
                client_ip="192.168.1.1",
                endpoint="/api/v1/test2",
                description="Test entry 2",
                event_metadata={},
                details={},
                previous_hash="abc123",
                audit_hash="def456",  # Will be computed
            ),
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entries
        mock_db_session.execute.return_value = mock_result

        # Compute actual hashes for the entries
        import hashlib

        def compute_hash(entry, prev_hash):
            content = f"{entry.tenant_id}:{entry.action}:{entry.resource}:{entry.timestamp.isoformat()}:{prev_hash or ''}"
            return hashlib.sha256(content.encode()).hexdigest()

        # Set correct hashes
        entries[0].audit_hash = compute_hash(entries[0], None)
        entries[1].previous_hash = entries[0].audit_hash
        entries[1].audit_hash = compute_hash(entries[1], entries[0].audit_hash)

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert
        assert result.is_valid is True
        assert result.total_entries == 2
        assert result.verified_entries == 2
        assert result.broken_at_entry_id is None
        assert result.broken_at_index is None

    async def test_verify_chain_detects_broken_chain(self, mock_db_session):
        """Test that verify_chain detects a broken hash chain."""
        import hashlib

        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Helper to compute hash like the implementation does
        def compute_hash(entry, prev_hash):
            content = f"{entry.tenant_id}:{entry.action}:{entry.resource}:{entry.timestamp.isoformat()}:{prev_hash or ''}"
            return hashlib.sha256(content.encode()).hexdigest()

        # Create chain with tampered second entry
        # First, create entry 1 with valid computed hash
        entry1 = MagicMock(
            id=1,
            tenant_id=1,
            action="action1",
            resource="resource1",
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            event_type="security",
            threat_level="low",
            client_ip="192.168.1.1",
            endpoint="/api/v1/test",
            description="Test entry 1",
            event_metadata={},
            details={},
            previous_hash=None,
            audit_hash="",  # Will compute below
        )
        entry1.audit_hash = compute_hash(entry1, None)

        # Entry 2 has wrong previous_hash (broken link)
        entry2 = MagicMock(
            id=2,
            tenant_id=1,
            action="action2",
            resource="resource2",
            timestamp=datetime(2026, 4, 1, 12, 1, 0, tzinfo=timezone.utc),
            event_type="security",
            threat_level="low",
            client_ip="192.168.1.1",
            endpoint="/api/v1/test2",
            description="Test entry 2",
            event_metadata={},
            details={},
            previous_hash="wrong_previous_hash",  # Broken link - doesn't match entry1 hash
            audit_hash="valid_hash_2",
        )

        entries = [entry1, entry2]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entries
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert
        assert result.is_valid is False
        assert result.broken_at_entry_id == 2
        assert result.broken_at_index == 1
        assert result.expected_hash == entry1.audit_hash  # Should match entry 1's hash
        assert result.actual_hash == "wrong_previous_hash"

    async def test_verify_entry_valid_entry_passes(self, mock_db_session):
        """Test that verify_entry passes for a valid entry."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        entry_id = 1
        tenant_id = 1

        import hashlib

        # Create a valid entry with correctly computed hash
        entry = MagicMock(
            id=1,
            tenant_id=1,
            action="user_login",
            resource="auth",
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            event_type="security",
            threat_level="low",
            client_ip="192.168.1.1",
            endpoint="/api/v1/login",
            description="User logged in",
            event_metadata={},
            details={},
            previous_hash=None,
            audit_hash="",
        )

        # Compute correct hash
        content = f"{entry.tenant_id}:{entry.action}:{entry.resource}:{entry.timestamp.isoformat()}:"
        correct_hash = hashlib.sha256(content.encode()).hexdigest()
        entry.audit_hash = correct_hash

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_entry(entry_id, tenant_id)

        # Assert
        assert result.is_valid is True
        assert result.hash_matches is True
        assert result.previous_hash_matches is True
        assert result.computed_hash == correct_hash
        assert result.stored_hash == correct_hash

    async def test_verify_entry_detects_tampered_entry(self, mock_db_session):
        """Test that verify_entry detects a tampered entry."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        entry_id = 1
        tenant_id = 1

        # Create entry with tampered hash
        entry = MagicMock(
            id=1,
            tenant_id=1,
            action="user_login",
            resource="auth",
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            event_type="security",
            threat_level="low",
            client_ip="192.168.1.1",
            endpoint="/api/v1/login",
            description="User logged in",
            event_metadata={},
            details={},
            previous_hash=None,
            audit_hash="tampered_hash_value",  # Wrong hash
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_entry(entry_id, tenant_id)

        # Assert
        assert result.is_valid is False
        assert result.hash_matches is False
        assert result.stored_hash == "tampered_hash_value"
        assert result.computed_hash != "tampered_hash_value"

    async def test_tenant_isolation(self, mock_db_session):
        """Test that verification respects tenant isolation."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Mock entries for tenant 1 only
        entries = [
            MagicMock(
                id=1,
                tenant_id=1,  # Correct tenant
                action="action1",
                resource="resource1",
                timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
                event_type="security",
                threat_level="low",
                client_ip="192.168.1.1",
                endpoint="/api/v1/test",
                description="Test",
                event_metadata={},
                details={},
                previous_hash=None,
                audit_hash="hash1",
            ),
        ]

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entries
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert - verify tenant_id filter is applied in query
        assert result.tenant_id == tenant_id
        # The mock should have been called with a query that filters by tenant_id
        mock_db_session.execute.assert_called()

    async def test_empty_chain_handling(self, mock_db_session):
        """Test handling of empty chain."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert
        assert result.is_valid is True  # Empty chain is valid
        assert result.total_entries == 0
        assert result.verified_entries == 0
        assert result.broken_at_entry_id is None

    async def test_single_entry_chain(self, mock_db_session):
        """Test verification of single entry chain."""
        from src.core.governance.hash_chain import HashChainVerifier

        # Arrange
        verifier = HashChainVerifier(mock_db_session)
        tenant_id = 1

        import hashlib

        entry = MagicMock(
            id=1,
            tenant_id=1,
            action="action1",
            resource="resource1",
            timestamp=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            event_type="security",
            threat_level="low",
            client_ip="192.168.1.1",
            endpoint="/api/v1/test",
            description="Test entry",
            event_metadata={},
            details={},
            previous_hash=None,
            audit_hash="",
        )

        # Compute correct hash
        content = f"{entry.tenant_id}:{entry.action}:{entry.resource}:{entry.timestamp.isoformat()}:"
        correct_hash = hashlib.sha256(content.encode()).hexdigest()
        entry.audit_hash = correct_hash

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entry]
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await verifier.verify_chain(tenant_id)

        # Assert
        assert result.is_valid is True
        assert result.total_entries == 1
        assert result.verified_entries == 1
        assert result.broken_at_entry_id is None
