"""Unit tests for AgentDiscoveryService.find_agents_by_functions()."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_discovery import AgentDiscoveryService


def _make_service() -> AgentDiscoveryService:
    svc = AgentDiscoveryService.__new__(AgentDiscoveryService)
    svc._tenant_id = 1
    svc._cache = {}
    svc._ttl = 300
    svc._db_session = None
    svc._async_session_factory = None
    return svc


def _make_service_with_ctx(session_ctx: MagicMock) -> AgentDiscoveryService:
    """Build a service whose _session_scope delegates to session_ctx."""
    svc = _make_service()

    @asynccontextmanager
    async def _factory():
        async with session_ctx as s:
            yield s

    svc._async_session_factory = _factory
    return svc


def _make_session_ctx(agents: list) -> MagicMock:
    """Build a mock async-session context manager that returns *agents* from scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = agents

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_testing_path_uses_python_filtering():
    """TESTING=1 path: full table scan then Python-side filter on ORM objects."""
    agent_a = MagicMock()
    agent_a.capabilities = ["contracts", "legal"]
    agent_a.agent_id = "legal_agent_001"

    agent_b = MagicMock()
    agent_b.capabilities = ["analytics"]
    agent_b.agent_id = "data_agent_001"

    svc = _make_service_with_ctx(_make_session_ctx([agent_a, agent_b]))

    with patch.dict("os.environ", {"TESTING": "1"}):
        result = await svc.find_agents_by_functions(["contracts"])

    assert len(result) == 1
    assert result[0].agent_id == "legal_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_empty_caps_returns_empty():
    svc = _make_service()
    result = await svc.find_agents_by_functions([])
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_respects_limit():
    """TESTING path: never returns more than limit agents."""
    agents = [MagicMock(capabilities=["contracts"], agent_id=f"agent_{i:03d}") for i in range(5)]
    svc = _make_service_with_ctx(_make_session_ctx(agents))

    with patch.dict("os.environ", {"TESTING": "1"}):
        result = await svc.find_agents_by_functions(["contracts"], limit=3)

    assert len(result) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_returns_empty_on_exception():
    failing_ctx = MagicMock()
    failing_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
    failing_ctx.__aexit__ = AsyncMock(return_value=False)
    svc = _make_service_with_ctx(failing_ctx)

    with patch.dict("os.environ", {"TESTING": "1"}):
        result = await svc.find_agents_by_functions(["contracts"])
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_no_match_returns_empty():
    """No agent has the requested capability."""
    agent = MagicMock()
    agent.capabilities = ["analytics"]
    agent.agent_id = "data_agent_001"
    svc = _make_service_with_ctx(_make_session_ctx([agent]))

    with patch.dict("os.environ", {"TESTING": "1"}):
        result = await svc.find_agents_by_functions(["contracts"])

    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_by_functions_postgresql_path_returns_list():
    """PostgreSQL path: calls DB with JSONB @> containment query (GIN index path)."""
    mock_agent = MagicMock()
    mock_agent.agent_id = "legal_agent_001"
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_agent]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    svc = _make_service_with_ctx(mock_ctx)
    env_without_testing = {k: v for k, v in os.environ.items() if k != "TESTING"}

    with patch.dict("os.environ", env_without_testing, clear=True):
        result = await svc.find_agents_by_functions(["contracts"])

    assert result == [mock_agent]
    mock_session.execute.assert_awaited_once()
