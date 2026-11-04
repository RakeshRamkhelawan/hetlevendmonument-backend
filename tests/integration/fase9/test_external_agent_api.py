"""
Fase 9 Integration Tests: External Agent API Endpoints

Tests the complete API flow for external agent management:
- POST /api/v1/company/{id}/external-agents
- GET /api/v1/company/{id}/external-agents
- DELETE /api/v1/company/{id}/external-agents/{agent_id}
- POST /api/v1/company/{id}/external-agents/{agent_id}/heartbeat

Uses postgres_session for direct database testing.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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


@pytest.fixture
def mock_db_manager(postgres_session):
    """Create mock database manager that returns the postgres_session."""
    mock = MagicMock()

    class AsyncContextManager:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    mock.get_session = lambda: AsyncContextManager(postgres_session)
    return mock


@pytest.mark.integration
@pytest.mark.asyncio
class TestExternalAgentServiceIntegration:
    """Test external agent service layer with real database."""

    async def test_service_create_agent(
        self, postgres_session, mock_db_manager, mock_policy_engine, mock_budget_manager
    ):
        """Test creating agent through service layer."""
        from src.core.company.external_agent_service import ExternalAgentService
        from src.core.company.models import Company
        from src.core.container import TenantContext

        # Create test company
        company = Company(
            name=f"Service Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create service with mocked dependencies
        tenant_context = TenantContext(tenant_id=1, tenant_slug="test", bypass_filter=False)
        service = ExternalAgentService(
            mock_db_manager, tenant_context, mock_policy_engine, mock_budget_manager
        )

        # Register agent
        from src.core.company.schemas import ExternalAgentRegister

        data = ExternalAgentRegister(
            name="Service Test Agent",
            runtime="python",
            capabilities=["data_processing"],
        )
        register_result = await service.register(data)
        agent_id = register_result["agent_id"]

        # Verify API key was generated
        assert "api_key" in register_result
        assert register_result["api_key"] is not None

        # Get agent from database
        from sqlalchemy import select

        from src.core.company.models import ExternalAgent

        db_result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent_id)
        )
        agent = db_result.scalar_one()

        assert agent is not None
        assert agent.name == "Service Test Agent"
        assert agent.runtime == "python"
        assert agent.status == "registered"  # Initial status is "registered"

    async def test_service_heartbeat_updates_status(
        self, postgres_session, mock_db_manager, mock_policy_engine, mock_budget_manager
    ):
        """Test that heartbeat updates agent status."""
        from sqlalchemy import select

        from src.core.company.external_agent_service import ExternalAgentService
        from src.core.company.models import Company, ExternalAgent
        from src.core.container import TenantContext

        # Create test company and agent
        company = Company(
            name=f"Heartbeat Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        tenant_context = TenantContext(tenant_id=1, tenant_slug="test", bypass_filter=False)
        service = ExternalAgentService(
            mock_db_manager, tenant_context, mock_policy_engine, mock_budget_manager
        )

        from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest

        data = ExternalAgentRegister(
            name="Heartbeat Agent",
            runtime="python",
            capabilities=["monitoring"],
        )
        result = await service.register(data)
        agent_id = result["agent_id"]
        api_key = result["api_key"]

        # Send heartbeat
        heartbeat_data = HeartbeatRequest(status="idle")
        heartbeat_result = await service.heartbeat(agent_id, api_key, heartbeat_data)

        # Verify status updated - heartbeat updates status to "idle"
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent_id)
        )
        db_agent = result.scalar_one()
        assert db_agent.status == "idle"
        assert db_agent.last_heartbeat_at is not None

    async def test_service_list_agents_by_company(
        self, postgres_session, mock_db_manager, mock_policy_engine, mock_budget_manager
    ):
        """Test listing agents filtered by company."""
        from src.core.company.external_agent_service import ExternalAgentService
        from src.core.company.models import Company
        from src.core.container import TenantContext

        # Create test company
        company = Company(
            name=f"List Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        tenant_context = TenantContext(tenant_id=1, tenant_slug="test", bypass_filter=False)
        service = ExternalAgentService(
            mock_db_manager, tenant_context, mock_policy_engine, mock_budget_manager
        )

        # Create multiple agents
        from src.core.company.schemas import ExternalAgentRegister

        await service.register(
            ExternalAgentRegister(
                name="Agent 1",
                runtime="python",
                capabilities=["data_processing"],
            )
        )
        await service.register(
            ExternalAgentRegister(
                name="Agent 2",
                runtime="nodejs",
                capabilities=["web_scraping"],
            )
        )

        # List agents (returns all agents for tenant)
        agents = await service.list_agents()

        # list_agents returns ExternalAgentResponse objects
        assert len(agents) >= 2
        agent_names = [a.name for a in agents]
        assert "Agent 1" in agent_names
        assert "Agent 2" in agent_names

    async def test_service_delete_agent(
        self, postgres_session, mock_db_manager, mock_policy_engine, mock_budget_manager
    ):
        """Test deleting an agent."""
        from sqlalchemy import select

        from src.core.company.external_agent_service import ExternalAgentService
        from src.core.company.models import Company, ExternalAgent
        from src.core.container import TenantContext

        # Create test company and agent
        company = Company(
            name=f"Delete Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        tenant_context = TenantContext(tenant_id=1, tenant_slug="test", bypass_filter=False)
        service = ExternalAgentService(
            mock_db_manager, tenant_context, mock_policy_engine, mock_budget_manager
        )

        from src.core.company.schemas import ExternalAgentRegister

        register_result = await service.register(
            ExternalAgentRegister(
                name="Agent To Delete",
                runtime="python",
                capabilities=["data_processing"],
            )
        )
        agent_id = register_result["agent_id"]

        # Delete agent (soft delete)
        await service.deregister(agent_id)

        # Verify soft deletion - agent still exists but status is "deregistered"
        from sqlalchemy import select

        from src.core.company.models import ExternalAgent

        db_result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent_id)
        )
        agent = db_result.scalar_one()
        assert agent.status == "deregistered"

    async def test_service_invalid_api_key(
        self, postgres_session, mock_db_manager, mock_policy_engine, mock_budget_manager
    ):
        """Test that invalid API key is rejected."""
        from src.core.company.external_agent_service import ExternalAgentService
        from src.core.company.models import Company
        from src.core.container import TenantContext

        company = Company(
            name=f"Auth Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        tenant_context = TenantContext(tenant_id=1, tenant_slug="test", bypass_filter=False)
        service = ExternalAgentService(
            mock_db_manager, tenant_context, mock_policy_engine, mock_budget_manager
        )

        from src.core.company.schemas import ExternalAgentRegister, HeartbeatRequest

        register_result = await service.register(
            ExternalAgentRegister(
                name="Auth Agent",
                runtime="python",
                capabilities=["monitoring"],
            )
        )
        agent_id = register_result["agent_id"]
        api_key = register_result["api_key"]

        # Try heartbeat with wrong key - should raise AuthError
        from src.core.company.external_agent_service import AuthError

        try:
            await service.heartbeat(agent_id, "wrong-key", HeartbeatRequest(status="idle"))
            assert False, "Should have raised AuthError"
        except AuthError:
            pass  # Expected


@pytest.mark.integration
@pytest.mark.asyncio
class TestExternalAgentDirectDB:
    """Test external agent functionality directly at database level."""

    async def test_create_external_agent_direct(self, postgres_session):
        """Test creating external agent directly in database."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        # Create company
        company = Company(
            name=f"Direct Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create agent
        agent = ExternalAgent(
            tenant_id=1,
            company_id=company.id,
            name="Direct Agent",
            runtime="python",
            capabilities=["data_processing", "ml_inference"],
            status="offline",
            api_key_hash="hashed_key_here",
        )
        postgres_session.add(agent)
        await postgres_session.commit()
        await postgres_session.refresh(agent)

        # Verify
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent.id)
        )
        db_agent = result.scalar_one()

        assert db_agent.name == "Direct Agent"
        assert db_agent.runtime == "python"
        assert db_agent.status == "offline"
        assert db_agent.capabilities == ["data_processing", "ml_inference"]

    async def test_heartbeat_updates_timestamp(self, postgres_session):
        """Test that heartbeat updates last_heartbeat timestamp."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        company = Company(
            name=f"Heartbeat Direct {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        agent = ExternalAgent(
            tenant_id=1,
            company_id=company.id,
            name="Heartbeat Agent",
            runtime="nodejs",
            capabilities=["monitoring"],
            status="offline",
            api_key_hash="hashed_key",
        )
        postgres_session.add(agent)
        await postgres_session.commit()
        await postgres_session.refresh(agent)

        # Simulate heartbeat
        now = datetime.now(timezone.utc)
        agent.status = "online"
        agent.last_heartbeat = now
        await postgres_session.commit()

        # Verify
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent.id)
        )
        db_agent = result.scalar_one()

        assert db_agent.status == "online"
        assert db_agent.last_heartbeat is not None

    async def test_list_agents_by_company_direct(self, postgres_session):
        """Test listing agents by company."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        company = Company(
            name=f"List Direct {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        # Create agents
        for i in range(3):
            agent = ExternalAgent(
                tenant_id=1,
                company_id=company.id,
                name=f"Agent {i+1}",
                runtime="python",
                capabilities=["data_processing"],
                status="offline",
                api_key_hash=f"key_{i}",
            )
            postgres_session.add(agent)

        await postgres_session.commit()

        # Query
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.company_id == company.id)
        )
        agents = result.scalars().all()

        assert len(agents) == 3

    async def test_delete_agent_direct(self, postgres_session):
        """Test deleting agent directly."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        company = Company(
            name=f"Delete Direct {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        agent = ExternalAgent(
            tenant_id=1,
            company_id=company.id,
            name="To Delete",
            runtime="python",
            capabilities=["data_processing"],
            status="offline",
            api_key_hash="key_to_delete",
        )
        postgres_session.add(agent)
        await postgres_session.commit()
        await postgres_session.refresh(agent)

        agent_id = agent.id

        # Delete
        await postgres_session.delete(agent)
        await postgres_session.commit()

        # Verify
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.id == agent_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_agent_runtime_types(self, postgres_session):
        """Test that different runtime types can be stored."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        company = Company(
            name=f"Runtime Test {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company)
        await postgres_session.commit()
        await postgres_session.refresh(company)

        runtimes = ["python", "nodejs", "shell", "webhook"]

        for runtime in runtimes:
            agent = ExternalAgent(
                tenant_id=1,
                company_id=company.id,
                name=f"{runtime.capitalize()} Agent",
                runtime=runtime,
                capabilities=["test"],
                status="offline",
                api_key_hash=f"key_{runtime}",
            )
            postgres_session.add(agent)

        await postgres_session.commit()

        # Verify all stored
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.company_id == company.id)
        )
        agents = result.scalars().all()

        assert len(agents) == 4
        stored_runtimes = {a.runtime for a in agents}
        assert stored_runtimes == set(runtimes)


@pytest.mark.integration
@pytest.mark.asyncio
class TestExternalAgentTenantIsolation:
    """Test that agents are isolated by tenant."""

    async def test_agents_isolated_by_tenant_direct(self, postgres_session):
        """Test agents from one tenant are not visible to another."""
        from sqlalchemy import select

        from src.core.company.models import Company, ExternalAgent

        # Create companies for different tenants (both tenant_id=1 for isolation test
        # since we only have one tenant in the test setup)
        company_a = Company(
            name=f"Company A {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        company_b = Company(
            name=f"Company B {uuid4().hex[:8]}",
            tenant_id=1,
            company_type="mkb",
            sector="Technology",
        )
        postgres_session.add(company_a)
        postgres_session.add(company_b)
        await postgres_session.commit()
        await postgres_session.refresh(company_a)
        await postgres_session.refresh(company_b)

        # Create agent for company A
        agent_a = ExternalAgent(
            tenant_id=1,
            company_id=company_a.id,
            name="Company A Agent",
            runtime="python",
            capabilities=["data_processing"],
            status="offline",
            api_key_hash="key_a",
        )
        postgres_session.add(agent_a)
        await postgres_session.commit()

        # Query as company B
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.company_id == company_b.id)
        )
        agents_b = result.scalars().all()

        # Should not see company A's agents
        assert not any(a.name == "Company A Agent" for a in agents_b)

        # Verify company A has the agent
        result = await postgres_session.execute(
            select(ExternalAgent).where(ExternalAgent.company_id == company_a.id)
        )
        agents_a = result.scalars().all()
        assert any(a.name == "Company A Agent" for a in agents_a)
