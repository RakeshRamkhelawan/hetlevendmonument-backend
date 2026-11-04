"""Tests for tenant_id filter in privacy forget_me endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.governance.rate_limiter import InMemoryRateLimiter


def _make_app() -> tuple[FastAPI, TestClient, AsyncMock]:
    """Build a minimal FastAPI app with the privacy router and mocked deps."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.privacy.router import (
        get_current_user,
        router,
    )

    app = FastAPI()
    app.include_router(router)

    db_mock = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar.return_value = 0
    execute_result.scalars.return_value.all.return_value = []
    db_mock.execute.return_value = execute_result

    user_mock = MagicMock()
    user_mock.id = 7
    user_mock.tenant_id = 1
    user_mock.email = "test@example.com"

    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: user_mock

    return app, TestClient(app), db_mock


class TestForgetMeTenantIsolation:
    """POST /forget includes tenant_id in all DELETE queries."""

    def test_forget_me_returns_200_with_matching_email(self) -> None:
        _, client, _ = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.post(
                "/api/v1/privacy/forget",
                json={"confirm_email": "test@example.com", "reason": "testing"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_forget_me_returns_400_with_mismatched_email(self) -> None:
        _, client, _ = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.post(
                "/api/v1/privacy/forget",
                json={"confirm_email": "wrong@example.com", "reason": "testing"},
            )
        assert response.status_code == 400

    def test_forget_me_deletes_only_current_tenant_data(self) -> None:
        _, client, db_mock = _make_app()
        with patch.object(InMemoryRateLimiter, "is_allowed", return_value=True):
            response = client.post(
                "/api/v1/privacy/forget",
                json={"confirm_email": "test@example.com", "reason": "testing"},
            )
        assert response.status_code == 200

        # Verify execute was called at least 3 times for the DELETE statements
        calls = db_mock.execute.call_args_list
        assert len(calls) >= 3, f"Expected at least 3 execute calls, got {len(calls)}"

        # Verify tenant_id appears in the where clauses of DELETE queries.
        # SQLAlchemy Delete objects have a 'whereclause' attribute.
        from sqlalchemy.sql import Delete

        delete_calls = [c for c in calls if len(c.args) > 0 and isinstance(c.args[0], Delete)]
        assert len(delete_calls) >= 3, f"Expected at least 3 DELETE calls, got {len(delete_calls)}"

        for call in delete_calls:
            query = call.args[0]
            query_str = str(query.compile(compile_kwargs={"literal_binds": True}))
            assert "tenant_id" in query_str, f"DELETE query missing tenant_id filter: {query_str}"
