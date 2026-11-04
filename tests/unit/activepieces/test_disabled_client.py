"""
Unit tests for _DisabledActivePiecesClient stub.

Ensures graceful degradation returns safe defaults when ActivePieces
is not configured.
"""

import pytest

from src.core.activepieces.service import (
    ActivePiecesService,
    _DisabledActivePiecesClient,
)


class TestDisabledActivePiecesClient:
    """Test that all stub methods return safe defaults."""

    @pytest.fixture
    def client(self):
        return _DisabledActivePiecesClient()

    @pytest.mark.asyncio
    async def test_list_pieces_returns_empty_list(self, client):
        result = await client.list_pieces()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_piece_returns_none(self, client):
        result = await client.get_piece("some-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_flows_returns_empty_list(self, client):
        result = await client.list_flows()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.get_flow("some-id")

    @pytest.mark.asyncio
    async def test_create_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.create_flow(name="test")

    @pytest.mark.asyncio
    async def test_update_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.update_flow("some-id", name="test")

    @pytest.mark.asyncio
    async def test_delete_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.delete_flow("some-id")

    @pytest.mark.asyncio
    async def test_toggle_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.toggle_flow("some-id")

    @pytest.mark.asyncio
    async def test_validate_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.validate_flow("some-id")

    @pytest.mark.asyncio
    async def test_execute_flow_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.execute_flow("some-id")

    @pytest.mark.asyncio
    async def test_list_flow_runs_returns_empty_list(self, client):
        result = await client.list_flow_runs()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_flow_run_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.get_flow_run("some-id")

    @pytest.mark.asyncio
    async def test_retry_flow_run_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.retry_flow_run("some-id")

    @pytest.mark.asyncio
    async def test_cancel_flow_run_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.cancel_flow_run("some-id")

    @pytest.mark.asyncio
    async def test_list_connections_returns_empty_list(self, client):
        result = await client.list_connections()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_connection_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.get_connection("some-id")

    @pytest.mark.asyncio
    async def test_create_connection_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.create_connection(name="test")

    @pytest.mark.asyncio
    async def test_update_connection_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.update_connection("some-id", name="test")

    @pytest.mark.asyncio
    async def test_delete_connection_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.delete_connection("some-id")

    @pytest.mark.asyncio
    async def test_test_connection_returns_not_configured(self, client):
        result = await client.test_connection("some-id")
        assert result == {"success": False, "message": "ActivePieces not configured"}

    @pytest.mark.asyncio
    async def test_health_check_returns_unavailable(self, client):
        result = await client.health_check()
        assert result == {"is_available": False, "api_reachable": False}

    @pytest.mark.asyncio
    async def test_is_available_returns_false(self, client):
        assert client.is_available() is False

    @pytest.mark.asyncio
    async def test_list_project_flows_returns_empty_list(self, client):
        result = await client.list_project_flows("project-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_trigger_flow_returns_disabled_placeholder(self, client):
        result = await client.trigger_flow("flow-123", {"key": "value"})
        assert result == {
            "execution_id": "",
            "status": "DISABLED",
            "start_time": "",
            "duration": 0,
            "project_id": "",
            "flow_id": "flow-123",
        }

    @pytest.mark.asyncio
    async def test_get_run_logs_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client.get_run_logs("run-123")

    @pytest.mark.asyncio
    async def test_list_runs_returns_empty_list(self, client):
        result = await client.list_runs("flow-123", limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_make_request_raises_runtime_error(self, client):
        with pytest.raises(RuntimeError, match="ActivePieces client is disabled"):
            await client._make_request(
                "GET", "/flows", "list_flows", json_data={}, params={}
            )


class TestActivePiecesServiceUnconfigured:
    """Test that ActivePiecesService gracefully degrades when unconfigured."""

    @pytest.mark.asyncio
    async def test_service_uses_disabled_client_when_unconfigured(self):
        from unittest.mock import patch

        with patch("src.core.activepieces.service.ActivePiecesClient") as mock_client:
            mock_client.side_effect = ValueError("ActivePieces credentials not configured")
            service = ActivePiecesService()
            assert isinstance(service._client, _DisabledActivePiecesClient)

    @pytest.mark.asyncio
    async def test_list_pieces_returns_empty_when_unconfigured(self):
        from unittest.mock import patch

        with patch("src.core.activepieces.service.ActivePiecesClient") as mock_client:
            mock_client.side_effect = ValueError("ActivePieces credentials not configured")
            service = ActivePiecesService()
            result = await service._client.list_pieces()
            assert result == []

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_unconfigured(self):
        from unittest.mock import patch

        with patch("src.core.activepieces.service.ActivePiecesClient") as mock_client:
            mock_client.side_effect = ValueError("ActivePieces credentials not configured")
            service = ActivePiecesService()
            health = await service.check_health()
            assert health is False
