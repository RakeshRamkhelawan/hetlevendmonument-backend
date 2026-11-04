"""
Unit Tests for Soft Delete Mixin (SD-8.1)

Tests database mixin functionality.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest


class TestSoftDeleteMixin:
    """Tests for SoftDeleteMixin class."""

    def test_soft_delete_sets_timestamp(self):
        """Test soft_delete sets deleted_at timestamp."""
        from src.core.database.mixins import SoftDeleteMixin

        # Create a mock model with the mixin
        class MockModel(SoftDeleteMixin):
            deleted_at = None
            is_deleted = False

        model = MockModel()
        model.soft_delete()

        assert model.deleted_at is not None
        assert model.is_deleted is True

    def test_restore_clears_timestamp(self):
        """Test restore clears deleted_at timestamp."""
        from src.core.database.mixins import SoftDeleteMixin

        class MockModel(SoftDeleteMixin):
            deleted_at = datetime.utcnow()
            is_deleted = True

        model = MockModel()
        model.restore()

        assert model.deleted_at is None
        assert model.is_deleted is False


class TestTimestampMixin:
    """Tests for TimestampMixin class."""

    def test_mixin_has_created_at(self):
        """Test mixin defines created_at column."""
        from src.core.database.mixins import TimestampMixin

        assert hasattr(TimestampMixin, "created_at")

    def test_mixin_has_updated_at(self):
        """Test mixin defines updated_at column."""
        from src.core.database.mixins import TimestampMixin

        assert hasattr(TimestampMixin, "updated_at")


class TestAuditMixin:
    """Tests for AuditMixin class."""

    def test_audit_mixin_inherits_timestamps(self):
        """Test AuditMixin inherits from TimestampMixin."""
        from src.core.database.mixins import AuditMixin, TimestampMixin

        assert issubclass(AuditMixin, TimestampMixin)
