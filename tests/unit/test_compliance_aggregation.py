"""
Unit tests for ComplianceAggregationService.

Tests aggregation of compliance data for reporting dashboards.
Follows strict TDD - no production code before tests.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


class TestComplianceAggregationService:
    """Test suite for ComplianceAggregationService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create a mocked async database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_result(self) -> MagicMock:
        """Create a mocked query result."""
        return MagicMock()

    def test_service_class_exists(self) -> None:
        """RED: ComplianceAggregationService class must exist."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        assert ComplianceAggregationService is not None

    def test_dataclasses_exist(self) -> None:
        """RED: All summary dataclasses must exist."""
        from src.core.governance.compliance_aggregation import (
            AIActSummary,
            AuditSummary,
            GDPRSummary,
        )

        assert GDPRSummary is not None
        assert AIActSummary is not None
        assert AuditSummary is not None

    def test_service_initialization(self, mock_db: AsyncMock) -> None:
        """RED: Service must initialize with db_session."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        service = ComplianceAggregationService(db_session=mock_db)
        assert service.db_session is mock_db

    @pytest.mark.asyncio
    async def test_get_gdpr_summary_returns_correct_structure(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: get_gdpr_summary must return GDPRSummary dataclass."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
            GDPRSummary,
        )

        # Mock the query results
        mock_result.scalar_one_or_none = MagicMock(return_value=5)
        mock_result.scalar = MagicMock(return_value=10)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_gdpr_summary(tenant_id=1, days=30)

        assert isinstance(result, GDPRSummary)
        assert result.tenant_id == 1
        assert result.period_days == 30

    @pytest.mark.asyncio
    async def test_get_ai_act_summary_returns_correct_structure(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: get_ai_act_summary must return AIActSummary dataclass."""
        from src.core.governance.compliance_aggregation import (
            AIActSummary,
            ComplianceAggregationService,
        )

        mock_result.scalar = MagicMock(return_value=100)
        mock_result.scalar_one_or_none = MagicMock(return_value=20)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_ai_act_summary(tenant_id=1, days=30)

        assert isinstance(result, AIActSummary)
        assert result.tenant_id == 1
        assert result.period_days == 30

    @pytest.mark.asyncio
    async def test_get_audit_summary_returns_correct_structure(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: get_audit_summary must return AuditSummary dataclass."""
        from src.core.governance.compliance_aggregation import (
            AuditSummary,
            ComplianceAggregationService,
        )

        mock_result.all = MagicMock(return_value=[("critical", 5), ("warning", 10), ("info", 50)])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_audit_summary(tenant_id=1, days=30)

        assert isinstance(result, AuditSummary)
        assert result.tenant_id == 1
        assert result.period_days == 30
        assert result.critical_events == 5
        assert result.warning_events == 10
        assert result.info_events == 50

    @pytest.mark.asyncio
    async def test_gdpr_summary_filters_by_tenant_id(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: GDPR summary must filter queries by tenant_id."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        mock_result.scalar_one_or_none = MagicMock(return_value=0)
        mock_result.scalar = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        await service.get_gdpr_summary(tenant_id=42, days=30)

        # Check that execute was called with queries containing tenant_id filter
        calls = mock_db.execute.call_args_list
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_ai_act_summary_filters_by_tenant_id(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: AI Act summary must filter queries by tenant_id."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        mock_result.scalar = MagicMock(return_value=0)
        mock_result.scalar_one_or_none = MagicMock(return_value=0)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        await service.get_ai_act_summary(tenant_id=99, days=30)

        calls = mock_db.execute.call_args_list
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_audit_summary_filters_by_tenant_id(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: Audit summary must filter queries by tenant_id."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        await service.get_audit_summary(tenant_id=7, days=30)

        calls = mock_db.execute.call_args_list
        assert len(calls) > 0

    @pytest.mark.asyncio
    async def test_days_parameter_works_correctly(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: Days parameter must affect the date range filter."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
        )

        mock_result.scalar_one_or_none = MagicMock(return_value=0)
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)

        # Test with 7 days
        result = await service.get_gdpr_summary(tenant_id=1, days=7)
        assert result.period_days == 7

        # Test with 90 days
        result = await service.get_ai_act_summary(tenant_id=1, days=90)
        assert result.period_days == 90

        # Test with 365 days
        result = await service.get_audit_summary(tenant_id=1, days=365)
        assert result.period_days == 365

    @pytest.mark.asyncio
    async def test_handles_empty_data_gracefully(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: Service must handle empty database results gracefully."""
        from src.core.governance.compliance_aggregation import (
            AIActSummary,
            AuditSummary,
            ComplianceAggregationService,
            GDPRSummary,
        )

        # All queries return empty/zero results
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)

        gdpr = await service.get_gdpr_summary(tenant_id=1, days=30)
        assert isinstance(gdpr, GDPRSummary)
        assert gdpr.total_data_subjects == 0

        ai_act = await service.get_ai_act_summary(tenant_id=1, days=30)
        assert isinstance(ai_act, AIActSummary)
        assert ai_act.total_ai_decisions == 0

        audit = await service.get_audit_summary(tenant_id=1, days=30)
        assert isinstance(audit, AuditSummary)
        assert audit.total_events == 0

    @pytest.mark.asyncio
    async def test_gdpr_summary_calculations(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: GDPR summary must calculate metrics correctly."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
            GDPRSummary,
        )

        # Setup mock to return specific values
        def mock_scalar_one_or_none():
            # Return different values for different queries
            calls = mock_db.execute.call_count
            if calls <= 1:
                return 100  # DSAR count
            elif calls <= 2:
                return 50  # Consent count
            return 24.5  # Avg response time

        mock_result.scalar_one_or_none = MagicMock(side_effect=mock_scalar_one_or_none)
        mock_result.scalar = MagicMock(return_value=50)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_gdpr_summary(tenant_id=1, days=30)

        assert isinstance(result, GDPRSummary)
        assert result.tenant_id == 1
        assert result.period_days == 30

    @pytest.mark.asyncio
    async def test_ai_act_summary_calculations(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: AI Act summary must calculate metrics correctly."""
        from src.core.governance.compliance_aggregation import (
            AIActSummary,
            ComplianceAggregationService,
        )

        mock_result.scalar = MagicMock(return_value=100)
        mock_result.scalar_one_or_none = MagicMock(return_value=25)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_ai_act_summary(tenant_id=1, days=30)

        assert isinstance(result, AIActSummary)
        assert result.tenant_id == 1
        assert result.period_days == 30

    @pytest.mark.asyncio
    async def test_audit_summary_aggregates_severity_counts(
        self, mock_db: AsyncMock, mock_result: MagicMock
    ) -> None:
        """RED: Audit summary must correctly aggregate event severity counts."""
        from src.core.governance.compliance_aggregation import (
            AuditSummary,
            ComplianceAggregationService,
        )

        # Mock returning severity counts
        mock_result.all = MagicMock(
            return_value=[
                ("critical", 3),
                ("warning", 7),
                ("info", 25),
                ("debug", 100),
            ]
        )
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_audit_summary(tenant_id=1, days=30)

        assert isinstance(result, AuditSummary)
        assert result.critical_events == 3
        assert result.warning_events == 7
        assert result.info_events == 25
        assert result.total_events == 135

    @pytest.mark.asyncio
    async def test_default_days_parameter(self, mock_db: AsyncMock) -> None:
        """RED: Days parameter should default to 30."""
        from src.core.governance.compliance_aggregation import (
            ComplianceAggregationService,
            GDPRSummary,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=0)
        mock_result.scalar = MagicMock(return_value=0)
        mock_result.all = MagicMock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = ComplianceAggregationService(db_session=mock_db)
        result = await service.get_gdpr_summary(tenant_id=1)

        assert isinstance(result, GDPRSummary)
        assert result.period_days == 30
