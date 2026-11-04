"""Een refresh zonder refresh-token (geen body-veld, geen cookie) geeft 401, geen 422.

Gemeten 2026-10-05 (nazorgtoets scenario 5): de browser stuurt `{"grant_type": "refresh_token"}`
en verwacht dat de backend het refresh-cookie leest. Het schema eiste `refresh_token` in de body,
dus FastAPI weigerde met 422 voordat de cookie-terugval in de route ooit draaide.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.auth.auth_config import auth_limiter
from src.core.api.auth.dependencies import get_db
from src.core.api.auth.router_token import router


def _client() -> TestClient:
    app = FastAPI()
    app.state.limiter = auth_limiter
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    return TestClient(app)


def test_refresh_with_only_grant_type_and_no_cookie_returns_401() -> None:
    response = _client().post("/refresh", json={"grant_type": "refresh_token"})

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Refresh token required"
