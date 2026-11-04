"""
Unit tests: GET /agents/ paginering -- BP-002 (SP-SEC-002)
RED voor de fix (limit/offset ontbreekt), GREEN na de fix.
"""

import inspect

import pytest


def test_list_agents_has_limit_parameter():
    """list_agents() in agent_endpoints.py MOET een limit parameter hebben -- BP-002."""
    from src.core.api.agent_endpoints import list_agents

    sig = inspect.signature(list_agents)
    assert "limit" in sig.parameters, (
        "BP-002: list_agents() heeft geen 'limit' parameter. "
        "Fix: voeg `limit: int = Query(default=50, le=1000)` toe (backend-patterns pattern 5)."
    )


def test_list_agents_has_offset_parameter():
    """list_agents() in agent_endpoints.py MOET een offset parameter hebben -- BP-002."""
    from src.core.api.agent_endpoints import list_agents

    sig = inspect.signature(list_agents)
    assert "offset" in sig.parameters, (
        "BP-002: list_agents() heeft geen 'offset' parameter. "
        "Fix: voeg `offset: int = Query(default=0, ge=0)` toe (backend-patterns pattern 5)."
    )


def test_crud_router_list_agents_has_limit_parameter():
    """list_agents() in agent_crud_router.py MOET een limit parameter hebben -- BP-002."""
    from src.core.api.v1.agents.agent_crud_router import list_agents

    sig = inspect.signature(list_agents)
    assert "limit" in sig.parameters, (
        "BP-002: agent_crud_router.list_agents() heeft geen 'limit' parameter. "
        "Fix: voeg `limit: int = Query(default=50, le=1000)` toe."
    )


@pytest.mark.asyncio
async def test_list_agents_respects_limit():
    """list_agents() MOET het limit-argument toepassen op de agents lijst -- BP-002."""
    from unittest.mock import AsyncMock, Mock, patch

    from src.core.api.agent_endpoints import list_agents

    sig = inspect.signature(list_agents)
    if "limit" not in sig.parameters:
        pytest.skip("limit parameter nog niet aanwezig -- test wordt groen na fix")

    mock_registry = AsyncMock()
    mock_user = Mock()
    mock_user.id = "user1"

    # Build 5 fake catalog agent configs for limit=2 testing
    def _fake_cfg(i: int) -> Mock:
        m = Mock()
        m.department = "it_security"
        m.is_active = True
        m.class_name = f"TestAgent{i}"
        m.ooda_profile = None
        m.allowed_tools = []
        m.description = f"Agent {i}"
        return m

    mock_loader = Mock()
    mock_loader.agents = {f"agent{i}": _fake_cfg(i) for i in range(5)}

    with (
        patch("src.core.als.agents.loader.EnterpriseCatalogLoader") as mock_loader_cls,
        patch(
            "src.core.activepieces.service.get_activepieces_service",
            side_effect=Exception("mocked -- vermijd netwerkaanroep"),
        ),
    ):
        mock_loader_cls.return_value = mock_loader
        result = await list_agents(
            category=None,
            capability=None,
            source=None,
            limit=2,
            offset=0,
            current_user=mock_user,
            _=1,
            registry=mock_registry,
        )

    assert len(result.agents) == 2, (
        f"BP-002: limit=2 maar {len(result.agents)} agents teruggegeven. "
        "Fix: pas limit-slicing toe in list_agents()."
    )
    assert result.total_count == 5, (
        f"BP-002: total_count moet de pre-slice telling zijn (5), niet de gepagineerde. "
        f"Gekregen: {result.total_count}."
    )
