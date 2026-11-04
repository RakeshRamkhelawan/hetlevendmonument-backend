"""
Tests for ActivePiecesClient with resilience patterns.

Tests cover:
- Authentication with retry logic
- Circuit breaker behavior
- Request handling through _make_request
- Graceful degradation
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest
from fastapi import HTTPException

# Constants for testing
TEST_API_URL = "http://test-activepieces:80/api/v1"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "password123"
TEST_TOKEN = "valid-jwt-token"
TEST_NEW_TOKEN = "new-valid-jwt-token"


@pytest.fixture
def mock_config():
    """Mock the unified config."""
    mock_cfg = MagicMock()
    mock_cfg.activepieces_api_url = TEST_API_URL
    mock_cfg.activepieces_email = TEST_EMAIL
    mock_cfg.activepieces_password = TEST_PASSWORD
    return mock_cfg


@pytest.fixture
def client(mock_config):
    """Create client instance with mocked config."""
    # Reset singleton circuit breaker for test isolation
    with patch("src.core.activepieces.client.ActivePiecesClient._circuit_breakers", {}):
        from src.core.activepieces.client import ActivePiecesClient
        from src.core.activepieces.verbinding import ApVerbinding

        return ActivePiecesClient(
            ApVerbinding(
                tenant_id=1,
                base_url=mock_config.activepieces_api_url,
                email=mock_config.activepieces_email,
                wachtwoord=mock_config.activepieces_password,
                project_id="proj-test",
            )
        )


@pytest.fixture
def mock_circuit_breaker():
    """Create a mock circuit breaker that passes through calls."""
    mock_cb = MagicMock()
    mock_cb.state = MagicMock()
    mock_cb.state.value = "closed"

    # Make call actually execute the function
    async def call_through(func, *args, **kwargs):
        return await func(*args, **kwargs)

    mock_cb.call = call_through
    return mock_cb


# =============================================================================
# Authentication Tests
# =============================================================================


@pytest.mark.asyncio
async def test_authenticate_success(client):
    """Test successful authentication stores token and expiry."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"token": TEST_TOKEN}
    mock_response.raise_for_status = MagicMock()

    with patch("src.core.activepieces.client.async_retry", new_callable=AsyncMock) as mock_retry:
        mock_retry.return_value = {"token": TEST_TOKEN}

        await client._authenticate()

        assert client.token == TEST_TOKEN
        assert client._token_expiry is not None
        assert client._token_expiry > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_authenticate_failure_http_error(client):
    """Test authentication failure on HTTP error raises 503."""
    with patch("src.core.activepieces.client.async_retry", new_callable=AsyncMock) as mock_retry:
        mock_retry.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)
        )

        with pytest.raises(HTTPException) as exc_info:
            await client._authenticate()

        assert exc_info.value.status_code == 503
        assert "authenticate" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_failure_connection_error(client):
    """Test authentication failure on connection error raises 503."""
    with patch("src.core.activepieces.client.async_retry", new_callable=AsyncMock) as mock_retry:
        mock_retry.side_effect = httpx.RequestError("Connection refused")

        with pytest.raises(HTTPException) as exc_info:
            await client._authenticate()

        assert exc_info.value.status_code == 503
        assert "unreachable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_token_caches_valid_token(client):
    """Test _get_token returns cached token if still valid."""
    client.token = TEST_TOKEN
    client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch.object(client, "_authenticate", new_callable=AsyncMock) as mock_auth:
        token = await client._get_token()

        assert token == TEST_TOKEN
        mock_auth.assert_not_called()


@pytest.mark.asyncio
async def test_get_token_refreshes_expired_token(client):
    """Test _get_token refreshes when token expired."""
    client.token = "old-token"
    client._token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)  # Expired

    with patch.object(client, "_authenticate", new_callable=AsyncMock) as mock_auth:

        async def set_new_token():
            client.token = TEST_NEW_TOKEN
            client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=23)

        mock_auth.side_effect = set_new_token

        token = await client._get_token()

        mock_auth.assert_called_once()
        assert token == TEST_NEW_TOKEN


# =============================================================================
# Circuit Breaker Tests
# =============================================================================


@pytest.mark.asyncio
async def test_is_available_returns_true_when_closed(client, mock_circuit_breaker):
    """Test is_available returns True when circuit is closed."""
    from src.core.tool_broker.resilience import CircuitBreakerState

    mock_circuit_breaker.state = CircuitBreakerState.CLOSED

    with patch.object(type(client), "circuit_breaker", new_callable=PropertyMock) as mock_cb_prop:
        mock_cb_prop.return_value = mock_circuit_breaker
        assert client.is_available() is True


@pytest.mark.asyncio
async def test_is_available_returns_false_when_open(client, mock_circuit_breaker):
    """Test is_available returns False when circuit is open."""
    from src.core.tool_broker.resilience import CircuitBreakerState

    mock_circuit_breaker.state = CircuitBreakerState.OPEN

    with patch.object(type(client), "circuit_breaker", new_callable=PropertyMock) as mock_cb_prop:
        mock_cb_prop.return_value = mock_circuit_breaker
        assert client.is_available() is False


@pytest.mark.asyncio
async def test_make_request_rejects_when_circuit_open(client):
    """Test _make_request raises 503 when circuit is open."""
    with patch.object(client, "is_available", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await client._make_request("GET", "/test", "test_op")

        assert exc_info.value.status_code == 503
        assert "circuit open" in exc_info.value.detail.lower()


# =============================================================================
# Request Tests
# =============================================================================


@pytest.mark.asyncio
async def test_make_request_success(client, mock_circuit_breaker):
    """Test successful request through _make_request."""
    client.token = TEST_TOKEN
    client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}
    mock_response.content = b'{"data": "test"}'
    mock_response.raise_for_status = MagicMock()

    with (
        patch.object(client, "is_available", return_value=True),
        patch.object(type(client), "circuit_breaker", new_callable=PropertyMock) as mock_cb_prop,
        patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request,
    ):
        mock_cb_prop.return_value = mock_circuit_breaker
        mock_request.return_value = mock_response

        result = await client._make_request("GET", "/test", "test_operation")

        assert result == {"data": "test"}


@pytest.mark.asyncio
async def test_create_flow_calls_make_request(client):
    """Test create_flow delegates to _make_request correctly."""
    with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make:
        mock_make.return_value = {"id": "flow-123"}

        result = await client.create_flow("proj-test", {"displayName": "Test Flow"})

        assert result["id"] == "flow-123"
        mock_make.assert_called_once_with(
            method="POST",
            endpoint="/flows",
            operation_name="create_flow",
            json_data={"projectId": "proj-test", "displayName": "Test Flow"},
        )


@pytest.mark.asyncio
async def test_update_flow_calls_make_request(client):
    """Test update_flow delegates to _make_request correctly."""
    with (
        patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make,
        patch.object(client, "get_flow", new_callable=AsyncMock),
    ):
        mock_make.return_value = {"id": "flow-123", "version": 2}

        result = await client.update_flow("flow-123", {"displayName": "Updated"})

        assert result["version"] == 2
        mock_make.assert_called_once_with(
            method="POST",
            endpoint="/flows/flow-123",
            operation_name="update_flow",
            json_data={"displayName": "Updated"},
        )


@pytest.mark.asyncio
async def test_delete_flow_returns_true_on_success(client):
    """Test delete_flow returns True on success."""
    with (
        patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make,
        patch.object(client, "get_flow", new_callable=AsyncMock),
    ):
        mock_make.return_value = {}

        result = await client.delete_flow("flow-123")

        assert result is True


@pytest.mark.asyncio
async def test_delete_flow_returns_false_on_error(client):
    """Test delete_flow returns False on error (graceful degradation)."""
    with (
        patch.object(client, "_make_request", new_callable=AsyncMock) as mock_make,
        patch.object(client, "get_flow", new_callable=AsyncMock),
    ):
        mock_make.side_effect = Exception("Delete failed")

        result = await client.delete_flow("flow-123")

        assert result is False


# =============================================================================
# Graceful Degradation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execute_workflow_graceful_when_unavailable(client):
    """Test execute_workflow returns fallback when service unavailable."""
    with patch.object(client, "is_available", return_value=False):
        result = await client.execute_workflow({"nodes": []})

        assert result["success"] is False
        assert result["fallback"] == "pending_sync"
        assert "unavailable" in result["error"].lower()


@pytest.mark.asyncio
async def test_health_check_returns_state(client, mock_circuit_breaker):
    """Test health_check returns circuit breaker state info."""
    from src.core.tool_broker.resilience import CircuitBreakerState

    client.token = TEST_TOKEN
    client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_circuit_breaker.state = CircuitBreakerState.CLOSED

    with patch.object(type(client), "circuit_breaker", new_callable=PropertyMock) as mock_cb_prop:
        mock_cb_prop.return_value = mock_circuit_breaker

        result = await client.health_check()

        assert "circuit_state" in result
        assert "is_available" in result
        assert "token_valid" in result
        assert result["token_valid"] is True
