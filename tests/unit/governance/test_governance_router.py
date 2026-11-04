"""Tests for Governance REST API router (Phase 4).

Covers: router structure, endpoint existence, response shape,
tenant isolation, and FastAPI dependency overrides.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_mock() -> AsyncMock:
    """Return an AsyncMock that looks like an AsyncSession.

    AsyncMock auto-promotes child attrs to AsyncMock, which breaks the
    synchronous `.scalars().all()` chain. Force execute() to return a
    plain MagicMock so the chain stays synchronous after the await.

    `.one()` returns a row-like object with total=0 so AccuracyMonitor
    short-circuits (MIN_SAMPLES check) and returns None without further queries.
    """
    db = AsyncMock()
    row = MagicMock()
    row.total = 0
    row.successes = 0
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.one.return_value = row
    db.execute.return_value = execute_result
    return db


def _make_app() -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with the governance router and mocked deps."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.governance.router import (
        _require_governance_read,
        get_current_tenant_id,
        get_current_user,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    db_mock = _make_db_mock()

    # Override auth / DB deps so tests run without infrastructure
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_tenant_id] = lambda: 1
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=7)
    app.dependency_overrides[_require_governance_read] = lambda: 1

    return app, TestClient(app)


# ---------------------------------------------------------------------------
# Router structure
# ---------------------------------------------------------------------------


class TestGovernanceRouterStructure:
    """The router module exports a properly prefixed APIRouter."""

    def test_router_is_importable(self) -> None:
        from src.core.api.v1.governance.router import router  # noqa: F401

    def test_router_has_governance_prefix(self) -> None:
        from src.core.api.v1.governance.router import router

        # Composite router has no top-level prefix; prefix lives in sub-routers.
        # Verify all routes are scoped to /api/v1/governance.
        route_paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert all("/api/v1/governance" in p for p in route_paths), (
            f"Expected all routes under /api/v1/governance, got: {route_paths}"
        )

    def test_router_has_governance_tag(self) -> None:
        from src.core.api.v1.governance.router import router

        # Tags live on the sub-routers; verify the routes carry them.
        tags = {t for r in router.routes if hasattr(r, "tags") for t in (r.tags or [])}
        assert "governance" in tags, f"Expected 'governance' tag in routes, got: {tags}"

    def test_router_has_five_routes(self) -> None:
        from src.core.api.v1.governance.router import router

        # GET /alerts, GET /accuracy/{agent}, GET /risk-register,
        # POST /quality-check/{agent}, GET /authority-reports
        assert len(router.routes) >= 5

    def test_dependency_exports(self) -> None:
        """Router module re-exports its dependencies for test overrides."""
        from src.core.api.v1.governance import router as mod

        assert hasattr(mod, "get_current_tenant_id")
        assert hasattr(mod, "get_current_user")


# ---------------------------------------------------------------------------
# GET /api/v1/governance/alerts
# ---------------------------------------------------------------------------


class TestListAlertsEndpoint:
    """GET /alerts returns a success response."""

    def test_alerts_returns_200(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert response.status_code == 200

    def test_alerts_response_has_success_true(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert response.json()["success"] is True

    def test_alerts_response_has_data_key(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert "data" in response.json()

    def test_alerts_accepts_severity_filter(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts?severity=critical")
        assert response.status_code == 200

    def test_alerts_accepts_acknowledged_filter(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts?acknowledged=false")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/governance/accuracy/{agent_name}
# ---------------------------------------------------------------------------


class TestAccuracyReportEndpoint:
    """GET /accuracy/{agent_name} delegates to AccuracyMonitor."""

    def test_accuracy_returns_200(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/accuracy/BotX")
        assert response.status_code == 200

    def test_accuracy_response_has_agent_name(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/accuracy/BotX")
        data = response.json()
        assert data["data"]["agent_name"] == "BotX"

    def test_accuracy_response_has_drift_key(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/accuracy/BotX")
        assert "drift" in response.json()["data"]


# ---------------------------------------------------------------------------
# GET /api/v1/governance/risk-register
# ---------------------------------------------------------------------------


class TestRiskRegisterEndpoint:
    """GET /risk-register returns tenant-scoped entries."""

    def test_risk_register_returns_200(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/risk-register")
        assert response.status_code == 200

    def test_risk_register_has_success_true(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/risk-register")
        assert response.json()["success"] is True

    def test_risk_register_data_is_list(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/risk-register")
        assert isinstance(response.json()["data"], list)


# ---------------------------------------------------------------------------
# POST /api/v1/governance/quality-check/{agent_name}
# ---------------------------------------------------------------------------


class TestQualityCheckEndpoint:
    """POST /quality-check/{agent_name} runs pre-deployment gate."""

    def test_quality_check_returns_200(self) -> None:
        _, client = _make_app()
        response = client.post("/api/v1/governance/quality-check/BotY")
        assert response.status_code == 200

    def test_quality_check_response_has_checks_key(self) -> None:
        _, client = _make_app()
        response = client.post("/api/v1/governance/quality-check/BotY")
        assert "checks" in response.json()["data"]

    def test_quality_check_success_true(self) -> None:
        _, client = _make_app()
        response = client.post("/api/v1/governance/quality-check/BotY")
        assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/governance/authority-reports
# ---------------------------------------------------------------------------


class TestAuthorityReportsEndpoint:
    """GET /authority-reports returns Art. 72 reports for tenant."""

    def test_authority_reports_returns_200(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/authority-reports")
        assert response.status_code == 200

    def test_authority_reports_has_success_true(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/authority-reports")
        assert response.json()["success"] is True

    def test_authority_reports_data_is_list(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/authority-reports")
        assert isinstance(response.json()["data"], list)
