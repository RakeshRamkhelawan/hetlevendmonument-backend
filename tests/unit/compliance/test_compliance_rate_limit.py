"""Tests for rate limiting on Compliance REST API endpoints."""

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


class TestComplianceReadRateLimit:
    """Compliance read endpoints are rate-limited to 60/min."""

    def test_score_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/score")
        assert response.status_code == 429

    def test_score_history_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/score/history")
        assert response.status_code == 429

    def test_gdpr_summary_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/report/gdpr/summary")
        assert response.status_code == 429

    def test_dsar_report_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/report/gdpr/dsar")
        assert response.status_code == 429

    def test_ai_act_summary_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/report/ai-act/summary")
        assert response.status_code == 429

    def test_ai_act_decisions_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/report/ai-act/decisions")
        assert response.status_code == 429

    def test_integrity_verify_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/integrity/verify")
        assert response.status_code == 429

    def test_integrity_status_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.get("/compliance/integrity/status")
        assert response.status_code == 429


class TestComplianceWriteRateLimit:
    """Compliance write endpoints are rate-limited to 10/min."""

    def test_integrity_verify_entry_returns_429_when_rate_limited(self) -> None:
        _, client = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=False):
            response = client.post(
                "/compliance/integrity/verify-entry",
                json={"entry_id": 12345},
            )
        assert response.status_code == 429
