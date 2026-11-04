"""
Unit tests for ComplianceScoreCalculator service.
Tests compliance score calculation with mocked database.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


class TestComplianceScoreCalculator:
    """Test suite for ComplianceScoreCalculator class."""

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
    def sample_compliance_data(self):
        """Sample compliance data for testing."""
        return {
            "gdpr_score": 85.0,
            "ai_act_score": 90.0,
            "audit_score": 75.0,
            "tenant_id": 1,
        }

    async def test_calculate_overall_score_exists(self, mock_db_session):
        """Test that calculate_overall_score method exists and returns correct structure."""
        # Import here to trigger ImportError if class doesn't exist
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 1

        # Mock the query result for GDPR compliance
        mock_gdpr_result = MagicMock()
        mock_gdpr_result.scalar_one_or_none = Mock(return_value=85.0)

        # Mock the query result for AI Act compliance
        mock_ai_act_result = MagicMock()
        mock_ai_act_result.scalar_one_or_none = Mock(return_value=90.0)

        # Mock the query result for audit logs
        mock_audit_result = MagicMock()
        mock_audit_result.scalar_one_or_none = Mock(return_value=75.0)

        # Set up mock to return different values for each call
        mock_db_session.execute.side_effect = [
            mock_gdpr_result,
            mock_ai_act_result,
            mock_audit_result,
        ]

        # Act
        result = await calculator.calculate_overall_score(tenant_id)

        # Assert
        assert isinstance(result, ComplianceScoreResult)
        assert result.tenant_id == tenant_id
        assert hasattr(result, "overall_score")
        assert hasattr(result, "gdpr_score")
        assert hasattr(result, "ai_act_score")
        assert hasattr(result, "audit_score")
        assert hasattr(result, "calculated_at")

    async def test_calculate_overall_score_weighted_average(self, mock_db_session):
        """Test that overall score is calculated with correct weights."""
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 1

        # Test data with known values
        gdpr_score = 100.0  # weight 40%
        ai_act_score = 0.0  # weight 35%
        audit_score = 0.0  # weight 25%
        # Expected: (100 * 0.40) + (0 * 0.35) + (0 * 0.25) = 40.0

        mock_gdpr_result = MagicMock()
        mock_gdpr_result.scalar_one_or_none = Mock(return_value=gdpr_score)

        mock_ai_act_result = MagicMock()
        mock_ai_act_result.scalar_one_or_none = Mock(return_value=ai_act_score)

        mock_audit_result = MagicMock()
        mock_audit_result.scalar_one_or_none = Mock(return_value=audit_score)

        mock_db_session.execute.side_effect = [
            mock_gdpr_result,
            mock_ai_act_result,
            mock_audit_result,
        ]

        # Act
        result = await calculator.calculate_overall_score(tenant_id)

        # Assert
        assert result.gdpr_score == gdpr_score
        assert result.ai_act_score == ai_act_score
        assert result.audit_score == audit_score
        assert result.overall_score == 40.0  # Only GDPR contributes
        assert result.tenant_id == tenant_id
        assert isinstance(result.calculated_at, datetime)

    async def test_calculate_overall_score_all_components(self, mock_db_session):
        """Test calculation with all components having values."""
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 2

        # Test data: GDPR 40%, AI Act 35%, Audit 25%
        gdpr_score = 80.0
        ai_act_score = 70.0
        audit_score = 90.0
        # Expected: (80 * 0.40) + (70 * 0.35) + (90 * 0.25)
        # = 32.0 + 24.5 + 22.5 = 79.0

        mock_gdpr_result = MagicMock()
        mock_gdpr_result.scalar_one_or_none = Mock(return_value=gdpr_score)

        mock_ai_act_result = MagicMock()
        mock_ai_act_result.scalar_one_or_none = Mock(return_value=ai_act_score)

        mock_audit_result = MagicMock()
        mock_audit_result.scalar_one_or_none = Mock(return_value=audit_score)

        mock_db_session.execute.side_effect = [
            mock_gdpr_result,
            mock_ai_act_result,
            mock_audit_result,
        ]

        # Act
        result = await calculator.calculate_overall_score(tenant_id)

        # Assert
        assert result.overall_score == 79.0
        assert result.gdpr_score == gdpr_score
        assert result.ai_act_score == ai_act_score
        assert result.audit_score == audit_score
        assert result.tenant_id == tenant_id

    async def test_calculate_overall_score_with_none_values(self, mock_db_session):
        """Test handling of None values from database."""
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 3

        # Some scores return None (no data yet)
        mock_gdpr_result = MagicMock()
        mock_gdpr_result.scalar_one_or_none = Mock(return_value=None)

        mock_ai_act_result = MagicMock()
        mock_ai_act_result.scalar_one_or_none = Mock(return_value=50.0)

        mock_audit_result = MagicMock()
        mock_audit_result.scalar_one_or_none = Mock(return_value=None)

        mock_db_session.execute.side_effect = [
            mock_gdpr_result,
            mock_ai_act_result,
            mock_audit_result,
        ]

        # Act
        result = await calculator.calculate_overall_score(tenant_id)

        # Assert - None values should be treated as 0
        assert result.gdpr_score == 0.0
        assert result.ai_act_score == 50.0
        assert result.audit_score == 0.0
        # (0 * 0.40) + (50 * 0.35) + (0 * 0.25) = 17.5
        assert result.overall_score == 17.5

    async def test_get_score_history_exists(self, mock_db_session):
        """Test that get_score_history method exists and returns list."""
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 1

        # Mock result for score history query
        mock_result = MagicMock()
        mock_result.all = Mock(return_value=[])
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await calculator.get_score_history(tenant_id)

        # Assert
        assert isinstance(result, list)

    async def test_get_score_history_returns_results(self, mock_db_session):
        """Test that get_score_history returns ComplianceScoreResult objects."""
        from src.core.governance.compliance_score import (
            ComplianceScoreCalculator,
            ComplianceScoreResult,
        )

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 1
        days = 30

        # Create mock history records
        now = datetime.now(timezone.utc)
        mock_records = [
            (
                75.0,
                80.0,
                70.0,
                75.5,
                now,
                tenant_id,
            ),
            (
                85.0,
                90.0,
                80.0,
                85.5,
                now,
                tenant_id,
            ),
        ]

        mock_result = MagicMock()
        mock_result.all = Mock(return_value=mock_records)
        mock_db_session.execute.return_value = mock_result

        # Act
        history = await calculator.get_score_history(tenant_id, days)

        # Assert
        assert len(history) == 2
        for item in history:
            assert isinstance(item, ComplianceScoreResult)
        assert history[0].gdpr_score == 75.0
        assert history[1].gdpr_score == 85.0

    async def test_get_score_history_default_days(self, mock_db_session):
        """Test that get_score_history uses default of 30 days."""
        from src.core.governance.compliance_score import ComplianceScoreCalculator

        # Arrange
        calculator = ComplianceScoreCalculator(mock_db_session)
        tenant_id = 1

        mock_result = MagicMock()
        mock_result.all = Mock(return_value=[])
        mock_db_session.execute.return_value = mock_result

        # Act - call without specifying days
        await calculator.get_score_history(tenant_id)

        # Assert - query should have been called (we verify the method works)
        assert mock_db_session.execute.called


class TestComplianceScoreResult:
    """Test suite for ComplianceScoreResult dataclass."""

    def test_result_creation(self):
        """Test creating ComplianceScoreResult instance."""
        from src.core.governance.compliance_score import ComplianceScoreResult

        now = datetime.now(timezone.utc)
        result = ComplianceScoreResult(
            overall_score=85.0,
            gdpr_score=90.0,
            ai_act_score=80.0,
            audit_score=85.0,
            calculated_at=now,
            tenant_id=1,
        )

        assert result.overall_score == 85.0
        assert result.gdpr_score == 90.0
        assert result.ai_act_score == 80.0
        assert result.audit_score == 85.0
        assert result.calculated_at == now
        assert result.tenant_id == 1

    def test_result_score_ranges(self):
        """Test that scores are within valid range (0-100)."""
        from src.core.governance.compliance_score import ComplianceScoreResult

        now = datetime.now(timezone.utc)

        # Test minimum scores
        result_min = ComplianceScoreResult(
            overall_score=0.0,
            gdpr_score=0.0,
            ai_act_score=0.0,
            audit_score=0.0,
            calculated_at=now,
            tenant_id=1,
        )
        assert result_min.overall_score == 0.0

        # Test maximum scores
        result_max = ComplianceScoreResult(
            overall_score=100.0,
            gdpr_score=100.0,
            ai_act_score=100.0,
            audit_score=100.0,
            calculated_at=now,
            tenant_id=1,
        )
        assert result_max.overall_score == 100.0
