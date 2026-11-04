"""Tests for AgentConfigRepository."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models.agent_config import AgentConfig
from src.core.repositories.agent_config_repository import AgentConfigRepository

@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def repo(mock_session: AsyncMock) -> AgentConfigRepository:
    return AgentConfigRepository(mock_session)

@pytest.mark.asyncio
async def test_create(repo: AgentConfigRepository, mock_session: AsyncMock) -> None:
    cfg = await repo.create(tenant_id=1, agent_type="t", agent_id="a1")
    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()
    mock_session.refresh.assert_awaited_once()
    assert cfg.tenant_id == 1

@pytest.mark.asyncio
async def test_get_active_configs_all(repo: AgentConfigRepository, mock_session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    result = await repo.get_active_configs()
    assert result == []

@pytest.mark.asyncio
async def test_get_active_configs_by_tenant(repo: AgentConfigRepository, mock_session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    result = await repo.get_active_configs(tenant_id=42)
    assert result == []
