"""Tests for pagination on Compliance REST API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.governance.rate_limiter import InMemoryRateLimiter


def _make_db_mock() -> AsyncMock:
    """Return an AsyncMock that looks like an AsyncSession."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar.return_value = 0
    execute_result.scalars.return_value.all.return_value = []
    db.execute.return_value = execute_result
    return db


def _make_app() -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with the compliance router and mocked deps."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.compliance.router import (
        get_current_user,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    db_mock = _make_db_mock()

    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: MagicMock(
        id=7, tenant_id=1, email="test@example.com"
    )

    return app, TestClient(app)


class TestComplianceScoreHistoryPagination:
    """GET /score/history supports limit and offset pagination."""

    def test_score_history_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/score/history")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_score_history_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/score/history?limit=1001")
        assert response.status_code == 422


class TestDSARReportPagination:
    """GET /report/gdpr/dsar supports limit and offset pagination."""

    def test_dsar_report_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/report/gdpr/dsar")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_dsar_report_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/report/gdpr/dsar?limit=2000")
        assert response.status_code == 422


class TestAIActDecisionsPagination:
    """GET /report/ai-act/decisions supports limit and offset pagination."""

    def test_ai_act_decisions_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/report/ai-act/decisions")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_ai_act_decisions_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.get("/compliance/report/ai-act/decisions?limit=5000")
        assert response.status_code == 422
