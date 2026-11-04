"""Tests for TemplateService agent creation functionality.

These tests verify that agents are properly created for departments
during template instantiation.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.company.models import Department
from src.core.company.template_service import TemplateService


@pytest.fixture
def mock_tenant_context():
    """Create mock tenant context."""
    context = MagicMock()
    context.tenant_id = 1
    return context


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    manager = MagicMock()
    manager.get_session = MagicMock()
    return manager


@pytest.fixture
def template_service(mock_db_manager, mock_tenant_context):
    """Create TemplateService instance with mocked dependencies."""
    return TemplateService(mock_db_manager, mock_tenant_context)


@pytest.mark.asyncio
async def test_user_gets_agents_when_creating_technology_company(template_service):
    """E2E: User creates company -> gets Engineering agents."""
    # Arrange
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "Engineering"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1  # Simulated auto-increment

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    # Act
    agents = await template_service._create_agents_for_department(mock_session, department)

    # Assert: User gets 4 agent types for Engineering
    assert len(agents) == 4
    agent_types = [a.agent_type for a in agents]
    assert "Code Reviewer" in agent_types
    assert "Tech Lead" in agent_types
    assert "DevOps Specialist" in agent_types
    assert "Security Engineer" in agent_types

    # Check all agents have correct foreign keys
    for agent in agents:
        assert agent.tenant_id == 1
        assert agent.department_id == department.id
        assert agent.name == agent.agent_type  # Name matches type


@pytest.mark.asyncio
async def test_user_gets_horeca_agents_for_kitchen_department(template_service):
    """E2E: User creates restaurant -> gets kitchen staff."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "Keuken"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    agent_types = [a.agent_type for a in agents]
    assert "Sous Chef" in agent_types
    assert "Line Cook" in agent_types
    assert "Pastry Chef" in agent_types


@pytest.mark.asyncio
async def test_product_department_gets_product_agents(template_service):
    """Test that Product department gets appropriate agents."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "Product"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    assert len(agents) == 3
    agent_types = [a.agent_type for a in agents]
    assert "Product Manager" in agent_types
    assert "UX Researcher" in agent_types
    assert "Business Analyst" in agent_types


@pytest.mark.asyncio
async def test_unknown_department_gets_generalist(template_service):
    """Test that unknown departments get Generalist fallback."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "UnknownDepartment"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    # Should get at least 1 Generalist agent
    assert len(agents) >= 1
    agent_types = [a.agent_type for a in agents]
    assert "Generalist" in agent_types


@pytest.mark.asyncio
async def test_sales_department_gets_sales_agents(template_service):
    """Test that Sales department gets sales-focused agents."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "Sales"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    assert len(agents) == 3
    agent_types = [a.agent_type for a in agents]
    assert "Sales Development Rep" in agent_types
    assert "Account Executive" in agent_types
    assert "Sales Manager" in agent_types


@pytest.mark.asyncio
async def test_hr_department_gets_hr_agents(template_service):
    """Test that HR department gets HR-focused agents."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "HR"

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    assert len(agents) == 2
    agent_types = [a.agent_type for a in agents]
    assert "Recruiter" in agent_types
    assert "HR Generalist" in agent_types


@pytest.mark.asyncio
async def test_case_insensitive_department_matching(template_service):
    """Test that department matching is case-insensitive."""
    department = MagicMock()
    department.id = uuid.uuid4()
    department.tenant_id = 1
    department.name = "engineering"  # lowercase

    mock_session = AsyncMock()
    created_agents = []

    async def mock_flush():
        for agent in created_agents:
            if not hasattr(agent, "id") or agent.id is None:
                agent.id = 1

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_agents.append(x)

    agents = await template_service._create_agents_for_department(mock_session, department)

    # Should match "Engineering" configuration
    assert len(agents) == 4
    agent_types = [a.agent_type for a in agents]
    assert "Code Reviewer" in agent_types
