"""OWASP A5 regression tests: exception text must not leak to API responses.

These tests are RED before the P2b fix (str(e) in detail/dict) and GREEN after.
Covers:
  - autonomous/agents_router.py:~313  GET  /health         (return dict)
  - routing/router.py:~151            GET  /health         (return dict)

POST /agents/create is uitgeschakeld sinds ADR-036 D12.5 (CRITICAL/P0,
docs/reports/ADR-036-VOLLEDIGE-AUDIT-2026-08-18.md) -- het pad dat hier
oorspronkelijk werd getoetst (de except-tak die str(e) zou kunnen lekken) is
nu structureel onbereikbaar (een onvoorwaardelijke 503 staat voor alle
bedrijfslogica). Zie tests/architecture/test_agent_factory_governance_gate.py
voor de guard die dit bewaakt. De test hieronder is aangepast om het NIEUWE
gedrag te toetsen (altijd 503, nooit interne foutdetails) in plaats van een
onbereikbaar pad te blijven mocken.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SENTINEL = "SENTINEL_EXCEPTION_TEXT_9a7b3c4d_DO_NOT_EXPOSE"


async def test_agents_router_create_is_disabled_and_does_not_leak_str_e() -> None:
    """POST /agents/create moet altijd 503 geven (ADR-036 D12.5), nooit interne details."""
    from fastapi import HTTPException

    from src.core.api.autonomous_endpoints import AgentCreationRequest
    from src.core.api.v1.autonomous.agents_router import create_autonomous_agent
    from src.core.auth.auth_service import UserResponse

    mock_user = UserResponse(id=1, tenant_id=1, email="t@t.com")
    request = AgentCreationRequest(
        archetype="SPECIALIST",
        name="test-agent",
        description="test",
        capabilities=[],
        tools=[],
        parameters={},
    )

    # De mock hieronder bewijst dat de factory NOOIT wordt aangeroepen -- als
    # de 503-guard ooit verwijderd wordt zonder een governance-check erbij,
    # zou dit een RuntimeError met de sentinel veroorzaken, en zou de test
    # onder de oude assertie weer relevant worden.
    with patch("src.core.api.v1.autonomous.agents_router.get_agent_factory") as mock_factory:
        mock_factory.return_value.request_agent_generation = AsyncMock(
            side_effect=RuntimeError(SENTINEL)
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_autonomous_agent(request, mock_user, 1)

    assert exc_info.value.status_code == 503
    mock_factory.assert_not_called()
    detail = exc_info.value.detail
    assert SENTINEL not in str(detail), (
        f"OWASP A5: exception text leaked in POST /agents/create detail: {detail}"
    )


async def test_autonomous_health_check_does_not_leak_str_e() -> None:
    """GET /autonomous/health return dict must not expose exception text (OWASP A5)."""
    from src.core.api.v1.autonomous.agents_router import autonomous_health_check
    from src.core.auth.auth_service import UserResponse

    mock_user = UserResponse(id=1, tenant_id=1, email="t@t.com")

    mock_factory = MagicMock()
    mock_factory.get_system_status = AsyncMock(side_effect=RuntimeError(SENTINEL))

    with (
        patch(
            "src.core.api.v1.autonomous.agents_router.get_agent_factory", return_value=mock_factory
        ),
        patch(
            "src.core.api.v1.autonomous.agents_router.get_self_healing_system",
            return_value=MagicMock(),
        ),
        patch(
            "src.core.api.v1.autonomous.agents_router.get_code_generator", return_value=MagicMock()
        ),
        patch(
            "src.core.api.v1.autonomous.agents_router.get_emergent_intelligence",
            return_value=MagicMock(),
        ),
    ):
        result = await autonomous_health_check(mock_user, 1)

    assert SENTINEL not in str(result), (
        f"OWASP A5: exception text leaked in GET /health response: {result}"
    )


async def test_routing_health_does_not_leak_str_e() -> None:
    """GET /routing/health return dict must not expose exception text (OWASP A5)."""
    from src.core.api.v1.routing.router import routing_health

    mock_guna_router = MagicMock()
    mock_guna_router.rajasic.embedder.health_check = AsyncMock(side_effect=RuntimeError(SENTINEL))
    mock_app = MagicMock()
    mock_app.state.guna_router = mock_guna_router

    mock_main_module = MagicMock()
    mock_main_module.app = mock_app

    mock_embedders_module = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "src.main": mock_main_module,
            "src.core.semantic_router.embedders": mock_embedders_module,
        },
    ):
        result = await routing_health()

    assert SENTINEL not in str(result), (
        f"OWASP A5: exception text leaked in GET /routing/health response: {result}"
    )
