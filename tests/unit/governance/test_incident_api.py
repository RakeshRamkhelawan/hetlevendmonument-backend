"""Tests for AI Act Incident Reporting API.

EU AI Act Compliance - Task 5: Incident Reporting (Article 62)
Tests for POST /api/v1/ai-act/incidents endpoint.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_mock_row(
    incident_id: str = "550e8400-e29b-41d4-a716-446655440000",
    severity: str = "high",
    status: str = "reported",
) -> MagicMock:
    row = MagicMock()
    row.id = incident_id
    row.severity = severity
    row.resolution_status = status
    row.incident_type = "unclassified"
    row.agent_id = "agent-001"
    row.agent_name = "Test Agent"
    row.description = "Unexpected output generated"
    row.created_at = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    row.eu_reporting_required = severity in ("high", "critical")
    row.eu_reported_at = None
    return row


def _make_app() -> tuple[FastAPI, MagicMock, MagicMock]:
    """Build a FastAPI test app with mocked auth and db dependencies."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.ai_act.incident_router import router
    from src.core.auth.dependencies import get_current_user

    mock_user = MagicMock()
    mock_user.tenant_id = 1

    mock_db = AsyncMock()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    return app, mock_user, mock_db


class TestIncidentReportingAPI:
    """Test incident reporting endpoints."""

    def test_report_incident_success(self) -> None:
        """Should accept valid incident report and return 201."""
        mock_row = _make_mock_row()
        app, _, _ = _make_app()

        with patch("src.core.api.v1.ai_act.incident_router.IncidentService") as MockSvc:
            svc = AsyncMock()
            svc.create_incident = AsyncMock(return_value=mock_row)
            MockSvc.return_value = svc

            client = TestClient(app)
            payload = {
                "severity": "high",
                "agent_id": "agent-001",
                "agent_name": "Test Agent",
                "description": "Unexpected output generated",
                "details": {"output_sample": "problematic content"},
            }
            response = client.post("/api/v1/ai-act/incidents", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "incident_id" in data
        assert data["severity"] == "high"
        assert data["status"] == "reported"

    def test_report_incident_missing_required_fields(self) -> None:
        """Should reject incident report without required fields (422)."""
        app, _, _ = _make_app()
        client = TestClient(app)

        payload = {"severity": "high"}  # Missing agent_id and description
        response = client.post("/api/v1/ai-act/incidents", json=payload)

        assert response.status_code == 422

    def test_report_incident_invalid_severity(self) -> None:
        """Should reject invalid severity level (422)."""
        app, _, _ = _make_app()
        client = TestClient(app)

        payload = {
            "severity": "invalid",
            "agent_id": "agent-001",
            "description": "Test incident",
        }
        response = client.post("/api/v1/ai-act/incidents", json=payload)

        assert response.status_code == 422

    def test_list_incidents(self) -> None:
        """Should list incidents and return 200 with incidents array."""
        app, _, _ = _make_app()

        with patch("src.core.api.v1.ai_act.incident_router.IncidentService") as MockSvc:
            svc = AsyncMock()
            svc.list_incidents = AsyncMock(return_value=[_make_mock_row()])
            MockSvc.return_value = svc

            client = TestClient(app)
            response = client.get("/api/v1/ai-act/incidents")

        assert response.status_code == 200
        data = response.json()
        assert "incidents" in data
        assert isinstance(data["incidents"], list)

    def test_get_incident_by_id(self) -> None:
        """Should return specific incident by ID."""
        incident_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_row = _make_mock_row(incident_id=incident_id)
        app, _, _ = _make_app()

        with patch("src.core.api.v1.ai_act.incident_router.IncidentService") as MockSvc:
            svc = AsyncMock()
            svc.get_incident = AsyncMock(return_value=mock_row)
            MockSvc.return_value = svc

            client = TestClient(app)
            response = client.get(f"/api/v1/ai-act/incidents/{incident_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == incident_id

    def test_get_nonexistent_incident(self) -> None:
        """Should return 404 for non-existent incident."""
        app, _, _ = _make_app()

        with patch("src.core.api.v1.ai_act.incident_router.IncidentService") as MockSvc:
            svc = AsyncMock()
            svc.get_incident = AsyncMock(return_value=None)
            MockSvc.return_value = svc

            client = TestClient(app)
            response = client.get("/api/v1/ai-act/incidents/nonexistent-id")

        assert response.status_code == 404


class TestIncidentSeverityClassification:
    """Test incident severity classification."""

    def test_critical_incident_requires_immediate_reporting(self) -> None:
        """Critical incidents should flag immediate EU reporting."""
        from src.core.governance.incident_service import classify_severity

        result = classify_severity(
            impact="death",
            scope="widespread",
            reversibility=False,
        )

        assert result == "critical"

    def test_high_incident_serious_harm(self) -> None:
        """High severity for serious harm."""
        from src.core.governance.incident_service import classify_severity

        # Single user serious injury = high (not widespread enough for critical)
        result = classify_severity(
            impact="serious_injury",
            scope="single_user",
            reversibility=True,
        )

        assert result == "high"

    def test_medium_incident_limited_impact(self) -> None:
        """Medium severity for limited impact."""
        from src.core.governance.incident_service import classify_severity

        # Multiple users with minor harm = medium
        result = classify_severity(
            impact="minor_harm",
            scope="multiple_users",
            reversibility=True,
        )

        assert result == "medium"

    def test_low_incident_no_harm(self) -> None:
        """Low severity for no actual harm."""
        from src.core.governance.incident_service import classify_severity

        result = classify_severity(
            impact="none",
            scope="single_user",
            reversibility=True,
        )

        assert result == "low"


class TestIncidentEUReportingFlag:
    """Test EU reporting requirements."""

    def test_critical_requires_eu_reporting(self) -> None:
        """Critical incidents require immediate EU AI Office reporting."""
        from src.core.governance.incident_service import requires_eu_reporting

        assert requires_eu_reporting("critical") is True

    def test_high_may_require_eu_reporting(self) -> None:
        """High severity may require EU reporting based on criteria."""
        from src.core.governance.incident_service import requires_eu_reporting

        assert requires_eu_reporting("high") is True

    def test_medium_does_not_require_eu_reporting(self) -> None:
        """Medium severity does not require EU reporting."""
        from src.core.governance.incident_service import requires_eu_reporting

        assert requires_eu_reporting("medium") is False

    def test_low_does_not_require_eu_reporting(self) -> None:
        """Low severity does not require EU reporting."""
        from src.core.governance.incident_service import requires_eu_reporting

        assert requires_eu_reporting("low") is False
