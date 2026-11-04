"""
Unit tests for Soft Delete and GDPR Deletion

Tests:
- Soft delete functionality
- Query filtering
- GDPR deletion manager
- Audit trail
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.database.gdpr_deletion import (
    AuditProtectionError,
    DeletionAudit,
    DeletionJustificationError,
    GDPRDeletionManager,
    GDPRDeletionReason,
)
from src.core.database.soft_delete import SoftDeleteManager, SoftDeleteMixin, SoftDeleteQuery


class TestSoftDeleteMixin:
    """Tests for SoftDeleteMixin."""

    def test_soft_delete_sets_timestamp(self):
        """Test soft delete sets deleted_at timestamp."""

        class TestModel(SoftDeleteMixin):
            __allow_unmapped__ = True
            pass

        model = TestModel()
        # The columns are sqlalchemy Column/MappedColumn objects when not mapped
        # So we need to check if it's a column definition or an actual value
        from sqlalchemy.orm import MappedColumn

        deleted_at_before = model.deleted_at
        # Before soft_delete, deleted_at should be None or a Column/MappedColumn
        assert (
            deleted_at_before is None
            or isinstance(deleted_at_before, (MappedColumn, type(None)))
            or hasattr(deleted_at_before, "default")
        )

        model.soft_delete(deleted_by=1, reason="Test deletion")

        # After soft_delete, deleted_at should be a datetime
        assert model.deleted_at is not None
        assert model.deleted_at != deleted_at_before
        assert model.is_deleted is True
        assert model.deleted_by == 1
        assert model.deletion_reason == "Test deletion"

    def test_soft_delete_sets_different_reasons(self):
        """Test soft delete with different reasons."""

        class TestModel(SoftDeleteMixin):
            pass

        model = TestModel()
        model.soft_delete(reason="User requested")

        assert model.deletion_reason == "User requested"

    def test_restore_clears_deletion(self):
        """Test restore clears soft delete fields."""

        class TestModel(SoftDeleteMixin):
            pass

        model = TestModel()
        model.soft_delete(deleted_by=1, reason="Test")

        assert model.is_deleted is True

        model.restore()

        assert model.deleted_at is None
        assert model.deleted_by is None
        assert model.deletion_reason is None
        assert model.is_deleted is False

    def test_hard_delete_validates_reason(self):
        """Test hard delete validates reason."""

        class TestModel(SoftDeleteMixin):
            pass

        model = TestModel()

        # Should raise without reason
        with pytest.raises(ValueError, match="deletion_reason"):
            model.hard_delete("")

        # Should not raise with valid reason
        model.hard_delete("GDPR erasure request")  # Just validates, doesn't delete


class TestSoftDeleteQuery:
    """Tests for SoftDeleteQuery helper."""

    def test_not_deleted_filter(self):
        """Test not_deleted filter."""

        class MockModel:
            deleted_at = MagicMock()
            deleted_at.is_ = MagicMock(return_value="filter_expr")

        result = SoftDeleteQuery.not_deleted(MockModel)
        MockModel.deleted_at.is_.assert_called_once_with(None)
        assert result == "filter_expr"

    def test_is_deleted_filter(self):
        """Test is_deleted filter."""

        class MockModel:
            deleted_at = MagicMock()
            deleted_at.isnot = MagicMock(return_value="filter_expr")

        result = SoftDeleteQuery.is_deleted(MockModel)
        MockModel.deleted_at.isnot.assert_called_once_with(None)
        assert result == "filter_expr"


class TestGDPRDeletionReason:
    """Tests for GDPRDeletionReason enum."""

    def test_deletion_reason_values(self):
        """Test all deletion reason values."""
        assert GDPRDeletionReason.USER_ERASURE_REQUEST.value == "user_erasure_request"
        assert GDPRDeletionReason.CONSENT_WITHDRAWN.value == "consent_withdrawn"
        assert GDPRDeletionReason.DATA_RETENTION_EXPIRED.value == "data_retention_expired"
        assert GDPRDeletionReason.REGULATORY_REQUIREMENT.value == "regulatory_requirement"
        assert GDPRDeletionReason.CONTRACT_TERMINATED.value == "contract_terminated"

    def test_deletion_reason_descriptions(self):
        """Test deletion reason descriptions."""
        assert "GDPR Article 17" in GDPRDeletionReason.USER_ERASURE_REQUEST.description()
        assert "Article 7" in GDPRDeletionReason.CONSENT_WITHDRAWN.description()


class TestGDPRDeletionManager:
    """Tests for GDPRDeletionManager."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.add = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def deletion_manager(self, mock_session):
        """Create GDPR deletion manager."""
        return GDPRDeletionManager(mock_session)

    @pytest.mark.asyncio
    async def test_soft_delete_entity(self, deletion_manager, mock_session):
        """Test soft deleting an entity."""

        class TestEntity(SoftDeleteMixin):
            pass

        entity = TestEntity()

        await deletion_manager.soft_delete(entity, deleted_by=1, reason="User requested")

        assert entity.is_deleted is True
        assert entity.deleted_by == 1
        assert entity.deletion_reason == "User requested"
        mock_session.add.assert_called_once_with(entity)

    @pytest.mark.asyncio
    async def test_hard_delete_creates_audit(self, deletion_manager, mock_session):
        """Test hard delete creates audit entry."""

        class TestEntity:
            id = 123
            __class__ = type("TestEntity", (), {})

        entity = TestEntity()

        await deletion_manager.hard_delete(
            entity,
            deletion_reason=GDPRDeletionReason.USER_ERASURE_REQUEST,
            deleted_by=1,
            tenant_id=42,
        )

        # Should add audit entry
        assert mock_session.add.called
        # Should delete entity
        mock_session.delete.assert_called_once_with(entity)

    @pytest.mark.asyncio
    async def test_hard_delete_requires_valid_reason(self, deletion_manager):
        """Test hard delete requires valid GDPR reason."""

        class TestEntity:
            id = 123

        entity = TestEntity()

        with pytest.raises(DeletionJustificationError):
            await deletion_manager.hard_delete(
                entity,
                deletion_reason="invalid_reason",  # Not a GDPRDeletionReason
            )

    @pytest.mark.asyncio
    async def test_hard_delete_protects_audit_logs(self, deletion_manager):
        """Test hard delete protects audit log entities."""

        class deletion_audit:  # Named like protected entity
            id = 1

        entity = deletion_audit()

        with pytest.raises(AuditProtectionError):
            await deletion_manager.hard_delete(
                entity,
                deletion_reason=GDPRDeletionReason.REGULATORY_REQUIREMENT,
            )

    @pytest.mark.asyncio
    async def test_anonymize_replaces_pii(self, deletion_manager, mock_session):
        """Test anonymization replaces PII fields."""

        class TestEntity:
            id = 1
            email = "user@example.com"
            name = "John Doe"
            age = 30
            anonymized = False

        entity = TestEntity()

        await deletion_manager.anonymize(
            entity,
            pii_fields=["email", "name"],
            retention_fields=["age"],
        )

        # PII should be anonymized
        assert "[REDACTED]" in entity.email
        assert "[REDACTED]" in entity.name
        # Non-PII should be retained
        assert entity.age == 30
        mock_session.add.assert_called_once_with(entity)

    @pytest.mark.asyncio
    async def test_handle_erasure_request_anonymizes_audit(self, deletion_manager, mock_session):
        """Test erasure request anonymizes audit logs."""

        class deletion_audit:
            id = 1
            user_email = "user@example.com"
            user_name = "John"
            anonymized = False

        entity = deletion_audit()

        result = await deletion_manager.handle_erasure_request(
            entity,
            erasure_type="audit_log",
            deleted_by=1,
        )

        assert result == "anonymized"

    @pytest.mark.asyncio
    async def test_handle_erasure_request_hard_deletes_data(self, deletion_manager, mock_session):
        """Test erasure request hard deletes operational data."""

        class OperationalData:
            id = 1
            __class__ = type("OperationalData", (), {})

        entity = OperationalData()

        result = await deletion_manager.handle_erasure_request(
            entity,
            erasure_type="some_data",
            deleted_by=1,
            tenant_id=42,
        )

        assert result == "hard_deleted"


class TestDeletionAudit:
    """Tests for DeletionAudit model."""

    def test_deletion_audit_creation(self):
        """Test creating deletion audit entry."""
        audit = DeletionAudit(
            entity_type="User",
            entity_id="123",
            deletion_reason=GDPRDeletionReason.USER_ERASURE_REQUEST.value,
            deleted_by=1,
            tenant_id=42,
        )

        assert audit.entity_type == "User"
        assert audit.entity_id == "123"
        assert audit.deletion_reason == "user_erasure_request"
        assert audit.deleted_by == 1
        assert audit.tenant_id == 42

    def test_deletion_audit_repr(self):
        """Test deletion audit string representation."""
        audit = DeletionAudit(
            entity_type="User",
            entity_id="123",
            deletion_reason=GDPRDeletionReason.USER_ERASURE_REQUEST.value,
        )

        repr_str = repr(audit)
        assert "User" in repr_str
        assert "123" in repr_str


class TestSoftDeleteManager:
    """Tests for SoftDeleteManager."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.add = MagicMock()
        return session

    def test_manager_soft_delete(self, mock_session):
        """Test manager soft delete."""

        class TestEntity(SoftDeleteMixin):
            __allow_unmapped__ = True
            pass

        entity = TestEntity()

        # SoftDeleteManager.soft_delete is not async
        SoftDeleteManager.soft_delete(mock_session, entity, deleted_by=1, reason="Test")

        assert entity.is_deleted is True
        mock_session.add.assert_called_once_with(entity)

    def test_manager_restore(self, mock_session):
        """Test manager restore."""

        class TestEntity(SoftDeleteMixin):
            __allow_unmapped__ = True
            pass

        entity = TestEntity()
        entity.soft_delete(deleted_by=1, reason="Test")

        # SoftDeleteManager.restore is not async
        SoftDeleteManager.restore(mock_session, entity)

        assert entity.is_deleted is False


class TestGDPRComplianceReport:
    """Tests for GDPRComplianceReport."""

    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = MagicMock()
        # Make execute an async mock
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_generate_deletion_report(self, mock_session):
        """Test generating deletion report."""
        from src.core.database.gdpr_deletion import GDPRComplianceReport

        report_gen = GDPRComplianceReport(mock_session)

        # Mock result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        report = await report_gen.generate_deletion_report(
            tenant_id=42,
            start_date=datetime.now(timezone.utc),
        )

        assert "rows_returned" in report
        assert "by_reason" in report
        assert "by_entity_type" in report
        assert report["tenant_id"] == 42


class TestGDPRDeletionManagerUtilities:
    """Tests for GDPRDeletionManager utility methods."""

    def test_get_retention_period(self):
        """Test retention period lookup."""
        # User erasure: 90 days
        assert (
            GDPRDeletionManager.get_retention_period(GDPRDeletionReason.USER_ERASURE_REQUEST) == 90
        )

        # Consent withdrawn: 30 days
        assert GDPRDeletionManager.get_retention_period(GDPRDeletionReason.CONSENT_WITHDRAWN) == 30

        # Data retention expired: 0 days (immediate)
        assert (
            GDPRDeletionManager.get_retention_period(GDPRDeletionReason.DATA_RETENTION_EXPIRED) == 0
        )

    def test_hash_entity(self):
        """Test entity hashing."""
        mock_session = MagicMock()
        manager = GDPRDeletionManager(mock_session)

        class TestEntity:
            id = 1
            name = "Test"

        hash_result = manager._hash_entity(TestEntity())
        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA256 hex length

    def test_extract_metadata(self):
        """Test metadata extraction."""
        mock_session = MagicMock()
        manager = GDPRDeletionManager(mock_session)

        class TestEntity:
            id = 1
            created_at = datetime.now(timezone.utc)
            is_active = True
            sensitive_data = "secret"  # Should not be in metadata

        metadata = manager._extract_metadata(TestEntity())

        assert metadata["class_name"] == "TestEntity"
        assert "created_at" in metadata
        assert "is_active" in metadata
