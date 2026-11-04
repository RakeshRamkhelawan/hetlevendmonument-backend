"""De LLM-service verliest de oorzaak van een fout niet meer (workflowscherm nazorg, Gate 2 code-review).

`LLMService.generate` verpakte een mislukte aanroep in een `LLMServiceError` zonder `from`. Een tijdelijke fout van de aanbieder
(HTTP 502, 503, 504, een verbindingsfout) was daardoor in de workflowengine niet meer te herkennen en kreeg geen nieuwe poging,
terwijl de engine alleen op de oorzaak kan beoordelen of een nieuwe poging zin heeft (`foutsoort.is_tijdelijke_fout`).

Mutatiebewijs (2026-10-26): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.core.services.llm.base import LLMMessage, LLMServiceError
from src.core.services.llm.service import LLMService
from src.core.workflow.foutsoort import is_tijdelijke_fout


def _service(fout: BaseException) -> LLMService:
    service = LLMService(provider="mock", model="mock-model", max_retries=1)
    service.provider.generate = AsyncMock(side_effect=fout)  # type: ignore[method-assign]
    return service


def _vraag() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="Hallo")]


@pytest.mark.asyncio
async def test_een_gewone_fout_van_de_aanbieder_blijft_als_oorzaak_beschikbaar() -> None:
    oorspronkelijk = ValueError("kapot")

    with pytest.raises(LLMServiceError) as fout:
        await _service(oorspronkelijk).generate(messages=_vraag())

    assert fout.value.__cause__ is oorspronkelijk


@pytest.mark.asyncio
async def test_een_verbindingsfout_na_alle_pogingen_behoudt_de_oorzaak() -> None:
    oorspronkelijk = ConnectionError("verbroken")

    with pytest.raises(LLMServiceError) as fout:
        await _service(oorspronkelijk).generate(messages=_vraag())

    assert fout.value.__cause__ is oorspronkelijk


@pytest.mark.asyncio
async def test_een_tijdelijk_onbereikbare_aanbieder_is_in_de_engine_te_herkennen() -> None:
    verzoek = httpx.Request("POST", "https://api.example/v1/chat")
    onbereikbaar = httpx.HTTPStatusError(
        "503", request=verzoek, response=httpx.Response(503, request=verzoek)
    )

    with pytest.raises(LLMServiceError) as fout:
        await _service(onbereikbaar).generate(messages=_vraag())

    assert is_tijdelijke_fout(fout.value) is True


@pytest.mark.asyncio
async def test_een_ongeldige_aanvraag_blijft_inhoudelijk() -> None:
    verzoek = httpx.Request("POST", "https://api.example/v1/chat")
    ongeldig = httpx.HTTPStatusError(
        "400", request=verzoek, response=httpx.Response(400, request=verzoek)
    )

    with pytest.raises(LLMServiceError) as fout:
        await _service(ongeldig).generate(messages=_vraag())

    assert is_tijdelijke_fout(fout.value) is False
