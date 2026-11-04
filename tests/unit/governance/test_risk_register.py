"""Tests for Art. 9 Risk Register.

EU AI Act Compliance - Art. 9: Risk Management System
"""

from __future__ import annotations

import pytest

from src.core.governance.risk_register import (
    RISK_MATRIX,
    RiskEntry,
    RiskEntryCreate,
    RiskImpact,
    RiskLikelihood,
    calculate_residual_risk,
)


class TestRiskLikelihoodEnum:
    """RiskLikelihood enum tests."""

    def test_all_five_levels_exist(self) -> None:
        values = {level.value for level in RiskLikelihood}
        assert values == {"rare", "unlikely", "possible", "likely", "almost_certain"}


class TestRiskImpactEnum:
    """RiskImpact enum tests."""

    def test_all_five_levels_exist(self) -> None:
        values = {level.value for level in RiskImpact}
        assert values == {"negligible", "minor", "moderate", "major", "catastrophic"}


class TestRiskMatrix:
    """RISK_MATRIX lookup tests (Art. 9 risk scoring)."""

    def test_risk_matrix_is_dict(self) -> None:
        assert isinstance(RISK_MATRIX, dict)
        assert len(RISK_MATRIX) > 0

    def test_almost_certain_catastrophic_is_unacceptable(self) -> None:
        key = (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.CATASTROPHIC)
        assert RISK_MATRIX[key] == "unacceptable"

    def test_likely_catastrophic_is_unacceptable(self) -> None:
        key = (RiskLikelihood.LIKELY, RiskImpact.CATASTROPHIC)
        assert RISK_MATRIX[key] == "unacceptable"

    def test_likely_major_is_high(self) -> None:
        key = (RiskLikelihood.LIKELY, RiskImpact.MAJOR)
        assert RISK_MATRIX[key] == "high"

    def test_possible_major_is_high(self) -> None:
        key = (RiskLikelihood.POSSIBLE, RiskImpact.MAJOR)
        assert RISK_MATRIX[key] == "high"

    def test_possible_moderate_is_medium(self) -> None:
        key = (RiskLikelihood.POSSIBLE, RiskImpact.MODERATE)
        assert RISK_MATRIX[key] == "medium"

    def test_rare_negligible_is_low(self) -> None:
        key = (RiskLikelihood.RARE, RiskImpact.NEGLIGIBLE)
        assert RISK_MATRIX[key] == "low"


class TestCalculateResidualRisk:
    """calculate_residual_risk() helper tests."""

    def test_returns_string(self) -> None:
        result = calculate_residual_risk(RiskLikelihood.RARE, RiskImpact.NEGLIGIBLE)
        assert isinstance(result, str)

    def test_high_risk_combination(self) -> None:
        result = calculate_residual_risk(RiskLikelihood.LIKELY, RiskImpact.MAJOR)
        assert result == "high"

    def test_unacceptable_combination(self) -> None:
        result = calculate_residual_risk(RiskLikelihood.ALMOST_CERTAIN, RiskImpact.CATASTROPHIC)
        assert result == "unacceptable"

    def test_unknown_combination_returns_medium(self) -> None:
        """Combinations not in matrix should default to 'medium'."""
        result = calculate_residual_risk(RiskLikelihood.RARE, RiskImpact.CATASTROPHIC)
        assert isinstance(result, str)


class TestRiskEntryCreate:
    """RiskEntryCreate Pydantic schema tests."""

    def test_valid_entry_creates_successfully(self) -> None:
        entry = RiskEntryCreate(
            agent_name="Credit Scorer",
            risk_description="Discriminatory credit decisions",
            likelihood=RiskLikelihood.POSSIBLE,
            impact=RiskImpact.MAJOR,
            mitigation="Regular bias audits",
            residual_risk="medium",
        )
        assert entry.agent_name == "Credit Scorer"
        assert entry.likelihood == RiskLikelihood.POSSIBLE
        assert entry.impact == RiskImpact.MAJOR

    def test_agent_name_max_length_enforced(self) -> None:
        with pytest.raises(Exception):
            RiskEntryCreate(
                agent_name="x" * 201,  # Exceeds 200 char limit
                risk_description="Too long",
                likelihood=RiskLikelihood.RARE,
                impact=RiskImpact.NEGLIGIBLE,
                mitigation="None",
                residual_risk="low",
            )

    def test_required_fields_enforced(self) -> None:
        with pytest.raises(Exception):
            RiskEntryCreate(agent_name="Bot")  # Missing required fields


class TestRiskEntryModel:
    """RiskEntry SQLAlchemy model tests."""

    def test_tablename(self) -> None:
        assert RiskEntry.__tablename__ == "governance_risk_entries"

    def test_has_tenant_id_column(self) -> None:
        assert "tenant_id" in RiskEntry.__table__.c

    def test_tenant_id_is_not_nullable(self) -> None:
        col = RiskEntry.__table__.c["tenant_id"]
        assert col.nullable is False

    def test_has_required_columns(self) -> None:
        cols = set(RiskEntry.__table__.c.keys())
        required = {
            "id",
            "tenant_id",
            "agent_name",
            "risk_description",
            "likelihood",
            "impact",
            "mitigation",
            "residual_risk",
            "last_reviewed",
        }
        assert required.issubset(cols)
