"""
Tests for Health Endpoints - FASE 6.3
"""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status

from src.core.api.health_endpoints import deep_health_check, health_check, readiness_check


@pytest.fixture
def mock_request():
    """Create a mock request object for rate limiter."""
    request = MagicMock(spec=Request)
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_response():
    """Create a mock response object"""
    from fastapi import Response
    response = MagicMock(spec=Response)
    return response


class TestHealthCheck:
    """Test basic health check"""

    @pytest.mark.asyncio
    @patch("src.core.api.health_endpoints.limiter.enabled", False)
    async def test_health_check_returns_ok(self):
        """Test basic health check returns status ok"""
        result = await health_check()
        # Handle both dict and JSONResponse types
        if hasattr(result, 'body'):
            import json
            result_data = json.loads(result.body)
        else:
            result_data = result
        assert result_data["status"] == "ok"


class TestReadinessCheck:
    """Test readiness probe"""

    @pytest.mark.asyncio
    @patch("src.core.api.health_endpoints.limiter.enabled", False)
    @patch("src.core.api.health_endpoints.db_manager")
    @patch("src.core.api.health_endpoints.get_cache")
    async def test_readiness_healthy(self, mock_get_cache, mock_db_manager, mock_request, mock_response):
        """Test readiness check when all dependencies healthy"""
        # Setup mocks
        mock_db_manager.is_initialized.return_value = True
        mock_db_manager.health_check = AsyncMock(return_value=True)

        mock_cache = AsyncMock()
        mock_cache.connected = True
        mock_cache.redis_client.ping = AsyncMock()
        mock_get_cache.return_value = mock_cache

        result = await readiness_check(mock_request, mock_response)

        assert result["status"] == "ready"
        assert "database" in result["dependencies"]
        assert "redis" in result["dependencies"]

    @pytest.mark.asyncio
    @patch("src.core.api.health_endpoints.limiter.enabled", False)
    @patch("src.core.api.health_endpoints.db_manager")
    async def test_readiness_db_not_initialized(self, mock_db_manager, mock_request, mock_response):
        """Test readiness check fails when database not initialized"""
        mock_db_manager.is_initialized.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await readiness_check(mock_request, mock_response)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = cast(dict, exc_info.value.detail)
        assert "not initialized" in detail.get("reason", "")


class TestDeepHealthCheck:
    """Test deep health check - FASE 6.3"""

    @pytest.mark.asyncio
    @patch("src.core.api.health_endpoints.limiter.enabled", False)
    @patch("src.core.api.health_endpoints.db_manager")
    @patch("src.core.api.health_endpoints.get_cache")
    @patch("src.core.api.health_endpoints.get_event_consumer")
    @patch("src.core.api.health_endpoints.get_pubsub_manager")
    @patch("aiohttp.ClientSession")
    async def test_deep_health_all_healthy(
        self,
        mock_session_class,
        mock_get_pubsub,
        mock_get_consumer,
        mock_get_cache,
        mock_db_manager,
        mock_request,
        mock_response,
    ):
        """Test deep health when all services healthy"""
        # Setup database mock
        mock_db_manager.is_initialized.return_value = True
        mock_db_manager.health_check = AsyncMock(return_value=True)

        # Setup cache mock
        mock_cache = AsyncMock()
        mock_cache.connected = True
        mock_cache.redis_client.ping = AsyncMock()
        mock_get_cache.return_value = mock_cache

        # Setup event consumer mock
        mock_consumer = AsyncMock()
        mock_consumer._connected = True
        mock_consumer.get_stats = AsyncMock(return_value={"connected": True, "total_handlers": 5})
        mock_get_consumer.return_value = mock_consumer

        # Setup pubsub mock
        mock_pubsub = AsyncMock()
        mock_pubsub.connected = True
        mock_pubsub.get_stats = AsyncMock(
            return_value={"subscribed_channels": 3, "total_handlers": 8}
        )
        mock_get_pubsub.return_value = mock_pubsub

        # Setup aiohttp mock
        mock_aio_response = AsyncMock()
        mock_aio_response.status = 200
        mock_aio_response.json = AsyncMock(return_value={"status": "ok"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_aio_response)
        mock_session_class.return_value = mock_session

        # Mock the authenticated user dependency
        with patch("src.core.api.health_endpoints.verify_token") as mock_auth:
            mock_auth.return_value = {"id": 1, "tenant_id": 1}
            result = await deep_health_check(mock_request, mock_response)

        assert result["status"] == "healthy"
        assert "checks" in result
        assert result["checks"]["database"]["status"] == "healthy"
        assert result["checks"]["redis"]["status"] == "healthy"
        assert result["checks"]["event_consumer"]["status"] == "healthy"
        assert result["checks"]["sync_server"]["status"] == "healthy"
        assert "timestamp" in result

    @pytest.mark.asyncio
    @patch("src.core.api.health_endpoints.limiter.enabled", False)
    @patch("src.core.api.health_endpoints.db_manager")
    async def test_deep_health_db_fails(self, mock_db_manager, mock_request, mock_response):
        """Test deep health fails when database is down"""
        mock_db_manager.is_initialized.return_value = False

        # Mock the authenticated user dependency
        with patch("src.core.api.health_endpoints.verify_token") as mock_auth:
            mock_auth.return_value = {"id": 1, "tenant_id": 1}
            with pytest.raises(HTTPException) as exc_info:
                await deep_health_check(mock_request, mock_response)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = cast(dict, exc_info.value.detail)
        assert "database" in detail["message"]
        assert detail["status"] == "unhealthy"


class TestSyncHealthEndpoints:
    """Test sync-server health endpoints"""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_sync_health_healthy(self, mock_session_class):
        """Test sync health when sync-server is healthy"""
        from src.core.api.v1.sync.health import sync_health_check

        # Setup mock
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session_class.return_value = mock_session

        result = await sync_health_check()

        assert result["status"] == "healthy"
        assert result["service"] == "sync-server-proxy"
        assert "checks" in result

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_sync_health_unavailable(self, mock_session_class):
        """Test sync health when sync-server is unreachable"""
        from aiohttp import ClientConnectorError

        from src.core.api.v1.sync.health import sync_health_check

        # Setup mock to raise connection error
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock(
            side_effect=ClientConnectorError(MagicMock(), OSError("Connection refused"))
        )
        mock_session_class.return_value = mock_session

        with pytest.raises(HTTPException) as exc_info:
            await sync_health_check()

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        detail = cast(dict, exc_info.value.detail)
        assert detail["status"] == "unavailable"
        assert "sync_server" in str(detail)

    @pytest.mark.asyncio
    async def test_sync_status(self):
        """Test sync status endpoint"""
        from src.core.api.v1.sync.health import sync_status

        result = await sync_status()

        assert "status" in result
        assert "timestamp" in result
        assert result["sync_server"] is not None

    @pytest.mark.asyncio
    @patch("src.core.api.v1.sync.health.db_manager")
    async def test_webhook_test(self, mock_db_manager):
        """Test webhook test endpoint"""
        from src.core.api.v1.sync.health import test_sync_webhook

        mock_db_manager.is_initialized.return_value = True

        result = await test_sync_webhook()

        assert result["webhook_test"] == "completed"
        assert "tests" in result
        assert "summary" in result
        assert result["summary"]["total"] > 0
