"""
RC-001: Agent execute en collaborate routes MOETEN de council gate doorlopen.

Tests zijn ROOD totdat RC-001 fix is geimplementeerd (SP-GOV-002 dag 1).
Na de fix: council gate via Depends(get_council_dependency) + require_council_approval
in handler body van execute_agent_primary, execute_agent_dispatcher,
execute_agent_legacy en collaborate_agents_route.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# parents[5] van tests/unit/api/v1/agents/this_file.py = repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]


# ---------------------------------------------------------------------------
# Laag A -- architectuur/bron bewijzen (geen runtimekoppelingen)
# ---------------------------------------------------------------------------


def test_execute_router_calls_require_council_approval() -> None:
    """RC-001: agent_execution_router.py MOET council gate via ADR-033 facade aanroepen."""
    src = (_REPO_ROOT / "src/core/api/v1/agents/agent_execution_router.py").read_text(
        encoding="utf-8"
    )
    assert "require_agent_council_approval" in src, (
        "RC-001 ONTBREEKT: agent_execution_router.py roept require_agent_council_approval "
        "niet aan -- council gate mist op execute-endpoints (SP-GOV-002)"
    )


def test_management_router_calls_require_council_approval() -> None:
    """RC-001: agent_management_router.py MOET council gate via ADR-033 facade aanroepen."""
    src = (_REPO_ROOT / "src/core/api/v1/agents/agent_management_router.py").read_text(
        encoding="utf-8"
    )
    assert "require_agent_council_approval" in src, (
        "RC-001 ONTBREEKT: agent_management_router.py roept require_agent_council_approval "
        "niet aan -- council gate mist op collaborate-endpoint (SP-GOV-002)"
    )


# ---------------------------------------------------------------------------
# Laag B -- gedrag: council-blokkade leidt tot 403
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    from src.core.auth import UserResponse

    user = MagicMock(spec=UserResponse)
    user.id = 1
    user.tenant_id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock()
    registry.distribute_task = AsyncMock(return_value={"result": "ok"})
    return registry


@pytest.mark.asyncio
async def test_execute_primary_council_block_returns_403(
    mock_user: MagicMock,
    mock_registry: MagicMock,
) -> None:
    """RC-001: execute_agent_primary geeft 403 terug als council blokkeert."""
    from src.core.api.agent_endpoints import AgentExecutionRequest
    from src.core.api.v1.agents.agent_execution_router import execute_agent_primary

    mock_council = MagicMock()
    blocked = HTTPException(
        status_code=403,
        detail={"code": "GOVERNANCE_BLOCKED", "message": "Council blocked execution"},
    )

    with (
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(side_effect=blocked),
        ),
        patch(
            "src.core.api.v1.agents.agent_execution_router.execute_agent",
            new=AsyncMock(return_value={"success": True}),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await execute_agent_primary(
                agent_id="agent-1",
                request=AgentExecutionRequest(input="test input"),
                current_user=mock_user,
                _=1,
                registry=mock_registry,
                council=mock_council,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_collaborate_council_block_returns_403(
    mock_user: MagicMock,
    mock_registry: MagicMock,
) -> None:
    """RC-001: collaborate_agents_route geeft 403 terug als council blokkeert."""
    from src.core.api.agent_endpoints import AgentCollaborationRequest
    from src.core.api.v1.agents.agent_management_router import collaborate_agents_route

    mock_council = MagicMock()
    blocked = HTTPException(
        status_code=403,
        detail={"code": "GOVERNANCE_BLOCKED", "message": "Council blocked collaboration"},
    )

    with (
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(side_effect=blocked),
        ),
        patch(
            "src.core.api.v1.agents.agent_management_router.collaborate_agents",
            new=AsyncMock(return_value={"success": True}),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await collaborate_agents_route(
                request=AgentCollaborationRequest(query="test task"),
                current_user=mock_user,
                _=1,
                registry=mock_registry,
                council=mock_council,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_dispatcher_council_block_returns_403(
    mock_user: MagicMock,
    mock_registry: MagicMock,
) -> None:
    """RC-001: execute_agent_dispatcher geeft 403 terug als council blokkeert."""
    from src.core.api.agent_endpoints import AgentQueryRequest
    from src.core.api.v1.agents.agent_execution_router import execute_agent_dispatcher

    mock_council = MagicMock()
    blocked = HTTPException(
        status_code=403,
        detail={"code": "GOVERNANCE_BLOCKED", "message": "Council blocked execution"},
    )

    with (
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(side_effect=blocked),
        ),
        patch(
            "src.core.api.v1.agents.agent_execution_router.execute_agent",
            new=AsyncMock(return_value={"success": True}),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await execute_agent_dispatcher(
                request=AgentQueryRequest(agent_id="agent-1", query="test input"),
                current_user=mock_user,
                _=1,
                registry=mock_registry,
                council=mock_council,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_council_block_returns_403(
    mock_user: MagicMock,
    mock_registry: MagicMock,
) -> None:
    """RC-001: execute_agent_legacy geeft 403 terug als council blokkeert."""
    from src.core.api.agent_endpoints import AgentExecutionRequest
    from src.core.api.v1.agents.agent_execution_router import execute_agent_legacy

    mock_council = MagicMock()
    blocked = HTTPException(
        status_code=403,
        detail={"code": "GOVERNANCE_BLOCKED", "message": "Council blocked execution"},
    )

    with (
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(side_effect=blocked),
        ),
        patch(
            "src.core.api.v1.agents.agent_execution_router.execute_agent",
            new=AsyncMock(return_value={"success": True}),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await execute_agent_legacy(
                agent_id="agent-1",
                request=AgentExecutionRequest(input="test input"),
                current_user=mock_user,
                _=1,
                registry=mock_registry,
                council=mock_council,
            )

    assert exc_info.value.status_code == 403
