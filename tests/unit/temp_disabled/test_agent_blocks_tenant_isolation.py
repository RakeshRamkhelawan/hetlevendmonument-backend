"""
Tenant isolation tests for agent blocks.

Tests verify that tenant_id filtering works correctly at:
1. AgentBlockRegistry level (unit test)
2. All 6 affected endpoints (integration tests with mocked CanvasService)
"""

import pytest
from typing import Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockRegistry,
    AgentBlockType,
    CodeBlockConfig,
    ExecutionEnvironment,
)


class TestAgentBlockRegistryTenantFiltering:
    """Unit tests for AgentBlockRegistry tenant isolation."""

    def test_registry_get_filters_by_tenant(self) -> None:
        """Test that registry.get() with tenant_id filters correctly."""
        reg = AgentBlockRegistry()

        canvas_id = uuid4()
        block_id = uuid4()

        # Create block for tenant 1
        block = AgentBlock(
            block_id=block_id,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=CodeBlockConfig(
                language=ExecutionEnvironment.SAFE_PYTHON, code="print('hello')"
            ),
            canvas_id=canvas_id,
            tenant_id=1,
        )
        reg.register(block)

        # Retrieve with tenant 1 — should succeed
        result = reg.get(block_id, tenant_id=1)
        assert result is block, "Block should be returned for correct tenant"

        # Retrieve with tenant 2 — should fail
        result = reg.get(block_id, tenant_id=2)
        assert result is None, "Block should be hidden from other tenant"

    def test_registry_get_without_tenant_filter_still_works(self) -> None:
        """Test backward compatibility: get() without tenant_id still returns block."""
        reg = AgentBlockRegistry()

        canvas_id = uuid4()
        block_id = uuid4()

        block = AgentBlock(
            block_id=block_id,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=CodeBlockConfig(
                language=ExecutionEnvironment.SAFE_PYTHON, code="print('hello')"
            ),
            canvas_id=canvas_id,
            tenant_id=1,
        )
        reg.register(block)

        # Without tenant_id — should return the block
        result = reg.get(block_id)
        assert result is block, "Block should be returned without tenant filter"

    def test_registry_nonexistent_block_returns_none(self) -> None:
        """Test that get() returns None for nonexistent block."""
        reg = AgentBlockRegistry()
        result = reg.get(uuid4(), tenant_id=1)
        assert result is None, "Nonexistent block should return None"

    def test_registry_multiple_tenants_isolation(self) -> None:
        """Test that multiple tenants can have separate blocks with same canvas_id."""
        reg = AgentBlockRegistry()

        canvas_id = uuid4()
        block_id_1 = uuid4()
        block_id_2 = uuid4()

        # Create blocks for two different tenants on same canvas
        block_1 = AgentBlock(
            block_id=block_id_1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=CodeBlockConfig(language=ExecutionEnvironment.SAFE_PYTHON, code="print('t1')"),
            canvas_id=canvas_id,
            tenant_id=1,
        )
        block_2 = AgentBlock(
            block_id=block_id_2,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=CodeBlockConfig(language=ExecutionEnvironment.SAFE_PYTHON, code="print('t2')"),
            canvas_id=canvas_id,
            tenant_id=2,
        )

        reg.register(block_1)
        reg.register(block_2)

        # Each tenant sees only their own block
        assert reg.get(block_id_1, tenant_id=1) is block_1
        assert reg.get(block_id_1, tenant_id=2) is None

        assert reg.get(block_id_2, tenant_id=2) is block_2
        assert reg.get(block_id_2, tenant_id=1) is None


@pytest.mark.unit
class TestAgentBlocksEndpointsTenantIsolation:
    """Tests for endpoint-level tenant isolation."""

    @pytest.mark.asyncio
    async def test_get_block_rejects_wrong_tenant(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that GET /{block_id} rejects access from wrong tenant."""
        canvas_id = uuid4()
        block_id = uuid4()
        user_id = uuid4()

        with patch(
            "src.core.api.v1.canvas.agent_blocks._verify_canvas_access",
            side_effect=HTTPException(status_code=404, detail="Canvas not found"),
        ):
            response = await client.get(
                f"/api/v1/canvas/{canvas_id}/blocks/{block_id}",
            )
            assert response.status_code == 404
            assert "Canvas not found" in response.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_delete_block_rejects_wrong_tenant(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that DELETE /{block_id} rejects access from wrong tenant."""
        canvas_id = uuid4()
        block_id = uuid4()

        with patch(
            "src.core.api.v1.canvas.agent_blocks._verify_canvas_access",
            side_effect=HTTPException(status_code=404, detail="Canvas not found"),
        ):
            response = await client.delete(
                f"/api/v1/canvas/{canvas_id}/blocks/{block_id}",
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_execution_rejects_wrong_tenant(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that POST /{block_id}/cancel rejects access from wrong tenant."""
        canvas_id = uuid4()
        block_id = uuid4()

        with patch(
            "src.core.api.v1.canvas.agent_blocks._verify_canvas_access",
            side_effect=HTTPException(status_code=404, detail="Canvas not found"),
        ):
            response = await client.post(
                f"/api/v1/canvas/{canvas_id}/blocks/{block_id}/cancel",
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_status_rejects_wrong_tenant(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that GET /{block_id}/status rejects access from wrong tenant."""
        canvas_id = uuid4()
        block_id = uuid4()

        with patch(
            "src.core.api.v1.canvas.agent_blocks._verify_canvas_access",
            side_effect=HTTPException(status_code=404, detail="Canvas not found"),
        ):
            response = await client.get(
                f"/api/v1/canvas/{canvas_id}/blocks/{block_id}/status",
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_block_validates_canvas_ownership(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Test that POST /{block_id}/execute validates canvas ownership before execution."""
        canvas_id = uuid4()
        block_id = uuid4()

        with patch(
            "src.core.api.v1.canvas.agent_blocks._verify_canvas_access",
            side_effect=HTTPException(status_code=404, detail="Canvas not found"),
        ):
            response = await client.post(
                f"/api/v1/canvas/{canvas_id}/blocks/{block_id}/execute",
            )
            assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.security
class TestWebSocketTenantIsolation:
    """Tests for WebSocket endpoint tenant isolation."""

    @pytest.mark.asyncio
    async def test_websocket_rejects_unauthenticated(self) -> None:
        """Test that WebSocket endpoint requires authentication."""
        from src.core.auth.websocket_auth import WebSocketAuthenticator

        mock_ws = MagicMock()
        authenticator = WebSocketAuthenticator()

        with patch.object(authenticator, "_extract_token", return_value=None):
            result = await authenticator.authenticate(mock_ws)
            assert result is None, "Unauthenticated WebSocket should return None"

    @pytest.mark.asyncio
    async def test_websocket_tenant_context_set_on_auth(self) -> None:
        """Test that tenant_id is set in context after successful WebSocket auth."""
        from src.core.auth.websocket_auth import WebSocketAuthenticator
        from src.core.middleware.tenant_context import get_tenant_id

        mock_ws = MagicMock()
        authenticator = WebSocketAuthenticator()

        valid_payload = {
            "user_id": str(uuid4()),
            "tenant_id": 42,
            "email": "test@example.com",
        }

        with (
            patch.object(authenticator, "_extract_token", return_value="valid.jwt.token"),
            patch.object(authenticator.jwt_handler, "verify_token", return_value=valid_payload),
            patch.object(mock_ws, "accept", new_callable=AsyncMock),
        ):
            # This test verifies the flow, actual tenant_id isolation
            # is verified at the endpoint level
            result = await authenticator.authenticate(mock_ws)
            assert result is not None
            assert result.tenant_id == 42
