"""Tests for Art. 17 Quality Management System.

EU AI Act Compliance - Art. 17: Quality management system.
"""

from __future__ import annotations

import pytest

from src.core.governance.quality_management import (
    QualityCheck,
    QualityCheckResult,
    QualityCheckType,
    QualityGate,
)


class TestQualityCheckTypeEnum:
    """QualityCheckType enum tests."""

    def test_all_four_types_exist(self) -> None:
        values = {t.value for t in QualityCheckType}
        assert values == {
            "pre_deployment",
            "post_deployment",
            "periodic_review",
            "incident_triggered",
        }


class TestQualityCheckResultEnum:
    """QualityCheckResult enum tests."""

    def test_all_three_results_exist(self) -> None:
        values = {r.value for r in QualityCheckResult}
        assert values == {"pass", "fail", "warning"}


class TestQualityCheckModel:
    """QualityCheck SQLAlchemy model structure."""

    def test_tablename(self) -> None:
        assert QualityCheck.__tablename__ == "governance_quality_checks"

    def test_has_tenant_id_column(self) -> None:
        assert "tenant_id" in QualityCheck.__table__.c

    def test_tenant_id_is_not_nullable(self) -> None:
        col = QualityCheck.__table__.c["tenant_id"]
        assert col.nullable is False

    def test_has_required_columns(self) -> None:
        cols = set(QualityCheck.__table__.c.keys())
        required = {
            "id",
            "tenant_id",
            "agent_name",
            "check_type",
            "result",
            "checked_at",
        }
        assert required.issubset(cols)


class TestQualityGateRequiredChecks:
    """QualityGate.REQUIRED_CHECKS covers all Art. 17 mandatory items."""

    def test_required_checks_is_list(self) -> None:
        assert isinstance(QualityGate.REQUIRED_CHECKS, list)
        assert len(QualityGate.REQUIRED_CHECKS) >= 6

    def test_required_checks_covers_art9_risk_classification(self) -> None:
        assert "risk_classification" in QualityGate.REQUIRED_CHECKS

    def test_required_checks_covers_art12_provenance(self) -> None:
        assert "model_provenance" in QualityGate.REQUIRED_CHECKS

    def test_required_checks_covers_art13_model_card(self) -> None:
        assert "model_card_complete" in QualityGate.REQUIRED_CHECKS

    def test_required_checks_covers_art14_human_oversight(self) -> None:
        assert "human_oversight_configured" in QualityGate.REQUIRED_CHECKS

    def test_required_checks_covers_art15_accuracy_baseline(self) -> None:
        assert "accuracy_baseline_set" in QualityGate.REQUIRED_CHECKS

    def test_required_checks_covers_art52_attribution(self) -> None:
        assert "attribution_configured" in QualityGate.REQUIRED_CHECKS


class TestQualityGateInit:
    """QualityGate initialization."""

    def test_init_accepts_db_session(self) -> None:
        from unittest.mock import MagicMock

        gate = QualityGate(db=MagicMock())
        assert gate is not None
