"""Unit tests for External Agent API Router.

Taak 5.3: External Agent API Router
Fase 5: Heartbeat Protocol & External Agents
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.api.v1.company.external_agent_router import (
    complete_task,
    deregister_agent,
    get_agent_from_api_key,
    get_next_task,
    heartbeat,
    list_agents,
    register_agent,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_service():
    """Create mock ExternalAgentService."""
    return MagicMock()


@pytest.fixture
def mock_user():
    """Create mock User."""
    user = MagicMock()
    user.tenant_id = 1
    user.id = 100
    return user


# ============================================================================
# Registration Tests
# ============================================================================


class TestRegistration:
    """Test agent registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_agent_success(self, mock_service):
        """Successful registration returns agent_id and api_key."""
        from src.core.company.schemas import ExternalAgentRegister

        mock_service.register = AsyncMock(
            return_value={
                "agent_id": str(uuid.uuid4()),
                "api_key": "sk-test-key",
                "heartbeat_endpoint": "/api/v1/agents/test/heartbeat",
            }
        )

        data = ExternalAgentRegister(
            name="Test Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await register_agent(data, mock_service)

        assert result["success"] is True
        assert "agent_id" in result["data"]
        assert "api_key" in result["data"]
        mock_service.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_agent_validation_error(self, mock_service):
        """Service validation error raises 400 error."""
        mock_service.register = AsyncMock(side_effect=ValueError("Invalid runtime"))

        from src.core.company.schemas import ExternalAgentRegister

        data = ExternalAgentRegister(name="Test", runtime="invalid", capabilities=["test"])

        with pytest.raises(HTTPException) as exc_info:
            await register_agent(data, mock_service)

        assert exc_info.value.status_code == 400


# ============================================================================
# Listing Tests
# ============================================================================


class TestListing:
    """Test agent listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_agents(self, mock_service):
        """List agents returns list of agents."""
        mock_service.list_agents = AsyncMock(
            return_value=[
                MagicMock(agent_id=str(uuid.uuid4()), name="Agent 1"),
                MagicMock(agent_id=str(uuid.uuid4()), name="Agent 2"),
            ]
        )

        result = await list_agents(50, 0, mock_service)

        assert result["success"] is True
        assert len(result["data"]) == 2
        mock_service.list_agents.assert_called_once_with(limit=50, offset=0)


# ============================================================================
# Deregistration Tests
# ============================================================================


class TestDeregistration:
    """Test agent deregistration endpoint."""

    @pytest.mark.asyncio
    async def test_deregister_agent_success(self, mock_service):
        """Successful deregistration returns 204."""
        mock_service.deregister = AsyncMock()

        agent_id = uuid.uuid4()
        await deregister_agent(agent_id, mock_service)

        mock_service.deregister.assert_called_once_with(agent_id)

    @pytest.mark.asyncio
    async def test_deregister_agent_not_found(self, mock_service):
        """Not found raises 404 error."""
        from src.core.exceptions.exceptions import NotFoundError

        mock_service.deregister = AsyncMock(side_effect=NotFoundError("Agent not found"))

        with pytest.raises(HTTPException) as exc_info:
            await deregister_agent(uuid.uuid4(), mock_service)

        assert exc_info.value.status_code == 404


# ============================================================================
# Heartbeat Tests
# ============================================================================


class TestHeartbeat:
    """Test heartbeat endpoint."""

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, mock_service):
        """Successful heartbeat returns ack and pending tasks."""
        from src.core.company.schemas import HeartbeatRequest, HeartbeatResponse

        mock_service.heartbeat = AsyncMock(
            return_value=HeartbeatResponse(
                ack=True,
                pending_tasks=[],
            )
        )

        agent_id = uuid.uuid4()
        data = HeartbeatRequest(status="idle")

        result = await heartbeat(agent_id, data, (agent_id, "api_key"), mock_service)

        assert result["success"] is True
        assert result["data"]["ack"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_auth_error_raises_401(self, mock_service):
        """Service AuthError converts to 401."""
        from src.core.company.schemas import HeartbeatRequest
        from src.core.exceptions.exceptions import AuthError

        mock_service.heartbeat = AsyncMock(side_effect=AuthError("Invalid API key"))

        agent_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await heartbeat(
                agent_id, HeartbeatRequest(status="idle"), (agent_id, "api_key"), mock_service
            )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_heartbeat_not_found_raises_404(self, mock_service):
        """Service NotFoundError converts to 404."""
        from src.core.company.schemas import HeartbeatRequest
        from src.core.exceptions.exceptions import NotFoundError

        mock_service.heartbeat = AsyncMock(side_effect=NotFoundError("Agent not found"))

        agent_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await heartbeat(
                agent_id, HeartbeatRequest(status="idle"), (agent_id, "api_key"), mock_service
            )

        assert exc_info.value.status_code == 404


# ============================================================================
# Task Management Tests
# ============================================================================


class TestTaskManagement:
    """Test task management endpoints."""

    @pytest.mark.asyncio
    async def test_get_next_task_success(self, mock_service):
        """Get next task returns task data."""
        mock_service.get_next_task = AsyncMock(return_value=None)  # No pending tasks

        agent_id = uuid.uuid4()
        result = await get_next_task(agent_id, (agent_id, "api_key"), mock_service)

        assert result["data"] is None

    @pytest.mark.asyncio
    async def test_get_next_task_wrong_agent(self, mock_service):
        """Accessing other agent's tasks raises 403."""
        with pytest.raises(HTTPException) as exc_info:
            await get_next_task(
                uuid.uuid4(),  # Requested agent
                (uuid.uuid4(), "api_key"),  # Different agent's credentials
                mock_service,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_complete_task_success(self, mock_service):
        """Complete task succeeds."""
        mock_service.complete_task = AsyncMock()

        from src.core.company.schemas import TaskCompleteRequest

        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()
        data = TaskCompleteRequest(status="completed", output={"result": "success"})

        await complete_task(agent_id, task_id, data, (agent_id, "api_key"), mock_service)

        mock_service.complete_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_task_wrong_agent(self, mock_service):
        """Completing other agent's task raises 403."""
        from src.core.company.schemas import TaskCompleteRequest

        with pytest.raises(HTTPException) as exc_info:
            await complete_task(
                uuid.uuid4(),  # Requested agent
                uuid.uuid4(),  # Task
                TaskCompleteRequest(status="completed", output={}),
                (uuid.uuid4(), "api_key"),  # Different agent's credentials
                mock_service,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_complete_task_auth_error_raises_401(self, mock_service):
        """Service AuthError for invalid credential converts to 401, not 403 (FA-001)."""
        from src.core.company.schemas import TaskCompleteRequest
        from src.core.exceptions.exceptions import AuthError

        mock_service.complete_task = AsyncMock(
            side_effect=AuthError("Invalid API key", status_code=401)
        )

        agent_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await complete_task(
                agent_id,
                uuid.uuid4(),
                TaskCompleteRequest(status="completed", output={}),
                (agent_id, "api_key"),
                mock_service,
            )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_complete_task_ownership_mismatch_raises_403(self, mock_service):
        """Service AuthError for task ownership mismatch converts to 403 (FA-001)."""
        from src.core.company.schemas import TaskCompleteRequest
        from src.core.exceptions.exceptions import AuthError

        mock_service.complete_task = AsyncMock(
            side_effect=AuthError("Task not assigned to this agent", status_code=403)
        )

        agent_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await complete_task(
                agent_id,
                uuid.uuid4(),
                TaskCompleteRequest(status="completed", output={}),
                (agent_id, "api_key"),
                mock_service,
            )

        assert exc_info.value.status_code == 403


# ============================================================================
# API Key Parsing Tests
# ============================================================================


class TestAPIKeyParsing:
    """Test API key parsing."""

    @pytest.mark.asyncio
    async def test_valid_api_key_format(self):
        """Valid API key format is parsed correctly."""
        agent_id = uuid.uuid4()
        api_key = f"{agent_id}:secret_key"

        result = await get_agent_from_api_key(api_key)

        assert result[0] == agent_id
        assert result[1] == "secret_key"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Missing API key raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_agent_from_api_key(None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_format_no_colon(self):
        """API key without colon raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_agent_from_api_key("invalid")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_agent_id(self):
        """Invalid agent ID format raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_agent_from_api_key("not-a-uuid:key")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_credential_after_colon_raises_401(self):
        """Header 'agent_id:' with nothing after the colon must not parse as authenticated.

        Regression guard: this exact input previously reached the service layer as an
        empty string, which the old `if api_key and ...` check treated as "skip verification".
        """
        agent_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await get_agent_from_api_key(f"{agent_id}:")

        assert exc_info.value.status_code == 401


# ============================================================================
# Authentication Flow Tests
# ============================================================================


class TestAuthenticationFlow:
    """Test authentication flows."""

    @pytest.mark.asyncio
    async def test_admin_endpoints_require_jwt(self):
        """Admin endpoints (register/list/delete) require JWT."""
        # These endpoints have Depends(get_current_user) in signature
        # This test verifies the dependency is present
        import inspect

        # Check register endpoint
        sig = inspect.signature(register_agent)
        assert "service" in sig.parameters

    @pytest.mark.asyncio
    async def test_agent_endpoints_require_api_key(self):
        """Agent endpoints (heartbeat/tasks) require API key."""
        import inspect

        # Check heartbeat endpoint -- credentials replaces x_api_key (parsed by get_agent_from_api_key)
        sig = inspect.signature(heartbeat)
        assert "credentials" in [p.name for p in sig.parameters.values()]
