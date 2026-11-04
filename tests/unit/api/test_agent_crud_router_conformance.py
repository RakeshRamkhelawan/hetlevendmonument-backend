"""
BP-001: agent_crud_router success/data-wrapper conformance tests.
RED voor de fix (geen success-sleutel in response), GREEN na de fix.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.api.v1.agents.agent_crud_router import (
    get_agent_details,
    update_agent_details,
)


def _make_user(tenant_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.tenant_id = tenant_id
    user.id = 100
    return user


def _make_agent(agent_id: str = "agent-001") -> MagicMock:
    agent = MagicMock()
    agent.id = 1
    agent.agent_id = agent_id
    agent.name = "Test Agent"
    agent.description = "A test agent"
    agent.address = "agent://test"
    agent.capabilities = ["cap1"]
    agent.tenant_id = 1
    agent.last_heartbeat = datetime.now(timezone.utc)
    agent.created_at = datetime.now(timezone.utc)
    agent.updated_at = datetime.now(timezone.utc)
    return agent


@pytest.mark.asyncio
async def test_get_agent_details_returns_success_wrapper():
    """get_agent_details() MOET een success-wrapper retourneren -- BP-001."""
    agent = _make_agent()

    repo = MagicMock()
    repo.get_registered_agent_by_agent_id = AsyncMock(return_value=agent)

    result = await get_agent_details(
        agent_id="agent-001",
        current_user=_make_user(),
        _=1,
        repo=repo,
    )

    assert result.get("success") is True, (
        "BP-001: get_agent_details() retourneert geen success=True wrapper. "
        "Fix: voeg 'success': True toe aan de response dict."
    )
    assert "data" in result, (
        "BP-001: get_agent_details() retourneert geen 'data' sleutel. "
        "Fix: nest de agent-velden onder 'data'."
    )


@pytest.mark.asyncio
async def test_update_agent_details_returns_success_key():
    """update_agent_details() MOET success=True retourneren -- gedragstest (conformance via architecture test).

    Noot: de RED-before-fix voor de scanner-violation (return-REGEL) wordt gedekt door
    tests/architecture/test_api_response_format_conformance.py::test_critical_routers_use_success_wrapper.
    """
    from src.core.api.agent_endpoints import AgentUpdateRequest

    agent = _make_agent()

    repo = MagicMock()
    repo.get_registered_agent_by_agent_id = AsyncMock(return_value=agent)
    repo.update_agent = AsyncMock()

    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    request = AgentUpdateRequest(name="Updated Name")

    result = await update_agent_details(
        agent_id="agent-001",
        request=request,
        current_user=_make_user(),
        _=1,
        session=session,
        repo=repo,
    )

    assert isinstance(result, dict), "update_agent_details() retourneert geen dict."
    assert result.get("success") is True, "update_agent_details() retourneert geen success=True."
    assert "data" in result, "update_agent_details() retourneert geen 'data' sleutel."
    assert "agent" in result["data"], "update_agent_details() 'data' bevat geen 'agent' sleutel."


# ============================================================================
# Tenant isolation tests (backend-pattern #11)
# ============================================================================


@pytest.mark.asyncio
async def test_get_agent_details_missing_tenant_raises_401():
    """get_agent_details() MOET 401 geven als current_user geen tenant_id heeft."""
    user = _make_user()
    user.tenant_id = None

    repo = MagicMock()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_agent_details(
            agent_id="agent-001",
            current_user=user,
            _=1,
            repo=repo,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_agent_details_cross_tenant_returns_404():
    """get_agent_details() met verkeerde tenant MOET 404 geven, nooit data lekken."""
    repo = MagicMock()
    repo.get_registered_agent_by_agent_id = AsyncMock(return_value=None)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_agent_details(
            agent_id="agent-other-tenant",
            current_user=_make_user(tenant_id=2),
            _=1,
            repo=repo,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_agent_details_missing_tenant_raises_401():
    """update_agent_details() MOET 401 geven als current_user geen tenant_id heeft."""
    from src.core.api.agent_endpoints import AgentUpdateRequest

    user = _make_user()
    user.tenant_id = None

    repo = MagicMock()
    session = AsyncMock()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await update_agent_details(
            agent_id="agent-001",
            request=AgentUpdateRequest(name="X"),
            current_user=user,
            _=1,
            session=session,
            repo=repo,
        )

    assert exc_info.value.status_code == 401
