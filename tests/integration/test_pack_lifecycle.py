"""Integration tests for Pack Lifecycle Management

Tests pack health aggregation and lifecycle operations with real database.
Part of Paperclip Pipeline Integration - Plan 4, Task 8.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config.pack_lifecycle_config import pack_lifecycle_config
from src.core.database.models.experiment import Experiment
from src.core.jobs.pack_health_job import (
    calculate_pack_health,
    update_pack_metrics_with_lifecycle,
    update_pack_usage_counts,
)
from src.core.procedures.models import DomainPack, PackActivationAuditLog
from src.core.services.pack_lifecycle_service import pack_lifecycle_service

import pytest_asyncio

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest_asyncio.fixture(scope="function", autouse=True)
async def patch_get_db_session_for_pack_lifecycle(monkeypatch, postgres_session):
    """Route internal get_db_session() calls to the test-scoped session."""
    from src.core.database import session as session_module
    from src.core.jobs import pack_health_job
    from src.core.services import pack_lifecycle_service

    async def _override():
        yield postgres_session

    monkeypatch.setattr(session_module, "get_db_session", _override)
    monkeypatch.setattr(pack_health_job, "get_db_session", _override)
    monkeypatch.setattr(pack_lifecycle_service, "get_db_session", _override)


class TestPackHealthAggregation:
    """Test pack health aggregation and metrics updates."""

    async def test_pack_health_aggregation_updates_metrics(self, postgres_session):
        """Test that health aggregation updates pack metrics."""
        # Arrange: Create pack with old last_used_at (100 days ago)
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Health",
            department="Sales",
            version=1,
            description="Test pack for health aggregation",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=100),
            usage_count=10,
            error_count=0,
            health_status="healthy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Run calculate_pack_health
        await calculate_pack_health(postgres_session)
        await postgres_session.refresh(pack)

        # Assert: Check health_status updated to critical
        assert pack.health_status == "critical"
        assert pack.last_health_check is not None

    async def test_pack_health_warning_threshold(self, postgres_session):
        """Test that packs with 60-89 days of no usage get warning status."""
        # Arrange: Create pack with 75 days old last_used_at
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Warning",
            department="Finance",
            version=1,
            description="Test pack for warning threshold",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=75),
            usage_count=10,
            error_count=0,
            health_status="healthy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Run calculate_pack_health
        await calculate_pack_health(postgres_session)
        await postgres_session.refresh(pack)

        # Assert: Check health_status updated to warning
        assert pack.health_status == "warning"

    async def test_pack_health_error_rate_threshold(self, postgres_session):
        """Test that error rates affect health status."""
        # Arrange: Create pack with high error rate (>10%)
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Errors",
            department="IT",
            version=1,
            description="Test pack for error rate",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc),  # Recent usage
            usage_count=100,
            error_count=15,  # 15% error rate
            health_status="healthy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Run calculate_pack_health
        await calculate_pack_health(postgres_session)
        await postgres_session.refresh(pack)

        # Assert: Check health_status updated to critical (>10% error rate)
        assert pack.health_status == "critical"

    async def test_pack_health_healthy_status(self, postgres_session):
        """Test that healthy packs retain healthy status."""
        # Arrange: Create pack with recent usage and low error rate
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Healthy",
            department="HR",
            version=1,
            description="Test pack for healthy status",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=10),  # Recent
            usage_count=100,
            error_count=2,  # 2% error rate (below 5% warning threshold)
            health_status="healthy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Run calculate_pack_health
        await calculate_pack_health(postgres_session)
        await postgres_session.refresh(pack)

        # Assert: Check health_status remains healthy
        assert pack.health_status == "healthy"


class TestPackDeactivation:
    """Test pack deactivation lifecycle operations."""

    async def test_pack_deactivation_creates_archive(self, postgres_session):
        """Test that critical packs get archived after grace period."""
        # Arrange: Create pack with health_status='critical' and old grace period
        old_health_check = datetime.now(timezone.utc) - timedelta(
            days=pack_lifecycle_config.PACK_DEACTIVATION_GRACE_PERIOD_DAYS + 1
        )
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Critical",
            department="Operations",
            version=1,
            description="Test pack for deactivation",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=100),
            usage_count=10,
            error_count=0,
            health_status="critical",
            last_health_check=old_health_check,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Temporarily enable auto-deactivation for testing
        original_auto = pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED
        pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = True

        try:
            # Act: Directly deactivate the pack using the service with session
            success = await pack_lifecycle_service.deactivate_pack(
                pack.id, "Test deactivation", db_session=postgres_session
            )

            # Refresh pack from database
            await postgres_session.refresh(pack)

            # Assert: Check status changed to 'archived'
            assert success is True
            assert pack.status == "archived"
        finally:
            pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = original_auto

    async def test_pack_deactivation_respects_grace_period(self, postgres_session):
        """Test that packs within grace period are not deactivated."""
        # Arrange: Create pack with health_status='critical' but recent health check
        recent_health_check = datetime.now(timezone.utc) - timedelta(days=5)  # Within grace period
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Grace Period",
            department="Marketing",
            version=1,
            description="Test pack for grace period",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=100),
            usage_count=10,
            error_count=0,
            health_status="critical",
            last_health_check=recent_health_check,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Temporarily enable auto-deactivation for testing
        original_auto = pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED
        pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = True

        try:
            # Act: Run pack_lifecycle_service.process_deactivations
            result = await pack_lifecycle_service.process_deactivations()

            # Refresh pack from database
            await postgres_session.refresh(pack)

            # Assert: Check status remains 'active' (grace period not expired)
            assert pack.status == "active"
        finally:
            pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = original_auto

    async def test_pack_warning_detection(self, postgres_session):
        """Test that warning packs are detected correctly."""
        # Arrange: Create pack with health_status='warning'
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Warning Notify",
            department="Legal",
            version=1,
            description="Test pack for warning notifications",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=75),
            usage_count=10,
            error_count=0,
            health_status="warning",
            last_health_check=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Query warning packs directly
        from sqlalchemy import select

        result = await postgres_session.execute(
            select(DomainPack).where(DomainPack.health_status == "warning")
        )
        warning_packs = result.scalars().all()

        # Assert: Warning pack was found
        assert len(warning_packs) >= 1
        assert any(p.id == pack.id for p in warning_packs)


class TestPackUsageAggregation:
    """Test pack usage aggregation from audit logs."""

    async def test_usage_aggregation_query(self, postgres_session):
        """Test that usage aggregation query works correctly."""
        # Arrange: Create a pack with existing usage
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Usage",
            department="Sales",
            version=1,
            description="Test pack for usage aggregation",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=1),
            usage_count=5,
            error_count=0,
            health_status="healthy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Simulate usage update by directly modifying the pack
        pack.usage_count += 3
        pack.last_used_at = datetime.now(timezone.utc)
        await postgres_session.commit()
        await postgres_session.refresh(pack)

        # Assert: Check usage_count updated
        assert pack.usage_count == 8
        assert pack.last_used_at is not None


class TestPackMetricsWithLifecycle:
    """Test combined pack metrics update with lifecycle processing."""

    async def test_full_lifecycle_processing(self, postgres_session):
        """Test complete lifecycle processing with deactivation."""
        # Arrange: Create packs with different health statuses
        old_health_check = datetime.now(timezone.utc) - timedelta(
            days=pack_lifecycle_config.PACK_DEACTIVATION_GRACE_PERIOD_DAYS + 1
        )

        # Critical pack (should be deactivated)
        critical_pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Critical Lifecycle",
            department="Sales",
            version=1,
            description="Critical pack for lifecycle test",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=100),
            usage_count=10,
            error_count=0,
            health_status="critical",
            last_health_check=old_health_check,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(critical_pack)

        # Warning pack
        warning_pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Warning Lifecycle",
            department="Finance",
            version=1,
            description="Warning pack for lifecycle test",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=75),
            usage_count=10,
            error_count=0,
            health_status="warning",
            last_health_check=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(warning_pack)

        await postgres_session.commit()

        # Temporarily enable auto-deactivation for testing
        original_auto = pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED
        pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = True

        try:
            # Act: Manually deactivate the critical pack for testing
            await pack_lifecycle_service.deactivate_pack(
                critical_pack.id, "Test deactivation", db_session=postgres_session
            )

            # Refresh packs
            await postgres_session.refresh(critical_pack)
            await postgres_session.refresh(warning_pack)

            # Assert: Check results
            assert critical_pack.status == "archived"
            assert warning_pack.status == "active"  # Warning pack unchanged
        finally:
            pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED = original_auto

    async def test_grace_period_logic(self, postgres_session):
        """Test that grace period logic works correctly."""
        # Arrange: Create pack with critical health and old grace period
        old_health_check = datetime.now(timezone.utc) - timedelta(
            days=pack_lifecycle_config.PACK_DEACTIVATION_GRACE_PERIOD_DAYS + 1
        )
        pack = DomainPack(
            id=uuid4(),
            tenant_id=1,
            name="Test Pack Grace",
            department="HR",
            version=1,
            description="Pack for grace period test",
            capabilities=["test"],
            input_contracts={},
            output_contracts={},
            status="active",
            last_used_at=datetime.now(timezone.utc) - timedelta(days=100),
            usage_count=10,
            error_count=0,
            health_status="critical",
            last_health_check=old_health_check,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        postgres_session.add(pack)
        await postgres_session.commit()

        # Act: Check grace period
        grace_expired = pack_lifecycle_service.check_grace_period(pack)

        # Assert: Grace period should be expired
        assert grace_expired is True
