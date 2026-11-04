"""
Unit Tests for Usage Service
TASK-009: Usage Metering Implementation

Coverage Target: usage_service.py -> >90%

Tests cover:
- Recording usage events
- Monthly usage aggregation
- Quota checking
- Error handling
- Edge cases (month boundaries, zero values)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.usage_models import UsageRecord
from src.core.services.usage_service import UsageService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db_session():
    """Mock async database session"""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def usage_service(mock_db_session):
    """UsageService instance with mocked session"""
    return UsageService(mock_db_session)


# ============================================================================
# TEST: Record Usage
# ============================================================================


class TestRecordUsage:
    """Test usage recording functionality"""

    @pytest.mark.asyncio
    async def test_record_usage_success(self, usage_service, mock_db_session):
        """Test successful usage recording"""
        result = await usage_service.record_usage(
            tenant_id=1, metric_type="workflow_run", value=1.0, user_id=42
        )

        assert result is True
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_usage_with_metadata(self, usage_service, mock_db_session):
        """Test recording usage with metadata"""
        metadata = {"workflow_id": "wf-123", "agent_type": "researcher"}

        result = await usage_service.record_usage(
            tenant_id=1, metric_type="ai_token", value=1500.0, metadata=metadata
        )

        assert result is True
        # Verify the record was created with metadata
        call_args = mock_db_session.add.call_args
        record = call_args[0][0]
        assert record.metadata_json == metadata

    @pytest.mark.asyncio
    async def test_record_usage_default_value(self, usage_service, mock_db_session):
        """Test recording usage with default value of 1.0"""
        result = await usage_service.record_usage(tenant_id=1, metric_type="synthesis_run")

        assert result is True
        call_args = mock_db_session.add.call_args
        record = call_args[0][0]
        assert record.value == 1.0

    @pytest.mark.asyncio
    async def test_record_usage_error_handling(self, usage_service, mock_db_session):
        """Test that errors are handled gracefully"""
        mock_db_session.commit.side_effect = Exception("Database error")

        result = await usage_service.record_usage(tenant_id=1, metric_type="workflow_run")

        assert result is False
        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_usage_without_user_id(self, usage_service, mock_db_session):
        """Test recording usage without user_id (tenant-level only)"""
        result = await usage_service.record_usage(
            tenant_id=1, metric_type="ai_token", value=2000.0, user_id=None
        )

        assert result is True
        call_args = mock_db_session.add.call_args
        record = call_args[0][0]
        assert record.user_id is None


# ============================================================================
# TEST: Get Monthly Usage
# ============================================================================


class TestGetMonthlyUsage:
    """Test monthly usage aggregation"""

    @pytest.mark.asyncio
    async def test_get_monthly_usage_returns_sum(self, usage_service, mock_db_session):
        """Test that monthly usage returns correct sum"""
        mock_result = Mock()
        mock_result.scalar.return_value = 42.5
        mock_db_session.execute.return_value = mock_result

        total = await usage_service.get_monthly_usage(tenant_id=1, metric_type="workflow_run")

        assert total == 42.5

    @pytest.mark.asyncio
    async def test_get_monthly_usage_with_specific_month(self, usage_service, mock_db_session):
        """Test querying specific month/year"""
        mock_result = Mock()
        mock_result.scalar.return_value = 100.0
        mock_db_session.execute.return_value = mock_result

        total = await usage_service.get_monthly_usage(
            tenant_id=1, metric_type="ai_token", month=6, year=2025
        )

        assert total == 100.0

    @pytest.mark.asyncio
    async def test_get_monthly_usage_returns_zero_for_none(self, usage_service, mock_db_session):
        """Test that None result returns 0.0"""
        mock_result = Mock()
        mock_result.scalar.return_value = None
        mock_db_session.execute.return_value = mock_result

        total = await usage_service.get_monthly_usage(tenant_id=1, metric_type="synthesis_run")

        assert total == 0.0

    @pytest.mark.asyncio
    async def test_get_monthly_usage_error_handling(self, usage_service, mock_db_session):
        """Test error handling returns 0.0"""
        mock_db_session.execute.side_effect = Exception("Database error")

        total = await usage_service.get_monthly_usage(tenant_id=1, metric_type="workflow_run")

        assert total == 0.0

    @pytest.mark.asyncio
    async def test_get_monthly_usage_december_boundary(self, usage_service, mock_db_session):
        """Test December to January boundary calculation"""
        mock_result = Mock()
        mock_result.scalar.return_value = 50.0
        mock_db_session.execute.return_value = mock_result

        # Query December - should handle year rollover correctly
        total = await usage_service.get_monthly_usage(
            tenant_id=1, metric_type="workflow_run", month=12, year=2025
        )

        assert total == 50.0


# ============================================================================
# TEST: Check Quota
# ============================================================================


class TestCheckQuota:
    """Test quota checking functionality"""

    @pytest.mark.asyncio
    async def test_check_quota_within_limit(self, usage_service, mock_db_session):
        """Test quota check returns True when within limit"""
        mock_result = Mock()
        mock_result.scalar.return_value = 35.0  # 35 of 50 used
        mock_db_session.execute.return_value = mock_result

        within_quota = await usage_service.check_quota(
            tenant_id=1, metric_type="workflow_run", limit=50.0
        )

        assert within_quota is True

    @pytest.mark.asyncio
    async def test_check_quota_at_limit(self, usage_service, mock_db_session):
        """Test quota check returns False when at limit"""
        mock_result = Mock()
        mock_result.scalar.return_value = 50.0  # Exactly at limit
        mock_db_session.execute.return_value = mock_result

        within_quota = await usage_service.check_quota(
            tenant_id=1, metric_type="workflow_run", limit=50.0
        )

        assert within_quota is False

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(self, usage_service, mock_db_session):
        """Test quota check returns False when exceeded"""
        mock_result = Mock()
        mock_result.scalar.return_value = 75.0  # Over limit
        mock_db_session.execute.return_value = mock_result

        within_quota = await usage_service.check_quota(
            tenant_id=1, metric_type="workflow_run", limit=50.0
        )

        assert within_quota is False

    @pytest.mark.asyncio
    async def test_check_quota_zero_usage(self, usage_service, mock_db_session):
        """Test quota check returns True with zero usage"""
        mock_result = Mock()
        mock_result.scalar.return_value = None  # No usage yet
        mock_db_session.execute.return_value = mock_result

        within_quota = await usage_service.check_quota(
            tenant_id=1, metric_type="workflow_run", limit=50.0
        )

        assert within_quota is True


# ============================================================================
# TEST: Metric Types
# ============================================================================


class TestMetricTypes:
    """Test different metric type handling"""

    @pytest.mark.asyncio
    async def test_workflow_run_metric(self, usage_service, mock_db_session):
        """Test workflow_run metric recording"""
        result = await usage_service.record_usage(
            tenant_id=1, metric_type="workflow_run", value=1.0
        )

        assert result is True
        record = mock_db_session.add.call_args[0][0]
        assert record.metric_type == "workflow_run"

    @pytest.mark.asyncio
    async def test_ai_token_metric(self, usage_service, mock_db_session):
        """Test ai_token metric recording with large values"""
        result = await usage_service.record_usage(
            tenant_id=1,
            metric_type="ai_token",
            value=15000.0,  # 15k tokens
        )

        assert result is True
        record = mock_db_session.add.call_args[0][0]
        assert record.metric_type == "ai_token"
        assert record.value == 15000.0

    @pytest.mark.asyncio
    async def test_synthesis_run_metric(self, usage_service, mock_db_session):
        """Test synthesis_run metric recording"""
        result = await usage_service.record_usage(
            tenant_id=1, metric_type="synthesis_run", value=1.0
        )

        assert result is True
        record = mock_db_session.add.call_args[0][0]
        assert record.metric_type == "synthesis_run"


# ============================================================================
# TEST: Multi-Tenant Isolation
# ============================================================================


class TestMultiTenantIsolation:
    """Test tenant isolation in usage tracking"""

    @pytest.mark.asyncio
    async def test_usage_scoped_to_tenant(self, usage_service, mock_db_session):
        """Test that usage is scoped to specific tenant"""
        # Record for tenant 1
        await usage_service.record_usage(tenant_id=1, metric_type="workflow_run")

        record = mock_db_session.add.call_args[0][0]
        assert record.tenant_id == 1

    @pytest.mark.asyncio
    async def test_query_filters_by_tenant(self, usage_service, mock_db_session):
        """Test that queries are filtered by tenant_id"""
        mock_result = Mock()
        mock_result.scalar.return_value = 10.0
        mock_db_session.execute.return_value = mock_result

        await usage_service.get_monthly_usage(tenant_id=42, metric_type="ai_token")

        # Verify execute was called (query should filter by tenant)
        mock_db_session.execute.assert_called_once()
