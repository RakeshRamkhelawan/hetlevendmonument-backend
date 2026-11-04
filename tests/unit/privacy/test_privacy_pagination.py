"""Tests for pagination on Privacy REST API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_db_mock() -> AsyncMock:
    """Return an AsyncMock that looks like an AsyncSession."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar.return_value = 0
    execute_result.scalars.return_value.all.return_value = []
    db.execute.return_value = execute_result
    return db


def _make_app() -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with the privacy router and mocked deps."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.privacy.router import (
        get_current_user,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    db_mock = _make_db_mock()

    user_mock = MagicMock()
    user_mock.id = 7
    user_mock.tenant_id = 1
    user_mock.email = "test@example.com"

    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: user_mock

    return app, TestClient(app)


class TestGetAiDecisionsPagination:
    """GET /ai-decisions supports limit and offset pagination."""

    def test_ai_decisions_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_ai_decisions_default_limit_is_50(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions")
        assert response.json()["limit"] == 50

    def test_ai_decisions_default_offset_is_0(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions")
        assert response.json()["offset"] == 0

    def test_ai_decisions_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions?limit=1001")
        assert response.status_code == 422

    def test_ai_decisions_rejects_negative_offset(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions?offset=-1")
        assert response.status_code == 422

    def test_ai_decisions_rejects_zero_limit(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/ai-decisions?limit=0")
        assert response.status_code == 422


class TestGetHumanReviewRequestsPagination:
    """GET /human-review-requests supports limit and offset pagination."""

    def test_human_review_requests_returns_pagination_keys(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/human-review-requests")
        assert response.status_code == 200
        body = response.json()
        assert "limit" in body
        assert "offset" in body
        assert "total_count" in body

    def test_human_review_requests_rejects_limit_over_1000(self) -> None:
        _, client = _make_app()
        response = client.get("/api/v1/privacy/human-review-requests?limit=2000")
        assert response.status_code == 422
