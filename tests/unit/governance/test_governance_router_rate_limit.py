"""Tests for rate limiting on Governance REST API endpoints."""

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

    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_tenant_id] = lambda: 1
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=7)
    app.dependency_overrides[_require_governance_read] = lambda: 1

    return app, TestClient(app)


class TestGovernanceReadRateLimit:
    """Governance read endpoints are rate-limited to 60/min."""

    def test_alerts_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(
            InMemoryRateLimiter,
            "is_allowed",
            return_value=False,
        ):
            response = client.get("/api/v1/governance/alerts")
        assert response.status_code == 429
        assert "error" in response.json()["detail"]

    def test_risk_register_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(
            InMemoryRateLimiter,
            "is_allowed",
            return_value=False,
        ):
            response = client.get("/api/v1/governance/risk-register")
        assert response.status_code == 429

    def test_accuracy_report_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(
            InMemoryRateLimiter,
            "is_allowed",
            return_value=False,
        ):
            response = client.get("/api/v1/governance/accuracy/BotX")
        assert response.status_code == 429

    def test_authority_reports_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(
            InMemoryRateLimiter,
            "is_allowed",
            return_value=False,
        ):
            response = client.get("/api/v1/governance/authority-reports")
        assert response.status_code == 429


class TestGovernanceWriteRateLimit:
    """Governance write endpoints are rate-limited to 10/min."""

    def test_quality_check_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(
            InMemoryRateLimiter,
            "is_allowed",
            return_value=False,
        ):
            response = client.post("/api/v1/governance/quality-check/BotY")
        assert response.status_code == 429
