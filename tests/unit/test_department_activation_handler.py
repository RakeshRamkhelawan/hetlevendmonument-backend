"""Tests for department activation handler."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.events.department_activation_handler import DepartmentActivatedEvent, on_department_activated
from src.core.models.agent_config import AgentConfig

@pytest.mark.asyncio
async def test_on_department_activated_creates_config() -> None:
    session = MagicMock()
    with pytest.MonkeyPatch().context() as m:
        repo_mock = MagicMock()
        repo_mock.get_by_agent_id = AsyncMock(return_value=None)
        repo_mock.create = AsyncMock(return_value=AgentConfig(tenant_id=1, agent_type="sales_agent", agent_id="sales-1"))
        m.setattr("src.core.events.department_activation_handler.AgentConfigRepository", lambda db: repo_mock)
        event = DepartmentActivatedEvent(tenant_id=1, department="sales")
        await on_department_activated(event, session)
        repo_mock.create.assert_awaited_once()

@pytest.mark.asyncio
async def test_on_department_activated_reactivates_existing() -> None:
    session = MagicMock()
    with pytest.MonkeyPatch().context() as m:
        existing = AgentConfig(tenant_id=1, agent_type="sales_agent", agent_id="sales-1")
        existing.id = 42
        repo_mock = MagicMock()
        repo_mock.get_by_agent_id = AsyncMock(return_value=existing)
        repo_mock.update = AsyncMock(return_value=existing)
        m.setattr("src.core.events.department_activation_handler.AgentConfigRepository", lambda db: repo_mock)
        event = DepartmentActivatedEvent(tenant_id=1, department="sales")
        await on_department_activated(event, session)
        repo_mock.update.assert_awaited_once()
