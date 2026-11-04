"""SP-E04: AI Act incident + model provenance -> DB.

Tests verify that:
- _incident_store and _provenance_store module-level singletons are removed
- IncidentReportDB and ModelProvenanceDB ORM models exist in governance/models.py
- Both models conform to ADR-005 (tenant_id NOT NULL, RESTRICT FK) and ADR-031
- clock_timestamp() used as server_default (CLAUDE.md ss11.5)
- soft-delete column present (EU AI Act 10-year retention)
"""

import pytest


@pytest.mark.unit
class TestIncidentReportModel:
    def test_incident_report_model_exists(self):
        """IncidentReportDB ORM model exists in governance/models.py."""
        from src.core.governance.models import IncidentReportDB

        assert IncidentReportDB is not None

    def test_incident_report_has_table_name(self):
        """Table is named ai_act_incident_reports."""
        from src.core.governance.models import IncidentReportDB

        assert IncidentReportDB.__tablename__ == "ai_act_incident_reports"

    def test_incident_report_tenant_id_not_null(self):
        """tenant_id is NOT NULL (ADR-005)."""
        from src.core.governance.models import IncidentReportDB

        col = IncidentReportDB.__table__.c.tenant_id
        assert col.nullable is False

    def test_incident_report_has_soft_delete(self):
        """deleted_at column present for 10-year EU AI Act retention (ADR-031)."""
        from src.core.governance.models import IncidentReportDB

        assert hasattr(IncidentReportDB, "deleted_at")

    def test_incident_report_uses_clock_timestamp(self):
        """created_at uses clock_timestamp() server_default (CLAUDE.md ss11.5)."""
        from src.core.governance.models import IncidentReportDB

        col = IncidentReportDB.__table__.c.created_at
        sd = str(col.server_default.arg) if col.server_default else ""
        assert "clock_timestamp" in sd

    def test_incident_report_has_no_tenant_fk_so_it_survives_a_tenant_removal(self):
        """Geen vreemde sleutel naar `tenants`: de meldingen BLIJVEN bestaan als de tenant wordt opgeheven.

        Tot 2026-10-12 stond hier `ondelete=RESTRICT` ("EU AI Act 10-year retention"): de database
        weigerde dan de tenant te verwijderen zolang er een melding was. Besluit Rakesh 2026-10-12
        (AVG C): de melding wordt BEWAARD en geanonimiseerd (`avg_auditlog.py`), de tenantrij mag
        weg, en de koppeling is daarom losgelaten (migratie 20261012_audit_geen_tenant_fk). De
        bewaarplicht zelf is niet veranderd; alleen het mechanisme.
        """
        from src.core.governance.models import IncidentReportDB

        tenant_fks = [fk for fk in IncidentReportDB.__table__.foreign_keys if "tenants" in str(fk.column)]

        assert tenant_fks == []

    def test_incident_report_has_incident_type(self):
        """incident_type column exists (maps IncidentSeverity.severity)."""
        from src.core.governance.models import IncidentReportDB

        assert hasattr(IncidentReportDB, "incident_type")

    def test_incident_report_has_severity(self):
        """severity column exists."""
        from src.core.governance.models import IncidentReportDB

        assert hasattr(IncidentReportDB, "severity")

    def test_incident_report_has_eu_reporting_required(self):
        """eu_reporting_required column exists (Article 62 flag)."""
        from src.core.governance.models import IncidentReportDB

        assert hasattr(IncidentReportDB, "eu_reporting_required")


@pytest.mark.unit
class TestIncidentStoreSingletonRemoved:
    def test_incident_store_singleton_removed(self):
        """_incident_store module-level dict has been removed."""
        import src.core.governance.incident_service as mod

        assert not hasattr(mod, "_incident_store"), (
            "_incident_store must be removed; use IncidentReportDB ORM instead"
        )


@pytest.mark.unit
class TestProvenanceRecordModel:
    def test_provenance_record_model_exists(self):
        """ModelProvenanceDB ORM model exists in governance/models.py."""
        from src.core.governance.models import ModelProvenanceDB

        assert ModelProvenanceDB is not None

    def test_provenance_has_table_name(self):
        """Table is named model_provenance_records."""
        from src.core.governance.models import ModelProvenanceDB

        assert ModelProvenanceDB.__tablename__ == "model_provenance_records"

    def test_provenance_tenant_id_not_null(self):
        """tenant_id is NOT NULL (ADR-005)."""
        from src.core.governance.models import ModelProvenanceDB

        col = ModelProvenanceDB.__table__.c.tenant_id
        assert col.nullable is False

    def test_provenance_store_singleton_removed(self):
        """_provenance_store module-level dict has been removed."""
        import src.core.governance.model_provenance as mod

        assert not hasattr(mod, "_provenance_store"), (
            "_provenance_store must be removed; use ModelProvenanceDB ORM instead"
        )

    def test_provenance_has_soft_delete(self):
        """deleted_at column present for retention requirement (ADR-031)."""
        from src.core.governance.models import ModelProvenanceDB

        assert hasattr(ModelProvenanceDB, "deleted_at")

    def test_provenance_uses_clock_timestamp(self):
        """registered_at uses clock_timestamp() server_default (CLAUDE.md ss11.5)."""
        from src.core.governance.models import ModelProvenanceDB

        col = ModelProvenanceDB.__table__.c.registered_at
        sd = str(col.server_default.arg) if col.server_default else ""
        assert "clock_timestamp" in sd

    def test_provenance_tenant_fk_restrict(self):
        """tenant_id FK has ondelete=RESTRICT."""
        from src.core.governance.models import ModelProvenanceDB

        for fk in ModelProvenanceDB.__table__.foreign_keys:
            if "tenant" in str(fk.column):
                assert fk.ondelete == "RESTRICT"
                return
        pytest.fail("No tenant FK found on ModelProvenanceDB")

    def test_provenance_has_provider(self):
        """provider column exists (LLM provider name)."""
        from src.core.governance.models import ModelProvenanceDB

        assert hasattr(ModelProvenanceDB, "provider")

    def test_provenance_has_input_hash(self):
        """input_hash column exists (Article 53 requirement)."""
        from src.core.governance.models import ModelProvenanceDB

        assert hasattr(ModelProvenanceDB, "input_hash")

    def test_provenance_has_output_hash(self):
        """output_hash column exists (Article 53 requirement)."""
        from src.core.governance.models import ModelProvenanceDB

        assert hasattr(ModelProvenanceDB, "output_hash")

    def test_provenance_has_retention_until(self):
        """retention_until column exists (Article 12 -- 6 months default)."""
        from src.core.governance.models import ModelProvenanceDB

        assert hasattr(ModelProvenanceDB, "retention_until")
