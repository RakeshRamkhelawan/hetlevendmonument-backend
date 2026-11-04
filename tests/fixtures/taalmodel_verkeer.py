"""Vangt AL het HTTP-verkeer van taalmodelaanroepen op en onthoudt naar welke host het ging.

Brief 2026-10-19 (DeepSeek overal eruit): het bewijs per pad is "met `DEEPSEEK_API_KEY` en een Mistralsleutel
gezet gaat er geen verzoek naar DeepSeek". Dat bewijs hoort op de HTTP-LAAG, niet op een mock van de
clientklasse: een mock van `DeepSeekProvider` ziet een eigen client met `openai.OpenAI(...)` of een
`ChatOpenAI` niet, terwijl elke client uiteindelijk een `httpx`-transport gebruikt.

Hier worden daarom de twee TRANSPORTMETHODEN van httpx vervangen (`HTTPTransport.handle_request` en
`AsyncHTTPTransport.handle_async_request`). Elke client, ook een die een bibliotheek zelf bouwt (openai,
langchain), loopt daar langs. Er gaat niets het netwerk op; het antwoord is een vast OpenAI-chatantwoord.

De vervangen methoden lezen/loggen geen headers, dus er komt ook geen sleutel in het verkeerslogboek.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

#: Hosts die NOOIT een klantverzoek mogen ontvangen (geen verwerkersovereenkomst of niet de keuze van de klant).
VERBODEN_HOSTS = (
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
    "generativelanguage.googleapis.com",
)


@dataclass
class Verkeer:
    """Wat er aan verzoeken langskwam."""

    hosts: list[str] = field(default_factory=list)
    paden: list[str] = field(default_factory=list)
    lichamen: list[dict[str, object]] = field(default_factory=list)

    def verboden(self) -> list[str]:
        return sorted({h for h in self.hosts if h in VERBODEN_HOSTS})


def _antwoord(inhoud: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "cmpl-test",
            "model": "mistral-small-latest",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": inhoud},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            # De vorm van Ollama (`/api/chat`): hetzelfde antwoord, zodat een lokaal model dat dit pad volgt
            # ook een bruikbaar antwoord krijgt.
            "message": {"role": "assistant", "content": inhoud},
            "done": True,
            "prompt_eval_count": 1,
            "eval_count": 1,
        },
    )


def installeer_verkeer(
    monkeypatch: pytest.MonkeyPatch, inhoud: str = "ok", onbereikbaar: tuple[str, ...] = ()
) -> Verkeer:
    """Zet de opvang aan voor deze test en geeft het logboek terug.

    `onbereikbaar`: hosts waarvoor het verzoek WEL wordt genoteerd maar met een verbindingsfout eindigt
    (een lokaal model dat uit staat). Het verzoek telt dus mee in `hosts`.
    """
    verkeer = Verkeer()

    def noteer(request: httpx.Request) -> None:
        if request.url.host in onbereikbaar:
            verkeer.hosts.append(request.url.host)
            raise httpx.ConnectError("onbereikbaar (testdubbel)", request=request)
        verkeer.hosts.append(request.url.host)
        verkeer.paden.append(request.url.path)
        try:
            lichaam = json.loads(request.content or b"{}")
        except ValueError:
            lichaam = {}
        verkeer.lichamen.append(lichaam if isinstance(lichaam, dict) else {})

    def sync_verzoek(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        request.read()
        noteer(request)
        return _antwoord(inhoud)

    async def async_verzoek(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        await request.aread()
        noteer(request)
        return _antwoord(inhoud)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", sync_verzoek)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_verzoek)
    return verkeer
