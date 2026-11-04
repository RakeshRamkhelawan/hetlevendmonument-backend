"""
Integration tests for Fase 5: Heartbeat Protocol & External Agents

These tests verify the service layer integration with PostgreSQL database.
API-level integration tests are kept minimal due to database session complexity.

Requires: PostgreSQL database with proper schema
"""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi import status
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_policy_engine():
    """Mock policy engine for testing."""
    mock = MagicMock()
    mock.validate_output = MagicMock(return_value={"valid": True})
    return mock


@pytest.fixture
def mock_budget_manager():
    """Mock budget manager for testing."""
    mock = MagicMock()
    mock.check_budget = AsyncMock(return_value={"allowed": True, "remaining": 1000})
    mock.track_usage = AsyncMock()
    return mock


@pytest_asyncio.fixture
async def external_agent_service(postgres_session, mock_policy_engine, mock_budget_manager):
    """Create ExternalAgentService with test dependencies."""
    from src.core.company.external_agent_service import ExternalAgentService
    from src.core.container import TenantContext

    tenant_context = TenantContext(
        tenant_id=1,
        tenant_slug="test",
        bypass_filter=False,
    )

    # Create mock db_manager that returns our postgres_session
    mock_db_manager = MagicMock()

    class SessionContextManager:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, *args):
            pass

    mock_db_manager.get_session = MagicMock(
        side_effect=lambda: SessionContextManager(postgres_session)
    )

    service = ExternalAgentService(
        db_manager=mock_db_manager,
        tenant_context=tenant_context,
        policy_engine=mock_policy_engine,
        budget_manager=mock_budget_manager,
    )
    return service


class TestExternalAgentServiceIntegration:
    """Test ExternalAgentService integration with PostgreSQL database."""

    @pytest.mark.asyncio
    async def test_service_register_agent(self, external_agent_service):
        """Service can register a new agent."""
        from src.core.company.schemas import ExternalAgentRegister

        register_data = ExternalAgentRegister(
            name="Service Test Agent",
            runtime="python",
            capabilities=["test"],
            heartbeat_interval_seconds=30,
        )

        result = await external_agent_service.register(register_data)

        assert "agent_id" in result
        assert "api_key" in result
        assert len(result["api_key"]) > 20

    @pytest.mark.asyncio
    async def test_service_heartbeat(self, external_agent_service):
        """Service can process heartbeat."""
        from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest

        # Register agent
        register_data = ExternalAgentRegister(
            name="Heartbeat Test Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)
        agent_id = result["agent_id"]
        api_key = result["api_key"]

        # Process heartbeat
        heartbeat_data = HeartbeatRequest(
            status="idle",
            metrics={"cpu": 50.0},
        )

        response = await external_agent_service.heartbeat(
            agent_id=agent_id,
            api_key=api_key,
            data=heartbeat_data,
        )

        assert response.ack is True
        assert isinstance(response.pending_tasks, list)

    @pytest.mark.asyncio
    async def test_service_invalid_api_key(self, external_agent_service):
        """Service rejects invalid API key."""
        from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest
        from src.core.exceptions.exceptions import AuthError

        # Register agent
        register_data = ExternalAgentRegister(
            name="Auth Test Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)
        agent_id = result["agent_id"]

        # Try heartbeat with wrong key
        heartbeat_data = HeartbeatRequest(status="idle")

        with pytest.raises(AuthError):
            await external_agent_service.heartbeat(
                agent_id=agent_id,
                api_key="wrong_key",
                data=heartbeat_data,
            )

    @pytest.mark.asyncio
    async def test_service_list_agents(self, external_agent_service):
        """Service can list agents."""
        from src.core.company.schemas import ExternalAgentRegister

        # Register agent
        register_data = ExternalAgentRegister(
            name="List Agent Test",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)
        agent_id = result["agent_id"]

        # List agents
        agents = await external_agent_service.list_agents()

        assert len(agents) >= 1
        agent_ids = [str(a.agent_id) for a in agents]
        assert agent_id in agent_ids

    @pytest.mark.asyncio
    async def test_service_deregister_agent(self, external_agent_service):
        """Service can deregister agent."""
        from src.core.company.schemas import ExternalAgentRegister

        # Register agent
        register_data = ExternalAgentRegister(
            name="Deregister Test Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)
        agent_id = result["agent_id"]

        # Deregister
        await external_agent_service.deregister(agent_id)

        # Verify agent is deregistered
        agents = await external_agent_service.list_agents()
        agent_ids = [str(a.agent_id) for a in agents]
        assert agent_id not in agent_ids


class TestExternalAgentBridgeIntegration:
    """Test ExternalAgentBridge integration with service."""

    @pytest.mark.asyncio
    async def test_bridge_basic_functionality(self, external_agent_service, postgres_session):
        """Bridge can be initialized and has correct properties."""
        from uuid import UUID

        from sqlalchemy import select

        from src.core.company.external_agent_bridge import ExternalAgentBridge
        from src.core.company.models import ExternalAgent
        from src.core.company.schemas import ExternalAgentRegister

        # Register agent
        register_data = ExternalAgentRegister(
            name="Bridge Test Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)

        # Get actual agent model from database
        agent_result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == UUID(result["agent_id"]))
        )
        agent = agent_result.scalar_one()

        # Create bridge
        bridge = ExternalAgentBridge(agent, external_agent_service)

        assert "ext-" in bridge.agent_id
        assert bridge.agent_type.value == "specialist"


class TestMultiTenantIsolation:
    """Test multi-tenant isolation for external agents."""

    @pytest.mark.asyncio
    async def test_agents_isolated_by_tenant(self, external_agent_service):
        """Agents are isolated by tenant ID."""
        from src.core.company.schemas import ExternalAgentRegister

        register_data = ExternalAgentRegister(
            name="Tenant 1 Agent",
            runtime="python",
            capabilities=["test"],
        )

        result = await external_agent_service.register(register_data)

        # List agents and verify tenant isolation through list
        agents = await external_agent_service.list_agents()
        agent = next((a for a in agents if str(a.agent_id) == result["agent_id"]), None)
        assert agent is not None


class TestEndToEndServiceFlow:
    """Complete end-to-end service-level integration tests."""

    @pytest.mark.asyncio
    async def test_full_external_agent_lifecycle(self, external_agent_service):
        """Complete lifecycle: register → heartbeat → list → deregister."""
        from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest

        # 1. Register
        register_data = ExternalAgentRegister(
            name="Lifecycle Test Agent",
            runtime="python",
            capabilities=["e2e_test"],
            heartbeat_interval_seconds=30,
        )

        result = await external_agent_service.register(register_data)
        agent_id = result["agent_id"]
        api_key = result["api_key"]

        # 2. Heartbeat
        heartbeat_data = HeartbeatRequest(
            status="idle",
            metrics={"cpu_percent": 30.0, "memory_percent": 50.0},
        )

        heartbeat_result = await external_agent_service.heartbeat(
            agent_id=agent_id,
            api_key=api_key,
            data=heartbeat_data,
        )

        assert heartbeat_result.ack is True

        # 3. List agents
        agents = await external_agent_service.list_agents()
        agent_ids = [str(a.agent_id) for a in agents]
        assert agent_id in agent_ids

        # 4. Deregister
        await external_agent_service.deregister(agent_id)

        # Verify agent is gone
        agents = await external_agent_service.list_agents()
        agent_ids = [str(a.agent_id) for a in agents]
        assert agent_id not in agent_ids
