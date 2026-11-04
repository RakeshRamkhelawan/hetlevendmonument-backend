"""
RC-002: Legacy CVA endpoint /chat/legacy MOET de Agent Council doorlopen.

Tests zijn ROOD totdat RC-002 fix is geimplementeerd (SP-GOV-002 dag 2).
Na de fix:
  - legacy_router.py roept require_council_approval aan (via function-body lazy import)
  - CVAChatResponse bevat decision_id veld
  - Council-blokkade leidt tot 403
  - Goedgekeurd pad retourneert decision_id in respons
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Laag A -- architectuur/bron bewijzen
# ---------------------------------------------------------------------------


def test_legacy_router_calls_require_council_approval() -> None:
    """RC-002: execute_cva_council_gate (wraps require_council_approval) MOET aangeroepen worden in legacy_router.py."""
    router_src = (_REPO_ROOT / "src/core/api/v1/cva/legacy_router.py").read_text(encoding="utf-8")
    deps_src = (_REPO_ROOT / "src/core/api/v1/cva/dependencies.py").read_text(encoding="utf-8")
    assert "execute_cva_council_gate" in router_src, (
        "RC-002 ONTBREEKT: legacy_router.py roept execute_cva_council_gate "
        "niet aan -- council gate mist op /chat/legacy (SP-GOV-002 dag 2)"
    )
    assert "require_council_approval" in deps_src, (
        "RC-002 ONTBREEKT: cva/dependencies.py roept require_council_approval "
        "niet aan -- ADR-033 facade voor council gate mist (SP-GOV-002 dag 2)"
    )


def test_legacy_chat_response_has_decision_id_field() -> None:
    """RC-002: CVAChatResponse MOET decision_id veld bevatten."""
    src = (_REPO_ROOT / "src/core/api/v1/cva/legacy_router.py").read_text(encoding="utf-8")
    assert "decision_id" in src, (
        "RC-002 ONTBREEKT: CVAChatResponse bevat geen decision_id veld -- "
        "voeg toe voor auditbaarheid (SP-GOV-002 dag 2)"
    )


# ---------------------------------------------------------------------------
# Laag B -- gedrag: council-blokkade leidt tot 403
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    from src.core.auth.auth_service import UserResponse

    user = MagicMock(spec=UserResponse)
    user.id = 1
    user.tenant_id = 1
    user.email = "test@example.com"
    return user


@pytest.mark.asyncio
async def test_legacy_cva_council_block_returns_403(
    mock_user: MagicMock,
) -> None:
    """RC-002: chat_with_cva geeft 403 terug als council blokkeert."""
    from src.core.api.v1.cva.legacy_router import CVAChatRequest, chat_with_cva

    blocked = HTTPException(
        status_code=403,
        detail={"code": "GOVERNANCE_BLOCKED", "message": "Council blocked legacy CVA"},
    )

    with (
        patch(
            "src.core.copilot.council.factory.build_council",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(side_effect=blocked),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await chat_with_cva(
                request=CVAChatRequest(message="test bericht"),
                current_user=mock_user,
                memory=None,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_legacy_cva_happy_path_returns_decision_id(
    mock_user: MagicMock,
) -> None:
    """RC-002: chat_with_cva retourneert decision_id uit council gate in respons."""
    from src.core.api.v1.cva.legacy_router import CVAChatRequest, chat_with_cva

    mock_decision = MagicMock()
    mock_decision.decision_id = "test-rc002-decision"

    mock_cva_result = MagicMock()
    mock_cva_result.response = "Test antwoord"
    mock_cva_result.success = True
    mock_cva_result.confidence = 0.9
    mock_cva_result.execution_time = 0.1
    mock_cva_result.suggestions = []
    mock_cva_result.llm_provider_used = "openai"
    mock_cva_result.orchestration_used = False
    mock_cva_result.performance_metrics = None

    mock_agent = MagicMock()
    mock_agent.process_command = AsyncMock(return_value=mock_cva_result)

    with (
        patch(
            "src.core.copilot.council.factory.build_council",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "src.core.copilot.council.governance_gate.require_council_approval",
            new=AsyncMock(return_value=mock_decision),
        ),
        patch(
            "src.core.api.v1.cva.legacy_router.get_cva_agent",
            new=AsyncMock(return_value=mock_agent),
        ),
    ):
        result = await chat_with_cva(
            request=CVAChatRequest(message="test bericht"),
            current_user=mock_user,
            memory=None,
        )

    assert result.decision_id == "test-rc002-decision", (
        f"RC-002: decision_id ontbreekt in respons (got: {result.decision_id})"
    )
