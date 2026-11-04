"""Tests for Art. 72 Authority Reporting.

EU AI Act Compliance - Art. 72: Market surveillance authority reporting.
"""

from __future__ import annotations

from src.core.governance.authority_reporting import (
    AuthorityReport,
    AuthorityReporter,
    AuthorityReportType,
)


class TestAuthorityReportTypeEnum:
    def test_all_three_types_exist(self) -> None:
        values = {t.value for t in AuthorityReportType}
        assert values == {"incident", "periodic", "conformity"}

    def test_incident_value(self) -> None:
        assert AuthorityReportType.INCIDENT == "incident"

    def test_periodic_value(self) -> None:
        assert AuthorityReportType.PERIODIC == "periodic"

    def test_conformity_value(self) -> None:
        assert AuthorityReportType.CONFORMITY_ASSESSMENT == "conformity"


class TestAuthorityReportModel:
    def test_tablename(self) -> None:
        assert AuthorityReport.__tablename__ == "governance_authority_reports"

    def test_has_tenant_id_column(self) -> None:
        assert "tenant_id" in AuthorityReport.__table__.c

    def test_tenant_id_is_not_nullable(self) -> None:
        assert AuthorityReport.__table__.c["tenant_id"].nullable is False

    def test_has_required_columns(self) -> None:
        cols = set(AuthorityReport.__table__.c.keys())
        required = {
            "id",
            "tenant_id",
            "report_type",
            "authority_name",
            "content",
            "created_at",
        }
        assert required.issubset(cols)

    def test_has_submitted_at_nullable(self) -> None:
        """submitted_at starts null — only set when actually submitted."""
        col = AuthorityReport.__table__.c["submitted_at"]
        assert col.nullable is True


class TestAuthorityReporterConstants:
    def test_authority_ap_constant(self) -> None:
        assert AuthorityReporter.AUTHORITY_AP == "Autoriteit Persoonsgegevens"

    def test_authority_acm_constant(self) -> None:
        assert AuthorityReporter.AUTHORITY_ACM == "Autoriteit Consument & Markt"


class TestAuthorityReporterInit:
    def test_init_accepts_db_session(self) -> None:
        from unittest.mock import MagicMock

        reporter = AuthorityReporter(db=MagicMock())
        assert reporter is not None


class TestAuthorityReporterReportIncident:
    """report_incident() creates an AuthorityReport record."""

    def test_report_incident_method_exists(self) -> None:
        import inspect

        assert hasattr(AuthorityReporter, "report_incident")
        assert inspect.iscoroutinefunction(AuthorityReporter.report_incident)

    def test_report_incident_signature(self) -> None:
        import inspect

        sig = inspect.signature(AuthorityReporter.report_incident)
        params = set(sig.parameters.keys())
        assert {"tenant_id", "incident_type", "agent_name", "details"}.issubset(params)
