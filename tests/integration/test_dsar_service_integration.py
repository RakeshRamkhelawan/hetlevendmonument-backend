"""
Integration tests for DSARService - GDPR Art. 15, 17, 20 compliance.

TDD Workflow: RED phase - Write failing test first.
Tests require actual PostgreSQL database.
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# These imports will fail initially - that's the RED phase
from src.core.governance.dsar_service import (
    DSARAuthorizationError,
    DSARDeletionResult,
    DSARExportResult,
    DSARService,
    DSARTenantIsolationError,
)
from src.core.governance.models import AuditLog
from src.core.models.rbac_models import Tenant, User


@pytest.mark.integration
@pytest.mark.gdpr
@pytest.mark.requires_postgres
class TestDSARExport:
    """Test suite for GDPR Art. 20 - Right to Data Portability."""

    async def test_export_user_data_returns_actual_data(self, db: AsyncSession):
        """DSAR export must return ACTUAL user data from database."""
        # Arrange: Create tenant and user
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Store user_id before async operation (prevents lazy-load after async boundary)
        user_id = str(user.id)
        tenant_id = tenant.id

        # Act: Export user data
        service = DSARService(db)
        result = await service.export_user_data(
            user_id=user_id,
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            is_admin=False,
        )

        # Assert: Verify actual data returned
        assert isinstance(result, DSARExportResult)
        assert result.user_id == user_id
        assert result.tenant_id == tenant_id
        assert result.total_records > 0
        assert "user_profile" in result.data
        assert result.data["user_profile"][0]["email"] == "test@example.com"

    async def test_export_creates_audit_log(self, db: AsyncSession):
        """DSAR export must create audit log entry."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Store IDs before async operation (prevents lazy-load after async boundary)
        user_id = str(user.id)
        tenant_id = tenant.id

        # Act
        service = DSARService(db)
        await service.export_user_data(
            user_id=user_id,
            tenant_id=tenant_id,
            requested_by_user_id=user_id,
            is_admin=False,
        )

        # Assert: Check audit log
        result = await db.execute(
            AuditLog.__table__.select().where(AuditLog.action == "gdpr.dsar_export")
        )
        audit_logs = result.fetchall()
        assert len(audit_logs) >= 1
        assert audit_logs[0].tenant_id == tenant_id

    async def test_export_unauthorized_user_blocked(self, db: AsyncSession):
        """User A must NOT be able to export User B's data."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user_a = User(
            email="user_a@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        user_b = User(
            email="user_b@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user_a)
        db.add(user_b)
        await db.commit()

        # Act & Assert
        service = DSARService(db)
        with pytest.raises(DSARAuthorizationError) as exc_info:
            await service.export_user_data(
                user_id=str(user_b.id),  # Target: User B
                tenant_id=tenant.id,
                requested_by_user_id=str(user_a.id),  # Requester: User A
                is_admin=False,
            )

        assert "not authorized" in str(exc_info.value).lower()

    async def test_export_cross_tenant_blocked(self, db: AsyncSession):
        """Cross-tenant data access must be blocked."""
        # Arrange
        tenant_1 = Tenant(name="Tenant 1", slug=f"tenant-1-{uuid.uuid4().hex[:8]}")
        tenant_2 = Tenant(name="Tenant 2", slug=f"tenant-2-{uuid.uuid4().hex[:8]}")
        db.add(tenant_1)
        db.add(tenant_2)
        await db.flush()

        user = User(
            email="user@example.com",
            tenant_id=tenant_1.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Act & Assert
        service = DSARService(db)
        with pytest.raises(DSARTenantIsolationError) as exc_info:
            await service.export_user_data(
                user_id=str(user.id),
                tenant_id=tenant_2.id,  # Wrong tenant!
                requested_by_user_id=str(user.id),
                is_admin=False,
            )

        assert "not found in tenant" in str(exc_info.value).lower()

    async def test_export_admin_can_export_other_user_data(self, db: AsyncSession):
        """Admin must be able to export any user's data."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        admin = User(
            email="admin@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        user = User(
            email="user@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(admin)
        db.add(user)
        await db.commit()

        # Store IDs before async operation (prevents lazy-load after async boundary)
        user_id = str(user.id)
        admin_id = str(admin.id)
        tenant_id = tenant.id

        # Act
        service = DSARService(db)
        result = await service.export_user_data(
            user_id=user_id,
            tenant_id=tenant_id,
            requested_by_user_id=admin_id,
            is_admin=True,  # Admin flag
        )

        # Assert
        assert result.user_id == user_id


@pytest.mark.integration
@pytest.mark.gdpr
@pytest.mark.requires_postgres
class TestDSARSoftDelete:
    """Test suite for GDPR Art. 17 - Right to Erasure (Soft Delete)."""

    async def test_soft_delete_marks_user_inactive(self, db: AsyncSession):
        """Soft delete must mark user as inactive, not remove from DB."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Act
        service = DSARService(db)
        result = await service.delete_user_data(
            user_id=str(user.id),
            tenant_id=tenant.id,
            hard_delete=False,  # Soft delete
            requested_by_user_id=str(user.id),
            is_admin=False,
        )

        # Assert
        assert isinstance(result, DSARDeletionResult)
        assert result.delete_type == "soft"
        assert result.scheduled_purge_date is not None

        # Refresh user from DB
        await db.refresh(user)
        assert user.is_active is False
        assert user.deleted_at is not None
        assert user.deletion_scheduled_for is not None

    async def test_soft_delete_sets_correct_grace_period(self, db: AsyncSession):
        """Soft delete must set 30-day grace period."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Act
        service = DSARService(db)
        result = await service.delete_user_data(
            user_id=str(user.id),
            tenant_id=tenant.id,
            hard_delete=False,
            requested_by_user_id=str(user.id),
            is_admin=False,
        )

        # Assert: Verify 30-day grace period
        grace_period = result.scheduled_purge_date - result.deleted_at
        assert grace_period.days == 30

    async def test_soft_delete_creates_audit_log(self, db: AsyncSession):
        """Soft delete must create audit log."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Act
        service = DSARService(db)
        await service.delete_user_data(
            user_id=str(user.id),
            tenant_id=tenant.id,
            hard_delete=False,
            requested_by_user_id=str(user.id),
            is_admin=False,
        )

        # Assert
        result = await db.execute(
            AuditLog.__table__.select().where(AuditLog.action == "gdpr.dsar_delete")
        )
        audit_logs = result.fetchall()
        assert len(audit_logs) >= 1
        assert audit_logs[0].details["delete_type"] == "soft"


@pytest.mark.integration
@pytest.mark.gdpr
@pytest.mark.requires_postgres
class TestDSARHardDelete:
    """Test suite for GDPR Art. 17 - Hard Delete (Admin Only)."""

    async def test_hard_delete_requires_admin(self, db: AsyncSession):
        """Hard delete must require admin privileges."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        user = User(
            email="test@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(user)
        await db.commit()

        # Act & Assert
        service = DSARService(db)
        with pytest.raises(DSARAuthorizationError) as exc_info:
            await service.delete_user_data(
                user_id=str(user.id),
                tenant_id=tenant.id,
                hard_delete=True,  # Hard delete
                requested_by_user_id=str(user.id),
                is_admin=False,  # Not admin!
            )

        assert "admin privileges" in str(exc_info.value).lower()

    async def test_hard_delete_actually_removes_data(self, db: AsyncSession):
        """Hard delete must permanently remove data."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        admin = User(
            email="admin@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        user = User(
            email="user@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(admin)
        db.add(user)
        await db.commit()

        user_id = user.id

        # Act
        service = DSARService(db)
        result = await service.delete_user_data(
            user_id=str(user_id),
            tenant_id=tenant.id,
            hard_delete=True,
            requested_by_user_id=str(admin.id),
            is_admin=True,
        )

        # Assert
        assert result.delete_type == "hard"
        assert result.scheduled_purge_date is None

        # Verify user is actually deleted
        result = await db.execute(User.__table__.select().where(User.id == user_id))
        deleted_user = result.scalar_one_or_none()
        assert deleted_user is None

    async def test_hard_delete_creates_audit_log(self, db: AsyncSession):
        """Hard delete must create audit log with threat level."""
        # Arrange
        tenant = Tenant(name="Test Tenant", slug=f"test-tenant-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        admin = User(
            email="admin@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        user = User(
            email="user@example.com",
            tenant_id=tenant.id,
            is_active=True,
            hashed_password="$2b$12$test",
        )
        db.add(admin)
        db.add(user)
        await db.commit()

        # Act
        service = DSARService(db)
        await service.delete_user_data(
            user_id=str(user.id),
            tenant_id=tenant.id,
            hard_delete=True,
            requested_by_user_id=str(admin.id),
            is_admin=True,
        )

        # Assert
        result = await db.execute(
            AuditLog.__table__.select().where(AuditLog.action == "gdpr.dsar_delete")
        )
        audit_logs = result.fetchall()
        hard_delete_logs = [log for log in audit_logs if log.details.get("delete_type") == "hard"]
        assert len(hard_delete_logs) >= 1


# Mark file as test file for pytest
__test__ = True
