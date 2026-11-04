"""
Unit tests for DSARService - GDPR Art. 15, 17, 20 compliance.

TDD Workflow: GREEN phase - Tests with mocked database.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.governance.dsar_service import (
    DSARAuthorizationError,
    DSARDeletionResult,
    DSARExportResult,
    DSARService,
    DSARTenantIsolationError,
)


@pytest.fixture(autouse=True)
def geen_echte_redis():
    """Het DSAR-verwijderpad ruimt ook Redis-sessies op; een unittest mag daar niet echt heen.

    Gemeten 2026-09-11 in de hoofdwerkmap op develop: vijf toetsen in dit bestand plus
    tests/unit/governance/test_gdpr_user_behavior.py::test_complete_data_deletion_workflow
    vielen om op de netwerkblokkade (ADR-036 OP-18), met in de melding een ECHTE verbinding
    naar localhost:6380. Die wordt geopend door
    `dsar_service._clear_copilot_sessions` (src/core/governance/dsar_service.py:374) via
    `get_redis()`. Poort 6380 stond tot commit ec7e2fb4 in de tolerantielijst van
    tests/fixtures/netwerkblokkade.py en is daar toen uit gehaald; sindsdien slaat de
    blokkade hier toe.

    De blokkade heeft GELIJK: een unittest hoort deze verbinding niet te maken. Dit is dan
    ook precies de remedie die de melding van de blokkade zelf voorschrijft -- het pad dat
    verbindt mocken, en niet de poort weer breed tolereren.

    De TypeError-regels over `begin_nested` in de logs van dit bestand zijn IETS ANDERS: dat
    is ruis uit best-effort-takken die hun fout zelf opvangen, en die tests slaagden daar al
    mee. Niet verwarren met deze faling.
    """
    with patch(
        "src.core.shared.redis_client.get_redis",
        new=AsyncMock(return_value=AsyncMock()),
    ):
        yield


@pytest.mark.unit
@pytest.mark.gdpr
class TestDSARExportUnit:
    """Unit tests for DSAR export functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = 123
        user.email = "test@example.com"
        user.tenant_id = 1
        user.is_active = True
        user.created_at = datetime.now(timezone.utc)
        user.last_login = None
        return user

    async def test_export_user_data_success(self, mock_db, mock_user):
        """Export must succeed for authorized user."""
        # Arrange
        service = DSARService(mock_db)

        # Mock the user lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.export_user_data(
            user_id="123",
            tenant_id=1,
            requested_by_user_id="123",
            is_admin=False,
        )

        # Assert
        assert isinstance(result, DSARExportResult)
        assert result.user_id == "123"
        assert result.tenant_id == 1
        assert "user_profile" in result.data
        assert result.data["user_profile"][0]["email"] == "test@example.com"

    async def test_export_unauthorized_blocked(self, mock_db, mock_user):
        """User A must not be able to export User B's data."""
        # Arrange
        service = DSARService(mock_db)

        # Mock the user lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(DSARAuthorizationError) as exc_info:
            await service.export_user_data(
                user_id="123",  # Target: User 123
                tenant_id=1,
                requested_by_user_id="456",  # Requester: User 456
                is_admin=False,
            )

        assert "not authorized" in str(exc_info.value).lower()

    async def test_export_admin_can_access_any_user(self, mock_db, mock_user):
        """Admin must be able to export any user's data."""
        # Arrange
        service = DSARService(mock_db)

        # Mock the user lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.export_user_data(
            user_id="123",
            tenant_id=1,
            requested_by_user_id="admin_456",  # Admin
            is_admin=True,
        )

        # Assert
        assert result.user_id == "123"

    async def test_export_cross_tenant_blocked(self, mock_db):
        """Cross-tenant access must be blocked."""
        # Arrange
        service = DSARService(mock_db)

        # Mock: User not found in tenant
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(DSARTenantIsolationError) as exc_info:
            await service.export_user_data(
                user_id="123",
                tenant_id=2,  # Wrong tenant
                requested_by_user_id="123",
                is_admin=False,
            )

        assert "not found in tenant" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.gdpr
class TestDSARDeleteUnit:
    """Unit tests for DSAR delete functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = 123
        user.email = "test@example.com"
        user.tenant_id = 1
        user.is_active = True
        return user

    async def test_soft_delete_marks_inactive(self, mock_db, mock_user):
        """Soft delete must mark user as inactive."""
        # Arrange
        service = DSARService(mock_db)

        # Mock user lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=False,
            requested_by_user_id="123",
            is_admin=False,
        )

        # Assert
        assert isinstance(result, DSARDeletionResult)
        assert result.delete_type == "soft"
        assert result.scheduled_purge_date is not None
        assert mock_user.is_active is False
        assert mock_user.deleted_at is not None

    async def test_soft_delete_sets_30_day_grace_period(self, mock_db, mock_user):
        """Soft delete must set 30-day grace period."""
        # Arrange
        service = DSARService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=False,
            requested_by_user_id="123",
            is_admin=False,
        )

        # Assert
        from datetime import timedelta

        grace_period = result.scheduled_purge_date - result.deleted_at
        assert grace_period.days == 30

    async def test_hard_delete_requires_admin(self, mock_db, mock_user):
        """Hard delete must require admin privileges."""
        # Arrange
        service = DSARService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(DSARAuthorizationError) as exc_info:
            await service.delete_user_data(
                user_id="123",
                tenant_id=1,
                hard_delete=True,  # Hard delete
                requested_by_user_id="123",
                is_admin=False,  # Not admin
            )

        assert "admin privileges" in str(exc_info.value).lower()

    async def test_hard_delete_actually_deletes(self, mock_db, mock_user):
        """Hard delete must permanently remove user."""
        # Arrange
        service = DSARService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        # Act
        result = await service.delete_user_data(
            user_id="123",
            tenant_id=1,
            hard_delete=True,
            requested_by_user_id="admin_456",
            is_admin=True,
        )

        # Assert
        assert result.delete_type == "hard"
        assert result.scheduled_purge_date is None


@pytest.mark.unit
@pytest.mark.gdpr
class TestDSARServiceConfig:
    """Unit tests for DSARService configuration."""

    def test_default_grace_period_is_30_days(self):
        """Default soft delete grace period must be 30 days."""
        from src.core.governance.dsar_service import DSARServiceConfig

        config = DSARServiceConfig()
        assert config.soft_delete_grace_period_days == 30

    def test_default_audit_retention_is_7_years(self):
        """Default audit retention must be 7 years."""
        from src.core.governance.dsar_service import DSARServiceConfig

        config = DSARServiceConfig()
        assert config.audit_retention_years == 7

    def test_custom_config_overrides_defaults(self):
        """Custom config must override defaults."""
        from src.core.governance.dsar_service import DSARServiceConfig

        config = DSARServiceConfig(
            soft_delete_grace_period_days=60,
            audit_retention_years=10,
        )
        assert config.soft_delete_grace_period_days == 60
        assert config.audit_retention_years == 10


# Mark file as test file for pytest
__test__ = True
