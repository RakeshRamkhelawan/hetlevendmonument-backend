"""
Unit tests for Compliance API schemas.

Sprint 7, Task 1.2 - TDD: RED phase first.
"""

from datetime import datetime, timezone

import pytest


class TestComplianceScoreResponse:
    """Test ComplianceScoreResponse Pydantic schema."""

    def test_schema_exists(self):
        """RED: ComplianceScoreResponse schema must exist."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        assert ComplianceScoreResponse is not None

    def test_schema_has_required_fields(self):
        """RED: Schema must have all required fields."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        # Create instance with all required fields
        calculated_at = datetime.now(timezone.utc)
        response = ComplianceScoreResponse(
            overall_score=87.5,
            gdpr_score=90.0,
            ai_act_score=85.0,
            audit_score=88.0,
            calculated_at=calculated_at,
            tenant_id=123,
        )

        assert response.overall_score == 87.5
        assert response.gdpr_score == 90.0
        assert response.ai_act_score == 85.0
        assert response.audit_score == 88.0
        assert response.calculated_at == calculated_at
        assert response.tenant_id == 123

    def test_schema_validation_error_on_missing_fields(self):
        """RED: Schema must reject missing required fields."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        with pytest.raises(Exception):  # Pydantic validation error
            ComplianceScoreResponse(
                overall_score=87.5,
                # Missing other required fields
            )

    def test_schema_score_ranges(self):
        """RED: Schema should validate score ranges (0-100)."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        calculated_at = datetime.now(timezone.utc)

        # Valid scores at boundaries
        response_min = ComplianceScoreResponse(
            overall_score=0.0,
            gdpr_score=0.0,
            ai_act_score=0.0,
            audit_score=0.0,
            calculated_at=calculated_at,
            tenant_id=1,
        )
        assert response_min.overall_score == 0.0

        response_max = ComplianceScoreResponse(
            overall_score=100.0,
            gdpr_score=100.0,
            ai_act_score=100.0,
            audit_score=100.0,
            calculated_at=calculated_at,
            tenant_id=1,
        )
        assert response_max.overall_score == 100.0

    def test_schema_serialization(self):
        """RED: Schema must serialize to dict correctly."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        calculated_at = datetime.now(timezone.utc)
        response = ComplianceScoreResponse(
            overall_score=87.5,
            gdpr_score=90.0,
            ai_act_score=85.0,
            audit_score=88.0,
            calculated_at=calculated_at,
            tenant_id=123,
        )

        data = response.model_dump()
        assert data["overall_score"] == 87.5
        assert data["gdpr_score"] == 90.0
        assert data["ai_act_score"] == 85.0
        assert data["audit_score"] == 88.0
        assert data["tenant_id"] == 123

    def test_schema_json_serialization(self):
        """RED: Schema must serialize to JSON correctly."""
        from src.core.api.v1.compliance.schemas import ComplianceScoreResponse

        calculated_at = datetime.now(timezone.utc)
        response = ComplianceScoreResponse(
            overall_score=87.5,
            gdpr_score=90.0,
            ai_act_score=85.0,
            audit_score=88.0,
            calculated_at=calculated_at,
            tenant_id=123,
        )

        json_str = response.model_dump_json()
        assert "87.5" in json_str
        assert "90.0" in json_str
        assert "85.0" in json_str
        assert "88.0" in json_str
        assert "123" in json_str
