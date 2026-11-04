"""De chat is een deur: een stilgezette klant krijgt geen modelaanroep, geen Prana-afschrijving en
een vaste Nederlandse melding (besluit A van de gebruiker, ronde 2).

Klant 1 staat stil, klant 2 is actief, klant 3 heeft een onleesbare stand (fail-closed). Alleen de
lezer van de stand en de dingen NA de deur zijn vervangen; de deur zelf draait echt.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.noodstop import guard
from src.core.noodstop.guard import (
    MELDING_CHAT_ONBEKEND,
    MELDING_CHAT_STIL,
    KlantStilgezet,
    eis_chat_actief,
)

STIL, ACTIEF, STORING = 1, 2, 3


class Doorgelaten(Exception):
    """De deur liet de aanvraag door: de eerste stap NA de deur is bereikt."""


@pytest.fixture(autouse=True)
def _standen(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        if tenant_id == STORING:
            raise ConnectionError("db weg")
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


def test_de_chatmelding_is_de_vaste_tekst_van_de_gebruiker() -> None:
    assert MELDING_CHAT_STIL == (
        "De agents van jouw organisatie staan tijdelijk stil. Neem contact op met je beheerder."
    )


@pytest.mark.asyncio
async def test_eis_chat_actief_geeft_de_chatmelding() -> None:
    with pytest.raises(KlantStilgezet) as stil:
        await eis_chat_actief(STIL)
    assert stil.value.bericht == MELDING_CHAT_STIL and not stil.value.onbekend
    with pytest.raises(KlantStilgezet) as onbekend:
        await eis_chat_actief(STORING)
    assert onbekend.value.bericht == MELDING_CHAT_ONBEKEND and onbekend.value.onbekend
    await eis_chat_actief(ACTIEF)


# --- cva_service.chat en chat_stream ------------------------------------------------------------


def _cva(monkeypatch: pytest.MonkeyPatch) -> tuple[object, MagicMock, MagicMock]:
    from src.core.services import cva_service as cs

    council = MagicMock()
    monkeypatch.setattr(cs, "build_council", council)
    service = cs.CVAService(db_session=MagicMock(), llm_service=MagicMock())
    maak_gesprek = AsyncMock(side_effect=Doorgelaten())
    llm = AsyncMock(side_effect=Doorgelaten())
    service._create_conversation = maak_gesprek  # type: ignore[method-assign]
    service._llm_voor = llm  # type: ignore[method-assign]
    return service, maak_gesprek, council


@pytest.mark.asyncio
async def test_cva_chat_weigert_de_stilgezette_klant_zonder_model_of_council(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, maak_gesprek, council = _cva(monkeypatch)
    with pytest.raises(HTTPException) as fout:
        await service.chat(message="hoi", user_id=1, tenant_id=STIL)  # type: ignore[attr-defined]
    assert fout.value.status_code == 403
    assert fout.value.detail == MELDING_CHAT_STIL
    maak_gesprek.assert_not_awaited()
    service._llm_voor.assert_not_awaited()  # type: ignore[attr-defined]
    council.assert_not_called()


@pytest.mark.asyncio
async def test_cva_chat_weigert_fail_closed_bij_onbekende_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, maak_gesprek, _ = _cva(monkeypatch)
    with pytest.raises(HTTPException) as fout:
        await service.chat(message="hoi", user_id=1, tenant_id=STORING)  # type: ignore[attr-defined]
    assert fout.value.status_code == 503
    assert fout.value.detail == MELDING_CHAT_ONBEKEND
    maak_gesprek.assert_not_awaited()


@pytest.mark.asyncio
async def test_cva_chat_van_een_andere_klant_komt_voorbij_de_deur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, maak_gesprek, _ = _cva(monkeypatch)
    with pytest.raises(Doorgelaten):
        await service.chat(message="hoi", user_id=1, tenant_id=ACTIEF)  # type: ignore[attr-defined]
    maak_gesprek.assert_awaited_once()


@pytest.mark.asyncio
async def test_cva_chat_stream_geeft_een_melding_en_geen_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, maak_gesprek, council = _cva(monkeypatch)
    brokken = [b async for b in service.chat_stream(message="hoi", user_id=1, tenant_id=STIL)]  # type: ignore[attr-defined]
    assert [json.loads(b) for b in brokken] == [{"error": MELDING_CHAT_STIL, "code": "NOODSTOP"}]
    maak_gesprek.assert_not_awaited()
    service._llm_voor.assert_not_awaited()  # type: ignore[attr-defined]
    council.assert_not_called()


@pytest.mark.asyncio
async def test_cva_chat_stream_van_een_andere_klant_komt_voorbij_de_deur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, maak_gesprek, _ = _cva(monkeypatch)
    with pytest.raises(Doorgelaten):
        _ = [b async for b in service.chat_stream(message="hoi", user_id=1, tenant_id=ACTIEF)]  # type: ignore[attr-defined]
    maak_gesprek.assert_awaited_once()


# --- copilot (HTTP en websocket lopen allebei via handle_turn) ----------------------------------


def _copilot() -> tuple[object, MagicMock, MagicMock]:
    from src.core.copilot.service import CopilotService

    llm_handler = MagicMock()
    prana = MagicMock()
    prana.charge = AsyncMock()
    service = CopilotService(
        council=MagicMock(),
        llm_handler=llm_handler,
        proposal_builder=MagicMock(),
        prana_service=prana,
    )
    service._augment_context = AsyncMock(side_effect=Doorgelaten())  # type: ignore[method-assign]
    return service, llm_handler, prana


@pytest.mark.asyncio
async def test_copilot_beurt_van_de_stilgezette_klant_raakt_model_en_prana_niet() -> None:
    service, llm_handler, prana = _copilot()
    antwoord = await service.handle_turn(tenant_id=STIL, user_id=1, message="hoi", context={})  # type: ignore[attr-defined]
    assert antwoord.verdict == "blocked"
    assert antwoord.message == MELDING_CHAT_STIL
    service._augment_context.assert_not_awaited()  # type: ignore[attr-defined]
    assert llm_handler.mock_calls == []
    prana.charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_copilot_beurt_weigert_fail_closed_bij_onbekende_stand() -> None:
    service, llm_handler, _ = _copilot()
    antwoord = await service.handle_turn(tenant_id=STORING, user_id=1, message="hoi", context={})  # type: ignore[attr-defined]
    assert antwoord.verdict == "blocked" and antwoord.message == MELDING_CHAT_ONBEKEND
    assert llm_handler.mock_calls == []


@pytest.mark.asyncio
async def test_copilot_beurt_van_een_andere_klant_komt_voorbij_de_deur() -> None:
    service, _, _ = _copilot()
    with pytest.raises(Doorgelaten):
        await service.handle_turn(tenant_id=ACTIEF, user_id=1, message="hoi", context={})  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_copilot_stream_geeft_voor_de_stilgezette_klant_alleen_de_weigering() -> None:
    service, llm_handler, _ = _copilot()
    kaders = [
        k
        async for k in service.handle_turn_stream(  # type: ignore[attr-defined]
            tenant_id=STIL, user_id=1, message="hoi", context={}
        )
    ]
    assert kaders[-1]["payload"]["message"] == MELDING_CHAT_STIL
    assert llm_handler.mock_calls == []


# --- agentic chat (src/domains/agentic) ---------------------------------------------------------


def _agentic(monkeypatch: pytest.MonkeyPatch) -> tuple[object, MagicMock]:
    from src.domains.agentic.services.chat_service import AgentChatService

    service = object.__new__(AgentChatService)
    sessie = AsyncMock(side_effect=Doorgelaten())
    service._get_or_create_session = sessie  # type: ignore[method-assign]
    return service, sessie


def _verzoek(tenant_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        message="hoi",
        user_id=1,
        tenant_id=tenant_id,
        session_id=None,
        feature_context=None,
        locale=None,
        route_path=None,
        metadata=None,
    )


@pytest.mark.asyncio
async def test_agentic_chat_weigert_de_stilgezette_klant_voor_er_een_sessie_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, sessie = _agentic(monkeypatch)
    with pytest.raises(KlantStilgezet) as stop:
        await service.process_chat(MagicMock(), _verzoek(STIL))  # type: ignore[attr-defined]
    assert stop.value.bericht == MELDING_CHAT_STIL
    sessie.assert_not_awaited()


@pytest.mark.asyncio
async def test_het_agent_endpoint_vertaalt_de_weigering_naar_403_en_503() -> None:
    from src.api.v1.endpoints import agent as endpoint

    for klant, status, melding in (
        (STIL, 403, MELDING_CHAT_STIL),
        (STORING, 503, MELDING_CHAT_ONBEKEND),
    ):
        service = MagicMock()
        service.process_chat = AsyncMock(
            side_effect=KlantStilgezet(melding, onbekend=klant == STORING)
        )
        endpoint._chat_service = service
        try:
            with pytest.raises(HTTPException) as fout:
                await endpoint.process_chat(
                    request=SimpleNamespace(
                        message="hoi",
                        session_id=None,
                        feature_context=None,
                        locale=None,
                        metadata=None,
                    ),
                    x_feature_context=None,
                    x_route_path=None,
                    current_user=SimpleNamespace(id=1, tenant_id=klant),
                    db=MagicMock(),
                )
        finally:
            endpoint._chat_service = None
        assert fout.value.status_code == status and fout.value.detail == melding


@pytest.mark.asyncio
async def test_agentic_chat_stream_geeft_een_foutkader_zonder_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, sessie = _agentic(monkeypatch)
    kaders = [k async for k in service.process_chat_stream(MagicMock(), _verzoek(STIL))]  # type: ignore[attr-defined]
    assert kaders == [{"type": "error", "error": MELDING_CHAT_STIL, "code": "NOODSTOP"}]
    sessie.assert_not_awaited()


@pytest.mark.asyncio
async def test_agentic_chat_van_een_andere_klant_komt_voorbij_de_deur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, sessie = _agentic(monkeypatch)
    with pytest.raises(Doorgelaten):
        await service.process_chat(MagicMock(), _verzoek(ACTIEF))  # type: ignore[attr-defined]
    sessie.assert_awaited_once()
