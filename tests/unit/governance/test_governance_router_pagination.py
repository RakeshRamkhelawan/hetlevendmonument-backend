"""Tests for pagination on Governance REST API list endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_db_mock_with_items(items: list) -> AsyncMock:
    """Return an AsyncMock that returns the given items for paginated queries."""
    db = AsyncMock()

    def _execute(query):
        result = MagicMock()
        # First call is count query -> scalar returns total
        # Subsequent calls are paginated queries -> scalars().all() returns items
        result.scalar.return_value = len(items)
        result.scalars.return_value.all.return_value = items
        return result

    db.execute.side_effect = _execute
    return db


def _make_app(items: list | None = None) -> tuple[FastAPI, TestClient]:
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

    db_mock = _make_db_mock_with_items(items or [])

    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_tenant_id] = lambda: 1
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=7)
    app.dependency_overrides[_require_governance_read] = lambda: 1

    return app, TestClient(app)


class TestListAlertsPagination:
    """GET /alerts supports limit and offset pagination."""

    def test_alerts_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_alerts_default_limit_is_50(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert response.json()["limit"] == 50

    def test_alerts_default_offset_is_0(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts")
        assert response.json()["offset"] == 0

    def test_alerts_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts?limit=1001")
        assert response.status_code == 422

    def test_alerts_rejects_negative_offset(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts?offset=-1")
        assert response.status_code == 422

    def test_alerts_rejects_zero_limit(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/alerts?limit=0")
        assert response.status_code == 422


class TestListRiskEntriesPagination:
    """GET /risk-register supports limit and offset pagination."""

    def test_risk_register_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/risk-register")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_risk_register_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/risk-register?limit=2000")
        assert response.status_code == 422


class TestListAuthorityReportsPagination:
    """GET /authority-reports supports limit and offset pagination."""

    def test_authority_reports_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/authority-reports")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_authority_reports_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/governance/authority-reports?limit=5000")
        assert response.status_code == 422
