import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.core.middleware.tenant_middleware import TenantMiddleware

@pytest.fixture
def mock_app():
    async def app(scope, receive, send):
        # Stuur een 200 OK terug
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    return app

@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "single_tenant")
async def test_tenant_middleware_fallback_single_tenant_no_jwt(mock_app):
    """Test 1.1 (ADR-036 OP-62, 2026-08-26, Rakesh GO): een verzoek zonder token krijgt in
    single_tenant mode 401, precies als in elke andere mode. Tot deze fix gaf de middleware
    hier `roles: ["admin"]` en `tenant_id=1` zonder enige verificatie -- volledige adminrechten
    voor elk onbeauthenticeerd verzoek. single_tenant mag de TENANT-resolutie vereenvoudigen
    (een GEVERIFIEERD token zonder `tenant_id`-claim valt elders in deze module terug op
    tenant_id=1, zie de code rond `if tenant_id is None`), maar nooit de AUTHENTICATIE zelf
    overslaan.
    """
    middleware = TenantMiddleware(mock_app)

    scope = {
        "type": "http",
        "path": "/api/v1/protected",
        "method": "GET",
        "headers": [],
        "client": ("127.0.0.1", 8000),
    }

    receive = AsyncMock()

    responses = []
    async def send(message):
        responses.append(message)

    await middleware(scope, receive, send)

    status = responses[0]["status"]
    assert status == 401, (
        f"Verwachtte 401 (geen token, ook in single_tenant mode) maar kreeg {status} -- "
        "de admin-zonder-token-omzeiling is terug."
    )
    assert scope["state"].get("roles") != ["admin"], (
        "Een onbeauthenticeerd verzoek kreeg adminrechten toegekend."
    )

@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "single_tenant")
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_tenant_middleware_fallback_single_tenant_with_jwt(mock_jwt, mock_app):
    """Test 1.2: Override path: DEPLOYMENT_MODE=single_tenant env var ingesteld, WEL JWT header -> request krijgt de tenant_id uit JWT."""
    # Mock een geldige JWT met tenant_id=99
    mock_jwt.verify_token.return_value = {"tenant_id": 99, "sub": "user123"}
    
    middleware = TenantMiddleware(mock_app)
    
    scope = {
        "type": "http",
        "path": "/api/v1/protected",
        "method": "GET",
        "headers": [(b"authorization", b"Bearer valid_token")],
        "client": ("127.0.0.1", 8000),
    }
    
    receive = AsyncMock()
    
    responses = []
    async def send(message):
        responses.append(message)
    
    await middleware(scope, receive, send)

    assert responses[0]["status"] == 200
    assert scope["state"].get("tenant_id") == 99


@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "single_tenant")
@patch("src.core.auth.jwt_handler.jwt_handler")
async def test_tenant_middleware_single_tenant_defaults_tenant_id_for_a_verified_token(
    mock_jwt, mock_app
):
    """single_tenant's legitieme vereenvoudiging overleeft OP-62's fix: een GEVERIFIEERD token
    zonder `tenant_id`-claim valt terug op tenant_id=1. Alleen het ONTBREKEN van elk token is
    nu een 401 (test 1.1) -- niet het ontbreken van de claim in een wel-geldig token.
    """
    mock_jwt.verify_token.return_value = {"sub": "user123", "roles": ["editor"]}

    middleware = TenantMiddleware(mock_app)

    scope = {
        "type": "http",
        "path": "/api/v1/protected",
        "method": "GET",
        "headers": [(b"authorization", b"Bearer valid_token")],
        "client": ("127.0.0.1", 8000),
    }

    receive = AsyncMock()

    responses = []
    async def send(message):
        responses.append(message)

    await middleware(scope, receive, send)

    assert responses[0]["status"] == 200
    assert scope["state"].get("tenant_id") == 1
    # De rollen komen uit het GEVERIFIEERDE token, niet uit een hardgecodeerde admin-default.
    assert scope["state"].get("roles") == ["editor"]

@pytest.mark.asyncio
@patch("src.core.middleware.tenant_middleware.DEPLOYMENT_MODE", "saas")
async def test_tenant_middleware_saas_default_no_jwt(mock_app):
    """Test 1.3: SaaS path: DEPLOYMENT_MODE=saas (default), geen JWT header -> request krijgt 401 Unauthorized."""
    middleware = TenantMiddleware(mock_app)
    
    scope = {
        "type": "http",
        "path": "/api/v1/protected",
        "method": "GET",
        "headers": [],
        "client": ("127.0.0.1", 8000),
    }
    
    receive = AsyncMock()
    
    responses = []
    async def send(message):
        responses.append(message)
    
    await middleware(scope, receive, send)
    
    # Zonder JWT in SaaS mode -> 401
    assert responses[0]["status"] == 401


@pytest.fixture(autouse=True)
def _account_is_actief_buiten_deze_test():
    """Deze tests gaan over tenantcontext en tokens, niet over de accountstatus, en hebben geen database.

    De controle zelf (uitgezet = 401 ACCOUNT_DISABLED, database weg = 503) wordt gemeten in
    `tests/integration/test_uitgeschakeld_is_uitgeschakeld.py`, tegen een echte database.
    """
    from unittest.mock import AsyncMock, patch

    from src.core.auth import account_status

    with patch.object(
        account_status,
        "haal_account_status",
        AsyncMock(return_value=account_status.AccountStatus.ACTIEF),
    ):
        yield
