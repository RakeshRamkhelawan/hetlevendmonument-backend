"""Een gecontroleerd adres helpt alleen als het verzoek ER OOK HEEN GAAT.

**De faalvorm die deze tests vastleggen (BE-LLM-004).** De SSRF-controle keurt een adres goed
door de naam op te zoeken en de antwoorden te toetsen. Geeft de laag daarna de NAAM door aan de
HTTP-client, dan zoekt die hem opnieuw op -- en het antwoord kan dan een ander adres zijn. Dat
is DNS-rebinding, en het is in 2026 tweemaal als kwetsbaarheid uitgebracht in precies deze
constructie: de URL-component van Langflow en `mcp-atlassian` (CVE-2026-27826). De controle
leest dan als bescherming en is het niet.

De verdediging bestaat uit drie delen die alleen SAMEN werken, en daarom staan ze hier alle
drie in een assertie:

1. het verzoek gaat naar het IP dat is goedgekeurd;
2. de `Host`-kop draagt de oorspronkelijke naam, anders antwoordt een server met naamgebaseerde
   virtuele hosts met de verkeerde site of met een weigering;
3. `sni_hostname` draagt diezelfde naam, anders valideert de TLS-laag het certificaat tegen een
   IP-adres en mislukt elke normale verbinding.

De tegenrichting hoort er net zo hard bij: zonder vastgepind IP -- het lokale model op
`127.0.0.1`, de bodem van de keten -- mag er NIETS veranderen.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.core.services.llm.base import LLMConfig, LLMMessage
from src.core.services.llm.providers import OpenAICompatibleProvider

NAAM_ADRES = "https://llm.klant.test/v1"
GEVALIDEERD_IP = "203.0.113.7"
LOKAAL = "http://127.0.0.1:11434/v1"


def _provider(**overrides: object) -> OpenAICompatibleProvider:
    kwargs: dict[str, object] = {"model": "een-model", "base_url": NAAM_ADRES}
    kwargs.update(overrides)
    return OpenAICompatibleProvider(LLMConfig(**kwargs))  # type: ignore[arg-type]  # dataclass, dict komt uit deze functie


def _vang_verzoek(provider: OpenAICompatibleProvider) -> list[httpx.Request]:
    """Vervang de client van DIT exemplaar en bewaar het verzoek dat eruit komt.

    Via `_client()` en niet via een patch op `openai_compatible.httpx`: dat laatste raakt het
    httpx-PAKKET en daarmee elke andere gebruiker in het proces (gemeten bij de Gate 2-review
    van BE-LLM-002).
    """
    gezien: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        gezien.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "model": "een-model",
            },
        )

    echte_client = httpx.AsyncClient
    provider._client = lambda: echte_client(  # type: ignore[method-assign]  # testdubbel per exemplaar
        transport=httpx.MockTransport(_handler)
    )
    return gezien


@pytest.mark.asyncio
async def test_het_verzoek_gaat_naar_het_IP_met_de_naam_in_host_en_sni() -> None:
    provider = _provider(pinned_ip=GEVALIDEERD_IP, sni_hostname="llm.klant.test")
    gezien = _vang_verzoek(provider)

    await provider.generate([LLMMessage(role="user", content="hallo")])

    assert len(gezien) == 1
    verzoek = gezien[0]
    assert verzoek.url.host == GEVALIDEERD_IP, (
        "het verzoek ging naar de NAAM en niet naar het gevalideerde adres -- dan zoekt de "
        "client zelf opnieuw op en is de controle een advies"
    )
    assert verzoek.headers["Host"] == "llm.klant.test"
    assert verzoek.extensions.get("sni_hostname") == "llm.klant.test"


@pytest.mark.asyncio
async def test_het_pad_en_de_poort_overleven_het_vastpinnen() -> None:
    """Een klanteindpunt op een eigen poort met een eigen pad moet bereikbaar blijven."""
    provider = _provider(
        base_url="https://llm.klant.test:8443/api/v1",
        pinned_ip=GEVALIDEERD_IP,
        sni_hostname="llm.klant.test",
    )
    gezien = _vang_verzoek(provider)

    await provider.generate([LLMMessage(role="user", content="hallo")])

    verzoek = gezien[0]
    assert verzoek.url.host == GEVALIDEERD_IP
    assert verzoek.url.port == 8443
    assert verzoek.url.path == "/api/v1/chat/completions"
    assert verzoek.headers["Host"] == "llm.klant.test:8443"


@pytest.mark.asyncio
async def test_zonder_vastpinnen_verandert_er_NIETS() -> None:
    """De tegenrichting. Zonder deze test is 'altijd naar een IP' een geldige oplossing."""
    provider = _provider(base_url=LOKAAL)
    gezien = _vang_verzoek(provider)

    await provider.generate([LLMMessage(role="user", content="hallo")])

    verzoek = gezien[0]
    assert verzoek.url.host == "127.0.0.1"
    assert verzoek.url.port == 11434
    # httpx zet zelf een Host-kop uit de URL; wat hier niet mag is dat WIJ hem overschrijven.
    assert verzoek.headers["Host"] == "127.0.0.1:11434"
    assert "sni_hostname" not in verzoek.extensions


@pytest.mark.asyncio
async def test_bij_http_gaat_er_GEEN_sni_mee() -> None:
    """Er is geen TLS-handdruk bij `http`, dus een servernaam zou daar alleen ruis zijn."""
    provider = _provider(
        base_url="http://llm.intern.test/v1",
        pinned_ip=GEVALIDEERD_IP,
        sni_hostname="llm.intern.test",
    )
    gezien = _vang_verzoek(provider)

    await provider.generate([LLMMessage(role="user", content="hallo")])

    verzoek = gezien[0]
    assert verzoek.url.host == GEVALIDEERD_IP
    assert verzoek.headers["Host"] == "llm.intern.test"
    assert "sni_hostname" not in verzoek.extensions


@pytest.mark.asyncio
async def test_ook_het_streampad_pint_vast() -> None:
    """Twee wegen naar buiten, twee keer dezelfde eis.

    Een eerdere ronde in dit project leverde precies deze fout op: een reparatie op het gewone
    pad, terwijl het streampad zijn eigen aanroep heeft en ongemoeid bleef.
    """
    provider = _provider(pinned_ip=GEVALIDEERD_IP, sni_hostname="llm.klant.test")
    gezien: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        gezien.append(request)
        brok = json.dumps({"choices": [{"delta": {"content": "hoi"}}]})
        return httpx.Response(200, text="data: " + brok + "\n\ndata: [DONE]\n\n")

    echte_client = httpx.AsyncClient
    provider._client = lambda: echte_client(  # type: ignore[method-assign]  # testdubbel per exemplaar
        transport=httpx.MockTransport(_handler)
    )

    stukjes: list[Any] = [s async for s in provider.stream([LLMMessage(role="user", content="x")])]

    assert stukjes == ["hoi"]
    verzoek = gezien[0]
    assert verzoek.url.host == GEVALIDEERD_IP
    assert verzoek.headers["Host"] == "llm.klant.test"
    assert verzoek.extensions.get("sni_hostname") == "llm.klant.test"


@pytest.mark.asyncio
async def test_een_omleiding_wordt_niet_gevolgd() -> None:
    """Een 3xx mag geen tweede, ONGECONTROLEERD verzoek opleveren.

    Dit is de scherpste faalvorm die een Gate 2-reviewer aanwees, en hij zit niet in onze code
    maar in een standaardwaarde van httpx. Zou de client een omleiding volgen, dan zoekt hij de
    nieuwe bestemming zelf op -- buiten de adrescontrole om, zonder vastgepind IP -- en neemt
    hij `sni_hostname` mee naar een andere host. Het hele vastpinnen is dan weg, en geen enkele
    andere test in dit bestand merkt het, want die geven allemaal een 200 terug.

    De test eist daarom twee dingen: er gaat precies EEN verzoek uit, en het eindigt in een
    fout in plaats van in een antwoord van de omleidingsbestemming.
    """
    provider = _provider(pinned_ip=GEVALIDEERD_IP, sni_hostname="llm.klant.test")

    assert provider._client().follow_redirects is False, (
        "`_client()` bouwt een client die omleidingen volgt; dan gaat er een verzoek naar een "
        "adres dat nooit is gecontroleerd"
    )

    gezien: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        gezien.append(request)
        if len(gezien) == 1:
            return httpx.Response(302, headers={"Location": "https://ergens-anders.test/v1"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "gelekt"}}]})

    echte_client = httpx.AsyncClient
    provider._client = lambda: echte_client(  # type: ignore[method-assign]  # testdubbel per exemplaar
        transport=httpx.MockTransport(_handler), follow_redirects=False
    )

    with pytest.raises(Exception):
        await provider.generate([LLMMessage(role="user", content="hallo")])

    assert len(gezien) == 1, (
        "de client volgde de omleiding; dan gaat er een verzoek naar een adres dat nooit is "
        "gecontroleerd en is het vastpinnen omzeild"
    )


def test_de_client_zet_follow_redirects_EXPLICIET_uit() -> None:
    """Onze bedoeling moet in de code staan, niet in een standaardwaarde van een ander.

    **Waarom dit een toets op de BRON is en niet op gedrag.** Een assertie op
    `provider._client().follow_redirects is False` blijft groen als je de vlag weghaalt, want
    httpx heeft vandaag dezelfde standaard. Gemeten met het mutatieharnas: de mutatie
    "haal `follow_redirects=False` weg" werd door geen enkele gedragstest betrapt. Dat is
    precies het probleem dat een Gate 2-reviewer aanwees: de sterkste claim van BE-LLM-004
    ("het verzoek gaat waar de controle keek") rust dan op een default van een derde partij
    die al eens is aangeraakt, en niet op een afspraak van ons.

    Deze toets sterft wel bij die mutatie, en dat is het enige wat hem rechtvaardigt.
    """
    import ast
    from pathlib import Path

    bron = Path("src/core/services/llm/providers/openai_compatible.py").read_text(encoding="utf-8")
    boom = ast.parse(bron)

    methode = next(
        (
            n
            for n in ast.walk(boom)
            if isinstance(n, ast.FunctionDef) and n.name == "_client"
        ),
        None,
    )
    assert methode is not None, "`_client` bestaat niet meer -- is hij hernoemd?"

    expliciet = [
        kw
        for aanroep in ast.walk(methode)
        if isinstance(aanroep, ast.Call)
        for kw in aanroep.keywords
        if kw.arg == "follow_redirects"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is False
    ]
    assert expliciet, (
        "`_client()` zet `follow_redirects=False` niet expliciet. Vandaag is dat ook de "
        "standaard van httpx, dus er gaat niets stuk -- tot die standaard verandert, en dan is "
        "het vastpinnen in een klap waardeloos zonder dat een test het merkt"
    )
