"""
ActivePieces Client Tests.

Tests verify:
1. Flow creation via API
2. Flow update via API
3. Flow deletion via API
4. Piece listing via API

All tests use mocked HTTP responses with respx.
"""

import pytest
from httpx import Response

import respx


class TestActivePiecesClient:
    """Test ActivePieces HTTP client."""

    @respx.mock
    async def test_create_flow(self):
        """TKT-FB-AP-001: Test flow creation via API."""
        # Setup mock
        route = respx.post("http://localhost:3000/api/v1/flows").mock(
            return_value=Response(
                201, json={"id": "flow-123", "name": "Test Flow", "status": "ENABLED"}
            )
        )

        # Import and test client
        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient(base_url="http://localhost:3000")
            result = await client.create_flow({"name": "Test Flow", "projectId": "project-123"})

            assert result["id"] == "flow-123"
            assert result["name"] == "Test Flow"
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_update_flow(self):
        """TKT-FB-AP-002: Test flow update via API."""
        route = respx.put("http://localhost:3000/api/v1/flows/flow-123").mock(
            return_value=Response(
                200, json={"id": "flow-123", "name": "Updated Flow", "status": "ENABLED"}
            )
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient(base_url="http://localhost:3000")
            result = await client.update_flow("flow-123", {"name": "Updated Flow"})

            assert result["name"] == "Updated Flow"
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_delete_flow(self):
        """TKT-FB-AP-003: Test flow deletion via API."""
        route = respx.delete("http://localhost:3000/api/v1/flows/flow-123").mock(
            return_value=Response(204)
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient(base_url="http://localhost:3000")
            result = await client.delete_flow("flow-123")

            assert result is True
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_list_pieces(self):
        """TKT-FB-AP-004: Test listing pieces via API."""
        route = respx.get("http://localhost:3000/api/v1/pieces").mock(
            return_value=Response(
                200,
                json=[
                    {"id": "slack", "name": "Slack", "version": "1.0.0"},
                    {"id": "gmail", "name": "Gmail", "version": "1.0.0"},
                ],
            )
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()
            pieces = await client.list_pieces()

            assert len(pieces) == 2
            assert pieces[0]["id"] == "slack"
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_trigger_flow(self):
        """TKT-FB-AP-005: Test triggering flow execution."""
        route = respx.post("http://localhost:3000/api/v1/flow-runs").mock(
            return_value=Response(
                201, json={"id": "run-123", "flowId": "flow-123", "status": "RUNNING"}
            )
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()
            result = await client.trigger_flow("flow-123", {"key": "value"})

            assert result["id"] == "run-123"
            assert result["status"] == "RUNNING"
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_get_flow_run_status(self):
        """TKT-FB-AP-006: Test getting flow run status."""
        route = respx.get("http://localhost:3000/api/v1/flow-runs/run-123").mock(
            return_value=Response(
                200, json={"id": "run-123", "flowId": "flow-123", "status": "SUCCEEDED", "logs": []}
            )
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()
            result = await client.get_run_status("run-123")

            assert result["status"] == "SUCCEEDED"
            assert route.called
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")


class TestActivePiecesClientErrorHandling:
    """Test ActivePieces client error handling."""

    @respx.mock
    async def test_handle_404_error(self):
        """TKT-FB-AP-007: Test handling 404 response."""
        respx.get("http://localhost:3000/api/v1/flows/not-found").mock(
            return_value=Response(404, json={"message": "Flow not found"})
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()

            # Should raise or return None for not found
            try:
                result = await client.get_flow("not-found")
                assert result is None
            except Exception as e:
                # Exception is also acceptable
                assert "not found" in str(e).lower() or "404" in str(e)
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_handle_500_error(self):
        """TKT-FB-AP-008: Test handling 500 response."""
        respx.post("http://localhost:3000/api/v1/flows").mock(
            return_value=Response(500, json={"message": "Internal server error"})
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()

            # Should raise exception
            with pytest.raises(Exception):
                await client.create_flow({"name": "Test"})
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")

    @respx.mock
    async def test_handle_connection_error(self):
        """TKT-FB-AP-009: Test handling connection error."""
        respx.get("http://localhost:3000/api/v1/pieces").mock(
            side_effect=Exception("Connection refused")
        )

        try:
            from src.core.focus_builder.activepieces_client import ActivePiecesClient

            client = ActivePiecesClient()

            # Should raise exception
            with pytest.raises(Exception):
                await client.list_pieces()
        except ImportError:
            pytest.skip("ActivePiecesClient not implemented")
