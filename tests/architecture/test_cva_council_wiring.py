"""Architecture guard: CVA chat MOET via require_council_approval lopen.

Test is ROOD totdat AIACT-003 fix is doorgevoerd.
TODO(SP-CVA-SEC): council gate ontbreekt -- EU AI Act Art. 14.
"""

import pathlib


def test_cva_service_calls_require_council_approval():
    """cva_service.py MOET require_council_approval importeren en aanroepen (AIACT-003)."""
    src = pathlib.Path("src/core/services/cva_service.py").read_text(encoding="utf-8")
    assert "require_council_approval" in src, (
        "TODO(SP-CVA-SEC): require_council_approval ONTBREEKT in cva_service.py. "
        "Fix: importeer en roep require_council_approval() aan in CVAService.chat() "
        "en CVAService.chat_stream() voordat LLMService.generate() wordt aangeroepen. "
        "EU AI Act Art. 14 (human oversight) vereist governance-gate voor AI-chat."
    )


def test_cva_chat_router_has_no_council_todo():
    """chat_router.py mag GEEN TODO voor council integratie meer bevatten (ARCH-014)."""
    src = pathlib.Path("src/core/api/v1/cva/chat_router.py").read_text(encoding="utf-8")
    assert "TODO(SP-VOLGENDE): governance/council" not in src, (
        "TODO voor council integratie is nog aanwezig in chat_router.py. "
        "Verwijder de TODO nadat AIACT-003 is geimplementeerd."
    )


def test_cva_chat_response_returns_decision_id():
    """ChatResponse schema MOET een decision_id veld bevatten (AIACT-002)."""
    src = pathlib.Path("src/core/schemas/cva_schemas.py").read_text(encoding="utf-8")
    assert "decision_id" in src, (
        "TODO(SP-CVA-SEC): decision_id ONTBREEKT in ChatResponse schema. "
        "Fix: voeg decision_id: str | None toe aan ChatResponse. "
        "Vereist voor Right-to-Explanation koppeling (EU AI Act Art. 13)."
    )
