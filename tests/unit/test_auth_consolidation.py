from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient

from src.core.auth import UserResponse
from src.core.auth.dependencies import (
    get_current_user,
    get_current_user_dependency,
    get_token_from_request,
)
from src.core.database.database import get_db


@pytest.fixture(autouse=True)
def _geen_ingetrokken_token(monkeypatch):
    """Deze tests mocken de database, dus ook de intrekkingscontrole (ADR-036 OP-188).

    `_get_user_from_token` raadpleegt sinds 2026-09-15 de blacklist op `jti`. Met een
    `AsyncMock`-database geeft `scalar_one_or_none()` een mock terug, en dat leest als
    "ingetrokken" -- de test faalt dan met een 401 die niets met zijn onderwerp te maken
    heeft. De productiecode is hier correct; de mock is te los.
    """
    from src.core.auth import oauth2_service as _mod

    async def _niet_ingetrokken(self, jti, db):  # noqa: ANN001, ANN202
        return False

    monkeypatch.setattr(_mod.OAuth2Service, "is_jti_revoked", _niet_ingetrokken)



class MockRequest:
    def __init__(self, headers=None, cookies=None, query_params=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.url = MagicMock()
        self.url.path = "/test"


def _build_protected_app(mock_db: AsyncMock) -> FastAPI:
    app = FastAPI()

    async def override_db():
        return mock_db

    app.dependency_overrides[get_db] = override_db

    @app.get("/current-user")
    async def current_user_route(current_user: UserResponse = Depends(get_current_user)):
        return {"email": current_user.email}

    @app.get("/current-user-wrapper")
    async def current_user_wrapper_route(
        current_user: UserResponse = Depends(get_current_user_dependency),
    ):
        return {"email": current_user.email}

    return app


@pytest.mark.asyncio
async def test_get_token_from_request_bearer_header():
    # Test 1: Capital Bearer
    request = MockRequest(headers={"authorization": "Bearer token123"})
    token = await get_token_from_request(request, MagicMock(credentials="token123"))
    assert token == "token123"

    # Test 2: Lowercase bearer (Manual extraction check)
    request = MockRequest(headers={"authorization": "bearer token456"})
    # credentials will be None if HTTPBearer fails or auto_error=False
    token = await get_token_from_request(request, None)
    assert token == "token456"


@pytest.mark.asyncio
async def test_get_token_from_request_cookie():
    # Test Cookie extraction
    request = MockRequest(cookies={"access_token": "cookie-token"})
    token = await get_token_from_request(request, None)
    assert token == "cookie-token"


@pytest.mark.asyncio
async def test_get_token_from_request_query_param():
    # Normal HTTP requests must not accept query-string tokens.
    request = MockRequest(query_params={"token": "ws-token"})
    with pytest.raises(HTTPException) as exc:
        await get_token_from_request(request, None)

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.value.detail == "Missing authentication credentials"


@pytest.mark.asyncio
async def test_get_token_from_request_missing():
    request = MockRequest()
    with pytest.raises(HTTPException) as exc:
        await get_token_from_request(request, None)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_current_user_db_validation():
    mock_db = AsyncMock()
    mock_payload = {"user_id": 1, "email": "test@example.com", "jti": "test-jti"}
    mock_user_response = UserResponse(id=1, email="test@example.com", tenant_id=1, roles=[])

    with patch("src.core.auth.dependencies.get_token_from_request", return_value="valid-token"):
        with patch(
            "src.core.auth.jwt_handler.jwt_handler.verify_token",
            return_value=mock_payload,
        ):
            with patch("src.core.security.security_manager.get_security_manager") as mock_sm:
                mock_sm.return_value.verify_token.return_value = None
                with patch(
                    "src.core.auth.dependencies.auth_service.get_user_by_email"
                ) as mock_get_user:
                    mock_get_user.return_value = mock_user_response
                    request = MockRequest()
                    result = await get_current_user(request=request, db=mock_db, token=None)

                    assert result == mock_user_response
                    mock_get_user.assert_called_once_with(mock_db, email="test@example.com")


def test_get_current_user_route_rejects_http_query_token():
    mock_db = AsyncMock()
    app = _build_protected_app(mock_db)
    client = TestClient(app)

    with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
        with patch(
            "src.core.auth.dependencies.auth_service.get_user_by_email",
            new=AsyncMock(
                return_value=UserResponse(id=1, email="test@example.com", tenant_id=1, roles=[])
            ),
        ):
            response = client.get("/current-user?token=query-token")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    mock_verify.assert_not_called()


def test_get_current_user_dependency_route_rejects_http_query_token():
    mock_db = AsyncMock()
    app = _build_protected_app(mock_db)
    client = TestClient(app)

    with patch("src.core.auth.dependencies.jwt_handler.verify_token") as mock_verify:
        with patch(
            "src.core.auth.dependencies.auth_service.get_user_by_email",
            new=AsyncMock(
                return_value=UserResponse(id=1, email="test@example.com", tenant_id=1, roles=[])
            ),
        ):
            response = client.get("/current-user-wrapper?token=query-token")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    mock_verify.assert_not_called()
