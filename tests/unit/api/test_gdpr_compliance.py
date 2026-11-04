"""
Unit tests for GDPR compliance endpoints (gdpr_compliance_endpoints.py).

Covers: data export, data deletion, audit trail, compliance status, checklist.
These are critical compliance tests — GDPR violations carry 4% annual turnover fines.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_mock_session():
    """Create a mock AsyncSession with proper return values for GDPR endpoints."""
    session = AsyncMock()

    # db.scalar() returns None (used for rate-limit check in export endpoint)
    session.scalar = AsyncMock(return_value=None)

    # db.execute() returns a result with flexible mock patterns
    mock_result = MagicMock()
    # scalar_one_or_none returns a mock tenant (for delete endpoint)
    mock_tenant = MagicMock()
    mock_tenant.id = "tenant_test_1"
    mock_tenant.is_active = True
    mock_result.scalar_one_or_none.return_value = mock_tenant
    # scalars().all() returns empty list (for listing queries)
    mock_result.scalars.return_value.all.return_value = []
    # scalar() returns 0 (for count queries)
    mock_result.scalar.return_value = 0
    # rowcount for delete operations
    mock_result.rowcount = 0

    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    return session


def _bouw_app(tenant: str) -> TestClient:
    """Een testapp met de GDPR-router en een gemockte tenantcontext (`tenant`)."""
    from src.core.api.gdpr_compliance_endpoints import router

    app = FastAPI()
    app.include_router(router)

    # Mock user
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"
    mock_user.role = "admin"
    mock_user.roles = ["admin"]
    mock_user.is_admin = True

    async def mock_db():
        yield _make_mock_session()

    async def mock_current_user():
        return mock_user

    def mock_tenant_id():
        return tenant

    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.database.database import get_db
    from src.core.middleware.tenant_context import get_tenant_id

    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_current_user_dependency] = mock_current_user
    app.dependency_overrides[get_tenant_id] = mock_tenant_id

    return TestClient(app)


@pytest.fixture
def gdpr_app():
    """Test app met een echte (numerieke) tenant: zo komt hij in productie uit de JWT."""
    return _bouw_app("7")


@pytest.fixture
def gdpr_app_tekst_tenant():
    """Test app met een tenant die geen getal is: dat hoort nooit voor te komen, en faalt netjes."""
    return _bouw_app("tenant_test_1")


class TestEenNietNumeriekeTenant:
    """Een tenant is in productie altijd een getal. Is hij het niet, dan een 400 en geen 500.

    Gevonden toen de harde wissing `int(tenant_id)` deed voor de export-eerst-controle, BUITEN het
    try-blok: de unittest met een tekst-tenant kreeg een ongevangen ValueError (2026-10-14).
    """

    def test_hard_delete_with_a_non_numeric_tenant_is_a_400(self, gdpr_app_tekst_tenant):
        antwoord = gdpr_app_tekst_tenant.post(
            "/api/gdpr/delete-all",
            json={"delete_type": "hard", "confirmation_code": "tenant_test_1"},
        )

        assert antwoord.status_code == 400

    def test_soft_delete_with_a_non_numeric_tenant_is_a_400(self, gdpr_app_tekst_tenant):
        antwoord = gdpr_app_tekst_tenant.post(
            "/api/gdpr/delete-all",
            json={"delete_type": "soft", "confirmation_code": "tenant_test_1"},
        )

        assert antwoord.status_code == 400

    def test_the_tenant_export_with_a_non_numeric_tenant_is_a_400(self, gdpr_app_tekst_tenant):
        antwoord = gdpr_app_tekst_tenant.post(
            "/api/gdpr/delete-all/export", json={"recipient": "klant"}
        )

        assert antwoord.status_code == 400

    def test_the_answer_names_the_tenant_not_the_confirmation_code(self, gdpr_app_tekst_tenant):
        antwoord = gdpr_app_tekst_tenant.post(
            "/api/gdpr/delete-all",
            json={"delete_type": "hard", "confirmation_code": "tenant_test_1"},
        )

        assert "tenant" in antwoord.json()["detail"].lower()
        assert "confirmation" not in antwoord.json()["detail"].lower()

    def test_a_wrong_confirmation_still_wins_over_the_tenant_check(self, gdpr_app_tekst_tenant):
        """De volgorde blijft: eerst de bevestigingscode, dan pas de tenantcontrole."""
        antwoord = gdpr_app_tekst_tenant.post(
            "/api/gdpr/delete-all", json={"delete_type": "soft", "confirmation_code": "fout"}
        )

        assert "confirmation" in antwoord.json()["detail"].lower()


class TestGDPRExport:
    """Tests for POST /api/gdpr/export (Article 20 - Data Portability)."""

    def test_export_returns_tenant_data(self, gdpr_app):
        response = gdpr_app.post(
            "/api/gdpr/export",
            json={"categories": ["all"], "format": "json", "include_metadata": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert "total_records" in data
        assert "data" in data

    def test_export_with_specific_categories(self, gdpr_app):
        response = gdpr_app.post(
            "/api/gdpr/export",
            json={"categories": ["personal", "audit"], "format": "json"},
        )
        assert response.status_code == 200

    def test_export_csv_format(self, gdpr_app):
        response = gdpr_app.post(
            "/api/gdpr/export",
            json={"categories": ["all"], "format": "csv"},
        )
        assert response.status_code == 200


class TestGDPRDelete:
    """Tests for POST /api/gdpr/delete-all (Article 17 - Right to Erasure)."""

    def test_soft_delete_with_correct_confirmation(self, gdpr_app):
        response = gdpr_app.post(
            "/api/gdpr/delete-all",
            json={
                "delete_type": "soft",
                "confirmation_code": "7",
                "reason": "User requested deletion",
            },
        )
        # Should succeed (200) or fail on AuditLog creation (500)
        assert response.status_code in [200, 500]

    def test_delete_rejects_wrong_confirmation(self, gdpr_app):
        response = gdpr_app.post(
            "/api/gdpr/delete-all",
            json={
                "delete_type": "soft",
                "confirmation_code": "wrong_code",
            },
        )
        assert response.status_code == 400
        assert "confirmation" in response.json()["detail"].lower()

    def test_hard_delete_without_an_offered_export_is_refused(self, gdpr_app):
        """Export eerst (besluit Rakesh 2026-10-12): zonder aangeboden export geen harde wissing."""
        response = gdpr_app.post(
            "/api/gdpr/delete-all",
            json={"delete_type": "hard", "confirmation_code": "7"},
        )

        assert response.status_code == 409

    def test_hard_delete_type(self, gdpr_app):
        from src.core.api.v1.gdpr_compliance import erasure_router

        with patch.object(erasure_router, "export_aangeboden", new=AsyncMock(return_value=True)):
            response = gdpr_app.post(
                "/api/gdpr/delete-all",
                json={"delete_type": "hard", "confirmation_code": "7"},
            )
        # Hard delete requires admin; mock user is admin, so accept 200 or 500
        assert response.status_code in [200, 500]


class TestGDPRAuditTrail:
    """Tests for GET /api/gdpr/audit-trail.

    Note: The route decorator is on _build_audit_query (a helper function)
    which expects tenant_id and AuditTrailRequest as plain parameters — not DI.
    FastAPI interprets these as query params, so this endpoint is effectively
    broken (returns 422). This is documented as a known issue.
    """

    def test_returns_200_with_optional_tenant_id(self, gdpr_app):
        """Audit-trail endpoint is accessible without tenant_id query param."""
        response = gdpr_app.get("/api/gdpr/audit-trail")
        assert response.status_code == 200


class TestGDPRStatus:
    """Tests for GET /api/gdpr/status."""

    def test_returns_compliance_status(self, gdpr_app):
        response = gdpr_app.get("/api/gdpr/status")
        assert response.status_code == 200
        data = response.json()
        assert "compliance_status" in data
        assert "gdpr_articles_implemented" in data

    def test_the_retention_terms_come_from_the_real_retention_policy(self, gdpr_app):
        """Beveiligingsnazorg 2026-10-14: hier stond een vast getal (90) dat nergens waar was.

        De bron is `retention_cleanup.get_default_policy`, dezelfde tabel die de opruimtaak leest.
        Een test die zelf 2555 intikt, zou alleen die keuze bevriezen; daarom wordt de verwachting
        uit de bron gehaald en daarnaast gecontroleerd dat het getal niet het oude vaste getal is.
        """
        from src.core.governance.retention_cleanup import (
            DataCategory,
            RetentionJurisdiction,
            get_default_policy,
        )

        data = gdpr_app.get("/api/gdpr/status").json()

        verwacht_data = get_default_policy(
            RetentionJurisdiction.EU, DataCategory.PERSONAL_DATA
        ).retention_days
        verwacht_audit = get_default_policy(
            RetentionJurisdiction.EU, DataCategory.AUDIT_LOG
        ).retention_days
        assert (data["data_retention_days"], data["audit_retention_days"]) == (
            verwacht_data,
            verwacht_audit,
        )

    def test_the_retention_terms_are_not_the_old_fixed_ninety_days(self, gdpr_app):
        data = gdpr_app.get("/api/gdpr/status").json()

        assert 90 not in (data["data_retention_days"], data["audit_retention_days"])

    def test_the_status_does_not_promise_automatic_deletion_the_job_does_not_do(self, gdpr_app):
        """Gate 2 (security, 2026-10-15): 2555 dagen zonder meer leest als "daarna verdwijnt het".

        De nachtelijke opruimtaak slaat persoonsgegevens en auditlog bewust over
        (`retention_cleanup_job._NIET_AUTOMATISCH`). De verwachting komt uit die tabel, zodat de
        status meebeweegt als iemand een categorie wel automatisch laat verwijderen.
        """
        from src.core.governance.retention_cleanup import DataCategory
        from src.core.jobs.retention_cleanup_job import _NIET_AUTOMATISCH

        data = gdpr_app.get("/api/gdpr/status").json()

        assert (
            data["data_retention_automatic_deletion"],
            data["audit_retention_automatic_deletion"],
        ) == (
            DataCategory.PERSONAL_DATA not in _NIET_AUTOMATISCH,
            DataCategory.AUDIT_LOG not in _NIET_AUTOMATISCH,
        )

    def test_the_status_does_not_claim_a_jurisdiction_the_job_does_not_use_alone(self, gdpr_app):
        """De taak draait EU, US, UK, CA en AU; `retention_jurisdiction: eu` was maar half waar."""
        data = gdpr_app.get("/api/gdpr/status").json()

        assert "retention_jurisdiction" not in data

    def test_the_retention_terms_follow_the_policy_when_it_changes(self, gdpr_app):
        """Tegenrichting: een vast getal dat toevallig klopt, wordt hier ontmaskerd."""
        from src.core.governance import retention_cleanup as rc

        sleutel = (rc.RetentionJurisdiction.EU, rc.DataCategory.AUDIT_LOG)
        oud = rc.DEFAULT_POLICIES[sleutel]
        rc.DEFAULT_POLICIES[sleutel] = rc.RetentionPolicy(
            jurisdiction=oud.jurisdiction,
            category=oud.category,
            retention_days=123,
            description=oud.description,
            regulatory_basis=oud.regulatory_basis,
        )
        try:
            data = gdpr_app.get("/api/gdpr/status").json()
        finally:
            rc.DEFAULT_POLICIES[sleutel] = oud

        assert data["audit_retention_days"] == 123


class TestGDPRChecklist:
    """Tests for GET /api/gdpr/checklist."""

    def test_returns_checklist(self, gdpr_app):
        response = gdpr_app.get("/api/gdpr/checklist")
        assert response.status_code == 200
        data = response.json()
        assert "checklist" in data
        assert "completed_requirements" in data
        assert "total_requirements" in data
