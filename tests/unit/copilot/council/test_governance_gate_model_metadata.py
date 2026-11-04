"""
RC-003: CVA require_council_approval aanroepen met echte model_id.

Tests zijn ROOD totdat RC-003 fix is geimplementeerd (SP-GOV-002 dag 1).
Na de fix:
  - cva_service.py geeft model_id=getattr(effective_llm, 'model', 'unknown') door
  - compute_canonical_json() bevat model_id en model_version in de hash-invoer
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# RC-003a: CVAService geeft echte model_id door
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cva_chat_passes_real_model_id_to_council() -> None:
    """RC-003: CVAService.chat() geeft model_id != 'unknown' door aan require_council_approval."""
    from src.core.services.cva_service import CVAService

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    db_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=db_result)

    mock_llm = MagicMock()
    mock_llm.model = "gemini-1.5-pro"
    mock_llm.provider.provider_name = "gemini"
    mock_llm.generate = AsyncMock(
        return_value=("Antwoord", {"total_tokens": 5, "model": "gemini-1.5-pro"})
    )

    mock_decision = MagicMock()
    mock_decision.decision_id = "test-decision-rc003"
    mock_council = MagicMock()
    mock_gate = AsyncMock(return_value=mock_decision)

    with (
        patch(
            "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "src.core.services.cva_service.build_council",
            new_callable=AsyncMock,
            return_value=mock_council,
        ),
        patch(
            "src.core.services.cva_service.require_council_approval",
            mock_gate,
        ),
    ):
        svc = CVAService(db_session=mock_db, llm_service=mock_llm)
        await svc.chat(message="Test bericht", user_id=1, tenant_id=1)

    mock_gate.assert_called_once()
    call_kwargs = mock_gate.call_args.kwargs
    model_id_passed = call_kwargs.get("model_id", "unknown")
    assert model_id_passed != "unknown", (
        "RC-003 ONTBREEKT: require_council_approval ontving model_id='unknown' "
        "maar effective_llm.model='gemini-1.5-pro' -- geef echte model_id door (SP-GOV-002)"
    )


@pytest.mark.asyncio
async def test_cva_chat_falls_back_to_unknown_when_llm_has_no_model_attr() -> None:
    """RC-003: CVAService.chat() valt terug op 'unknown' als effective_llm geen .model heeft."""
    from src.core.services.cva_service import CVAService

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    db_result = MagicMock()
    db_result.scalar_one_or_none.return_value = None
    db_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=db_result)

    # LLM without .model attribute: use spec that excludes 'model'
    # getattr(mock_llm, 'model', 'unknown') raises AttributeError via spec -> returns 'unknown'
    class _LLMSpec:
        provider: object
        generate: object

    mock_llm = MagicMock(spec=_LLMSpec)
    mock_llm.provider = MagicMock()
    mock_llm.provider.provider_name = "unknown_provider"
    mock_llm.generate = AsyncMock(
        return_value=("Antwoord", {"total_tokens": 5, "model": "unknown"})
    )

    mock_decision = MagicMock()
    mock_decision.decision_id = "test-decision-fallback"
    mock_council = MagicMock()
    mock_gate = AsyncMock(return_value=mock_decision)

    with (
        patch(
            "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "src.core.services.cva_service.build_council",
            new_callable=AsyncMock,
            return_value=mock_council,
        ),
        patch(
            "src.core.services.cva_service.require_council_approval",
            mock_gate,
        ),
    ):
        svc = CVAService(db_session=mock_db, llm_service=mock_llm)
        await svc.chat(message="Test bericht", user_id=1, tenant_id=1)

    mock_gate.assert_called_once()
    call_kwargs = mock_gate.call_args.kwargs
    model_id_passed = call_kwargs.get("model_id", "unknown")
    assert model_id_passed == "unknown", (
        f"RC-003: fallback moet 'unknown' zijn maar was '{model_id_passed}'"
    )


# ---------------------------------------------------------------------------
# RC-003b: compute_canonical_json bevat model_id in hash-invoer
# ---------------------------------------------------------------------------


def _make_audit_writer_and_proposal() -> tuple[Any, Any]:
    """Shared setup voor canonical JSON tests."""
    from src.core.copilot.council.audit_writer import CouncilAuditWriter
    from src.core.copilot.council.types import (
        DataClassification,
        Proposal,
        ProposalTrigger,
    )

    null_ctx = MagicMock()
    null_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    null_ctx.__aexit__ = AsyncMock(return_value=False)
    writer = CouncilAuditWriter(db_session_factory=lambda: null_ctx)  # type: ignore[arg-type]

    proposal = Proposal(
        tenant_id=1,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="cva.chat",
        action_params={"conversation_id": 42},
        reasoning="Test redenering",
        data_classification=DataClassification.INTERNAL,
        confidence=1.0,
        model_id="gpt-4-turbo",
        model_version="2024-04-09",
        context_snapshot={},
    )
    return writer, proposal


def test_canonical_json_contains_model_id_key() -> None:
    """RC-003: compute_canonical_json() MOET 'model_id' sleutel bevatten in hash-invoer."""
    from src.core.copilot.council.types import DecisionVerdict

    writer, proposal = _make_audit_writer_and_proposal()
    canonical = writer.compute_canonical_json(
        proposal=proposal,
        officer_verdicts=(),
        final_verdict=DecisionVerdict.APPROVED,
        previous_hash=None,
        explanation_for_user="Goedgekeurd",
    )
    data = json.loads(canonical)
    assert "model_id" in data, (
        "RC-003 ONTBREEKT: compute_canonical_json() bevat geen 'model_id' -- "
        "voeg model_id toe aan hash-invoer (SP-GOV-002)"
    )


def test_canonical_json_model_id_value_matches_proposal() -> None:
    """RC-003: model_id in canonical JSON MOET overeenkomen met Proposal.model_id."""
    from src.core.copilot.council.types import DecisionVerdict

    writer, proposal = _make_audit_writer_and_proposal()
    canonical = writer.compute_canonical_json(
        proposal=proposal,
        officer_verdicts=(),
        final_verdict=DecisionVerdict.APPROVED,
        previous_hash=None,
        explanation_for_user="Goedgekeurd",
    )
    data = json.loads(canonical)
    assert data.get("model_id") == "gpt-4-turbo", (
        f"RC-003: model_id in canonical JSON is '{data.get('model_id')}', verwacht 'gpt-4-turbo'"
    )


# ---------------------------------------------------------------------------
# RC-003c: chat_stream geeft echte model_id door (regressiebewaker)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cva_chat_stream_passes_real_model_id_to_council() -> None:
    """RC-003: CVAService.chat_stream() geeft model_id != 'unknown' door aan require_council_approval."""
    from unittest.mock import patch

    from src.core.services.cva_service import CVAService

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    mock_llm = MagicMock()
    mock_llm.model = "gpt-4-turbo"
    mock_llm.provider.provider_name = "openai"

    mock_decision = MagicMock()
    mock_decision.decision_id = "test-stream-decision"
    mock_council = MagicMock()
    mock_gate = AsyncMock(return_value=mock_decision)

    mock_conversation = MagicMock()
    mock_conversation.id = 99

    with (
        patch(
            "src.core.services.cva_service.build_council",
            new_callable=AsyncMock,
            return_value=mock_council,
        ),
        patch(
            "src.core.services.cva_service.require_council_approval",
            mock_gate,
        ),
    ):
        svc = CVAService(db_session=mock_db, llm_service=mock_llm)
        with patch.object(
            svc, "_create_conversation", new=AsyncMock(return_value=mock_conversation)
        ):
            gen = svc.chat_stream(message="Test bericht", user_id=1, tenant_id=1)
            try:
                await gen.__anext__()
            except (StopAsyncIteration, Exception):
                pass
            finally:
                await gen.aclose()

    mock_gate.assert_called_once()
    call_kwargs = mock_gate.call_args.kwargs
    model_id_passed = call_kwargs.get("model_id", "unknown")
    assert model_id_passed != "unknown", (
        "RC-003 ONTBREEKT in chat_stream: require_council_approval ontving model_id='unknown' "
        "maar self.llm.model='gpt-4-turbo' -- geef echte model_id door (SP-GOV-002)"
    )
