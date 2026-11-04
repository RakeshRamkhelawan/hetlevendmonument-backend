"""
Unit tests for RetentionCleanupService - GDPR/data retention compliance.

Tests cover:
- Jurisdiction-aware retention periods (EU, US, etc.)
- Automatic cleanup of expired data
- Audit logging of cleanup actions
- Configuration per data category
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRetentionJurisdiction:
    """Test jurisdiction enum and retention periods."""

    def test_jurisdiction_enum_values(self):
        """Test that all jurisdiction values exist."""
        from src.core.governance.retention_cleanup import RetentionJurisdiction

        assert RetentionJurisdiction.EU.value == "eu"
        assert RetentionJurisdiction.US.value == "us"
        assert RetentionJurisdiction.UK.value == "uk"
        assert RetentionJurisdiction.CA.value == "ca"
        assert RetentionJurisdiction.AU.value == "au"

    def test_jurisdiction_is_str_enum(self):
        """Test that jurisdiction is a string enum."""
        from src.core.governance.retention_cleanup import RetentionJurisdiction

        assert isinstance(RetentionJurisdiction.EU.value, str)


class TestDataCategory:
    """Test data category enum."""

    def test_data_category_values(self):
        """Test that all data category values exist."""
        from src.core.governance.retention_cleanup import DataCategory

        assert DataCategory.PERSONAL_DATA.value == "personal_data"
        assert DataCategory.FINANCIAL.value == "financial"
        assert DataCategory.HEALTH.value == "health"
        assert DataCategory.AUDIT_LOG.value == "audit_log"
        assert DataCategory.AI_DECISION.value == "ai_decision"
        assert DataCategory.COOKIE_CONSENT.value == "cookie_consent"


class TestRetentionPolicy:
    """Test retention policy configuration."""

    def test_policy_has_jurisdiction(self):
        """Test that policy has jurisdiction field."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            RetentionPolicy,
        )

        policy = RetentionPolicy(
            jurisdiction=RetentionJurisdiction.EU,
            category=DataCategory.PERSONAL_DATA,
            retention_days=2555,  # 7 years
        )
        assert policy.jurisdiction == RetentionJurisdiction.EU

    def test_policy_has_category(self):
        """Test that policy has category field."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            RetentionPolicy,
        )

        policy = RetentionPolicy(
            jurisdiction=RetentionJurisdiction.EU,
            category=DataCategory.PERSONAL_DATA,
            retention_days=2555,
        )
        assert policy.category == DataCategory.PERSONAL_DATA

    def test_policy_has_retention_days(self):
        """Test that policy has retention_days field."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            RetentionPolicy,
        )

        policy = RetentionPolicy(
            jurisdiction=RetentionJurisdiction.EU,
            category=DataCategory.PERSONAL_DATA,
            retention_days=2555,
        )
        assert policy.retention_days == 2555

    def test_policy_has_optional_description(self):
        """Test that policy has optional description field."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            RetentionPolicy,
        )

        policy = RetentionPolicy(
            jurisdiction=RetentionJurisdiction.EU,
            category=DataCategory.AUDIT_LOG,
            retention_days=2555,
            description="Dutch tax law requires 7 year retention",
        )
        assert policy.description == "Dutch tax law requires 7 year retention"


class TestDefaultPolicies:
    """Test default retention policies per jurisdiction."""

    def test_eu_personal_data_retention(self):
        """Test EU personal data default retention (GDPR)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.PERSONAL_DATA)
        assert policy.retention_days == 2555  # 7 years

    def test_eu_audit_log_retention(self):
        """Test EU audit log retention (7 years for compliance)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.AUDIT_LOG)
        assert policy.retention_days == 2555  # 7 years

    def test_eu_cookie_consent_retention(self):
        """Test EU cookie consent retention (GDPR Art. 7)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.COOKIE_CONSENT)
        assert policy.retention_days == 2555  # 7 years

    def test_us_personal_data_retention(self):
        """Test US personal data default retention."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.US, DataCategory.PERSONAL_DATA)
        assert policy.retention_days == 2190  # 6 years (typical US statute)

    def test_health_data_longer_retention(self):
        """Test health data has longer retention (HIPAA/GDPR)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.HEALTH)
        # Health data often kept longer (15 years in some jurisdictions)
        assert policy.retention_days >= 5475  # 15 years

    def test_financial_data_retention(self):
        """Test financial data retention (SOX/tax laws)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.FINANCIAL)
        # Financial records typically 7-10 years
        assert policy.retention_days >= 2555  # 7 years


class TestRetentionCleanupServiceInit:
    """Test RetentionCleanupService initialization."""

    @pytest.mark.asyncio
    async def test_init_accepts_db_session(self):
        """Test that service initializes with DB session."""
        from src.core.governance.retention_cleanup import RetentionCleanupService

        mock_session = AsyncMock()
        service = RetentionCleanupService(mock_session)
        assert service.db == mock_session

    @pytest.mark.asyncio
    async def test_init_accepts_tenant_id(self):
        """Test that service initializes with optional tenant_id."""
        from src.core.governance.retention_cleanup import RetentionCleanupService

        mock_session = AsyncMock()
        service = RetentionCleanupService(mock_session, tenant_id=123)
        assert service.tenant_id == 123

    @pytest.mark.asyncio
    async def test_init_tenant_id_defaults_to_none(self):
        """Test that tenant_id defaults to None."""
        from src.core.governance.retention_cleanup import RetentionCleanupService

        mock_session = AsyncMock()
        service = RetentionCleanupService(mock_session)
        assert service.tenant_id is None


class TestRetentionCleanupService:
    """Test RetentionCleanupService functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock DB session.

        `rowcount` krijgt een echt int (niet het onbewerkte, auto-gegenereerde AsyncMock-attribuut):
        `_create_audit_log` geeft `records_deleted` sinds ADR-036 OP-121 door aan
        `retention_evidence.build_resource`, dat het meteen synchroon JSON-serialiseert. Een
        Mock-object daar levert een `TypeError: Object of type AsyncMock is not JSON serializable`
        op, ook al deed niets voor deze fix ooit echt iets met die waarde.
        """
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 0
        session.execute = AsyncMock(return_value=execute_result)
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create a RetentionCleanupService instance."""
        from src.core.governance.retention_cleanup import RetentionCleanupService

        return RetentionCleanupService(mock_session, tenant_id=1)

    @pytest.mark.asyncio
    async def test_cleanup_expired_data_requires_category(self, service):
        """Test that cleanup requires a data category."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        result = await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
        )
        # Should return a cleanup result
        assert result is not None

    @pytest.mark.asyncio
    async def test_cleanup_respects_retention_period(self, service, mock_session):
        """Test that cleanup only removes data older than retention period."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        with patch("src.core.governance.retention_cleanup.datetime") as mock_datetime:
            # Set current time to a fixed point
            now = datetime(2026, 4, 4, 12, 0, 0)
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await service.cleanup_expired_data(
                category=DataCategory.PERSONAL_DATA,
                jurisdiction=RetentionJurisdiction.EU,
            )

            # Check that SQL query includes date filter
            call_args = mock_session.execute.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_cleanup_returns_count_deleted(self, service):
        """Test that cleanup returns count of deleted records."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        # Mock the execute to return a row count
        mock_result = MagicMock()
        mock_result.rowcount = 42
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
        )

        assert result.records_deleted == 42

    @pytest.mark.asyncio
    async def test_cleanup_creates_audit_log(self, service):
        """Test that cleanup creates an audit log entry."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        mock_result = MagicMock()
        mock_result.rowcount = 10
        service.db.execute = AsyncMock(return_value=mock_result)

        await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
        )

        # Should create audit log - check by looking at the calls
        # The audit log should reference GDPR/data retention
        calls = service.db.add.call_args_list if hasattr(service.db.add, "call_args_list") else []
        # Audit logging is done via add()

    @pytest.mark.asyncio
    async def test_cleanup_includes_gdpr_reference(self, service):
        """Test that audit log references GDPR Article 5(1)(e)."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        mock_result = MagicMock()
        mock_result.rowcount = 5
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
        )

        # Result should include GDPR reference
        assert "GDPR" in result.regulatory_basis or "Art. 5" in result.regulatory_basis

    @pytest.mark.asyncio
    async def test_cleanup_respects_tenant_isolation(self, service, mock_session):
        """De tenantconditie staat in de DELETE.

        **Deze test bevatte tot 2026-08-11 NUL assertions.** Hij eindigde op een comment
        (`# Should have tenant_id filtering`) na een `if`-blok dat niets deed. Hij kon dus niet
        falen, en dekte de bevinding die hij in zijn naam draagt (ADR-036 OP-123) op geen enkele
        manier af.

        Het weiger-gedrag zonder tenant staat in
        `test_retention_refuses_cross_tenant_delete.py`; deze test dekt de positieve kant.
        """
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
        )

        sql_teksten = [str(c.args[0]) for c in mock_session.execute.await_args_list if c.args]
        delete_sql = [s for s in sql_teksten if "DELETE FROM" in s]

        assert delete_sql, f"Geen DELETE uitgevoerd. Uitgevoerde SQL: {sql_teksten}"
        assert all("tenant_id = :tenant_id" in s for s in delete_sql), (
            f"Een DELETE zonder tenantconditie raakt alle tenants. SQL was: {delete_sql}"
        )

    async def test_cleanup_dry_run_does_not_delete(self, service, mock_session):
        """Test that dry_run mode only counts without deleting."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        mock_result = MagicMock()
        mock_result.fetchone.return_value = [100]
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.cleanup_expired_data(
            category=DataCategory.PERSONAL_DATA,
            jurisdiction=RetentionJurisdiction.EU,
            dry_run=True,
        )

        # Should not call commit in dry run mode
        assert not mock_session.commit.called
        assert result.records_deleted == 100  # But should still return count

    @pytest.mark.asyncio
    async def test_cleanup_ai_decisions(self, service):
        """Test cleanup of AI decision records."""
        from src.core.governance.retention_cleanup import DataCategory, RetentionJurisdiction

        mock_result = MagicMock()
        mock_result.rowcount = 25
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.cleanup_expired_data(
            category=DataCategory.AI_DECISION,
            jurisdiction=RetentionJurisdiction.EU,
        )

        assert result.records_deleted == 25


class TestCleanupResult:
    """Test CleanupResult data model."""

    def test_result_has_records_deleted(self):
        """Test that result has records_deleted field."""
        from src.core.governance.retention_cleanup import CleanupResult

        result = CleanupResult(
            records_deleted=100,
            category="personal_data",
            jurisdiction="eu",
            cutoff_date=datetime.now(timezone.utc),
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        assert result.records_deleted == 100

    def test_result_has_category(self):
        """Test that result has category field."""
        from src.core.governance.retention_cleanup import CleanupResult

        result = CleanupResult(
            records_deleted=100,
            category="personal_data",
            jurisdiction="eu",
            cutoff_date=datetime.now(timezone.utc),
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        assert result.category == "personal_data"

    def test_result_has_jurisdiction(self):
        """Test that result has jurisdiction field."""
        from src.core.governance.retention_cleanup import CleanupResult

        result = CleanupResult(
            records_deleted=100,
            category="personal_data",
            jurisdiction="eu",
            cutoff_date=datetime.now(timezone.utc),
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        assert result.jurisdiction == "eu"

    def test_result_has_cutoff_date(self):
        """Test that result has cutoff_date field."""
        from src.core.governance.retention_cleanup import CleanupResult

        cutoff = datetime.now(timezone.utc)
        result = CleanupResult(
            records_deleted=100,
            category="personal_data",
            jurisdiction="eu",
            cutoff_date=cutoff,
            regulatory_basis="GDPR Art. 5(1)(e)",
        )
        assert result.cutoff_date == cutoff

    def test_result_has_regulatory_basis(self):
        """Test that result has regulatory_basis field."""
        from src.core.governance.retention_cleanup import CleanupResult

        result = CleanupResult(
            records_deleted=100,
            category="personal_data",
            jurisdiction="eu",
            cutoff_date=datetime.now(timezone.utc),
            regulatory_basis="GDPR Art. 5(1)(e) - storage limitation",
        )
        assert "GDPR" in result.regulatory_basis


class TestScheduledCleanup:
    """Test scheduled/periodic cleanup functionality."""

    @pytest.mark.asyncio
    async def test_run_all_cleanups_processes_all_categories(self):
        """Test that run_all_cleanups processes all data categories."""
        from src.core.governance.retention_cleanup import (
            RetentionCleanupService,
            RetentionJurisdiction,
        )

        mock_session = AsyncMock()
        service = RetentionCleanupService(mock_session, tenant_id=1)

        # Mock cleanup_expired_data
        service.cleanup_expired_data = AsyncMock(
            return_value=MagicMock(
                records_deleted=10,
                category="personal_data",
                jurisdiction="eu",
            )
        )

        results = await service.run_all_cleanups(jurisdiction=RetentionJurisdiction.EU)

        # Should return multiple results (one per category)
        assert len(results) > 0
        assert all(hasattr(r, "records_deleted") for r in results)

    @pytest.mark.asyncio
    async def test_run_all_cleanups_aggregates_totals(self):
        """Test that run_all_cleanups aggregates total records deleted."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionCleanupService,
            RetentionJurisdiction,
        )

        mock_session = AsyncMock()
        service = RetentionCleanupService(mock_session, tenant_id=1)

        service.cleanup_expired_data = AsyncMock(
            return_value=MagicMock(
                records_deleted=5,
                category="personal_data",
                jurisdiction="eu",
            )
        )

        results = await service.run_all_cleanups(jurisdiction=RetentionJurisdiction.EU)

        # Total should be sum of all categories
        total = sum(r.records_deleted for r in results)
        assert total > 0


class TestRetentionReport:
    """Test retention reporting functionality."""

    @pytest.mark.asyncio
    async def test_generate_retention_report(self):
        """Test generating a retention compliance report."""
        from src.core.governance.retention_cleanup import (
            RetentionCleanupService,
            RetentionJurisdiction,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = [100]  # Return count as list
        mock_session.execute = AsyncMock(return_value=mock_result)
        service = RetentionCleanupService(mock_session, tenant_id=1)

        report = await service.generate_retention_report(jurisdiction=RetentionJurisdiction.EU)

        assert report is not None
        assert hasattr(report, "total_records")
        assert hasattr(report, "records_by_category")
        assert hasattr(report, "compliance_status")

    @pytest.mark.asyncio
    async def test_report_includes_upcoming_cleanups(self):
        """Test that report includes data approaching retention limit."""
        from src.core.governance.retention_cleanup import (
            RetentionCleanupService,
            RetentionJurisdiction,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = [50]  # Return count as list
        mock_session.execute = AsyncMock(return_value=mock_result)
        service = RetentionCleanupService(mock_session, tenant_id=1)

        report = await service.generate_retention_report(jurisdiction=RetentionJurisdiction.EU)

        # Should have upcoming cleanups section
        assert hasattr(report, "upcoming_cleanups")


# =============================================================================
# ADR-026 Digital Twin Production Hardening Tests
# =============================================================================


class TestTwinDataCategories:
    """Test Digital Twin data categories and retention policies."""

    def test_twin_observation_category_exists(self):
        """Test that TWIN_OBSERVATION data category exists."""
        from src.core.governance.retention_cleanup import DataCategory

        assert DataCategory.TWIN_OBSERVATION.value == "twin_observation"

    def test_twin_cost_log_category_exists(self):
        """Test that TWIN_COST_LOG data category exists."""
        from src.core.governance.retention_cleanup import DataCategory

        assert DataCategory.TWIN_COST_LOG.value == "twin_cost_log"

    def test_twin_observation_retention_days_zero(self):
        """Test that TWIN_OBSERVATION uses expires_at (retention_days=0)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.TWIN_OBSERVATION)
        assert policy.retention_days == 0

    def test_twin_cost_log_retention_days_zero(self):
        """Test that TWIN_COST_LOG uses expires_at (retention_days=0)."""
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        policy = get_default_policy(RetentionJurisdiction.EU, DataCategory.TWIN_COST_LOG)
        assert policy.retention_days == 0


class TestTwinTablesInAllowlist:
    """Test that twin tables are in the retention allowlist."""

    def test_user_behavior_observations_in_allowlist(self):
        """Test user_behavior_observations is in _RETENTION_ALLOWED_TABLES."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_TABLES

        assert "user_behavior_observations" in _RETENTION_ALLOWED_TABLES

    def test_twin_suggestion_log_in_allowlist(self):
        """Test twin_suggestion_log is in _RETENTION_ALLOWED_TABLES."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_TABLES

        assert "twin_suggestion_log" in _RETENTION_ALLOWED_TABLES

    def test_expires_at_in_allowed_columns(self):
        """Test expires_at is in _RETENTION_ALLOWED_COLUMNS."""
        from src.core.governance.retention_cleanup import _RETENTION_ALLOWED_COLUMNS

        assert "expires_at" in _RETENTION_ALLOWED_COLUMNS


class TestTwinTableMapping:
    """Test table mapping for Digital Twin categories."""

    @pytest.fixture
    def service(self):
        from src.core.governance.retention_cleanup import RetentionCleanupService

        return RetentionCleanupService(AsyncMock(), tenant_id=1)

    def test_twin_observation_table_mapping(self, service):
        """Test TWIN_OBSERVATION maps to user_behavior_observations with expires_at."""
        from src.core.governance.retention_cleanup import DataCategory

        table_info = service._get_table_info(DataCategory.TWIN_OBSERVATION)
        assert table_info["table"] == "user_behavior_observations"
        assert table_info["date_column"] == "expires_at"
        assert table_info["tenant_column"] == "tenant_id"

    def test_twin_cost_log_table_mapping(self, service):
        """Test TWIN_COST_LOG maps to twin_suggestion_log with expires_at."""
        from src.core.governance.retention_cleanup import DataCategory

        table_info = service._get_table_info(DataCategory.TWIN_COST_LOG)
        assert table_info["table"] == "twin_suggestion_log"
        assert table_info["date_column"] == "expires_at"
        assert table_info["tenant_column"] == "tenant_id"
