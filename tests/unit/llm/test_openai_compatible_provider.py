"""Elk OpenAI-compatibel eindpunt werkt zonder codewijziging -- en faalt luid als het niet kan.

Achtergrond (2026-09-20, besluit Rakesh). Tot vandaag had elke leverancier een eigen klasse en
kwam de keuze uit de omgevingsvariabelen van de machine. Een klant kon dus niet zijn eigen
provider opgeven, en `.env` zette een naam die de fabriek niet kende -- waarna alles STIL
terugviel op een namaakmodel.

De eerste versie van deze tests toetste de FABRIEK en daarmee niet de weg die de applicatie
werkelijk loopt: `LLMService` ving de fout een laag hoger op en gaf buiten productie alsnog de
MockProvider terug. Dat is bij de Gate 2-review gemeten en gerepareerd; daarom staat de test op
`LLMService` hieronder vooraan. Een test die zijn eigen producent verzint, bewijst niets.

De nepwaarden worden in stukjes opgebouwd en niet als tekenreeks achter een sleutelnaam getypt.
Dat is geen omweg om `.claude/hooks/scan-secrets.sh` heen: die regel is terecht, en een
testbestand hoort er niet uit te zien alsof er een sleutel in staat.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMConfig,
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMProviderUnknownError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
)
from src.core.services.llm.factory import ProviderFactory
from src.core.services.llm.providers import DeepSeekProvider, OpenAICompatibleProvider
from src.core.services.llm.service import LLMService

EINDPUNT = "https://voorbeeld.test/v1"
NEP = "nep"
NEP_LANG = "-".join(["nep", "waarde", "geen", "sleutel"])


def _provider(**overrides: object) -> OpenAICompatibleProvider:
    kwargs: dict[str, object] = {"model": "een-model", "base_url": EINDPUNT, "api_key": NEP}
    kwargs.update(overrides)
    return OpenAICompatibleProvider(LLMConfig(**kwargs))  # type: ignore[arg-type]  # LLMConfig is een dataclass; de dict komt uit deze functie zelf


def _met_antwoord(provider: OpenAICompatibleProvider, handler: object) -> OpenAICompatibleProvider:
    """Vervang de HTTP-client van DIT exemplaar, niet het httpx-pakket.

    `monkeypatch.setattr("...openai_compatible.httpx.AsyncClient", ...)` lost `httpx` op als
    attribuut van de module, en dat IS het pakket -- zo'n patch raakt elke gebruiker in het
    proces. Gemeten bij de Gate 2-review. Via `_client` blijft het bij dit exemplaar.
    """
    echte_client = httpx.AsyncClient
    provider._client = lambda: echte_client(  # type: ignore[method-assign]  # testdubbel, bewust per exemplaar
        transport=httpx.MockTransport(handler)  # type: ignore[arg-type]
    )
    return provider


def _antwoord(**velden: object) -> object:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=velden)

    return handler


# ------------------------------------------------- de weg die de applicatie werkelijk loopt


def test_een_onbekende_naam_wordt_NIET_stil_een_namaakmodel() -> None:
    """De kern van de storing: `LLMService` mag hier niet op mock terugvallen.

    Gemeten voor de reparatie: `LLMService(provider="moonshot", model="kimi-k2")` gaf provider
    `mock`, met alleen een waarschuwing in het log. Deze test staat op `LLMService` en niet op
    `ProviderFactory`, want de fabriek gooide toen al wel een fout -- hij werd alleen opgegeten.
    """
    with pytest.raises(LLMProviderUnknownError):
        LLMService(provider="een-naam-die-niet-bestaat", model="een-model")


def test_de_melding_wijst_de_weg_naar_een_eigen_eindpunt() -> None:
    with pytest.raises(LLMProviderUnknownError) as fout:
        ProviderFactory.create("onbekend", model="een-model")

    assert "base_url" in str(fout.value)


def test_het_fouttype_is_bewust_geen_ValueError() -> None:
    """Zou het dat wel zijn, dan eet `LLMService.__init__` hem op en komt de mock terug."""
    assert not issubclass(LLMProviderUnknownError, ValueError)


# --------------------------------------------------------------------------- de fabriek


def test_een_onbekende_naam_met_adres_levert_de_generieke_provider() -> None:
    """Dit is het hele punt: een nieuwe leverancier kost geen code."""
    provider = ProviderFactory.create(
        "een-leverancier-die-wij-niet-kennen",
        model="een-model",
        base_url=EINDPUNT,
        api_key=NEP,
    )
    assert isinstance(provider, OpenAICompatibleProvider)


def test_een_bestaande_naam_blijft_zijn_eigen_klasse_houden() -> None:
    """Regressie: het nieuwe pad mag de bestaande providers niet overnemen."""
    provider = ProviderFactory.create("deepseek", model="deepseek-chat", api_key=NEP)
    assert isinstance(provider, DeepSeekProvider)


# --------------------------------------------------------------------------- de naam


def test_de_gerapporteerde_naam_is_die_van_de_aanroeper() -> None:
    """`provider_name` komt in een logregel en in een veld van een API-antwoord."""
    provider = ProviderFactory.create(
        "moonshot", model="kimi", base_url="https://api.moonshot.ai/v1", api_key=NEP
    )
    assert provider.provider_name == "moonshot"


def test_de_override_wijkt_aantoonbaar_af_van_de_afleiding_uit_de_klassenaam() -> None:
    """Zonder override zou een aanroep naar DeepSeek als 'openaicompatible' in het log staan.

    Dit toetst het VERSCHIL met de basisklasse in plaats van de uitkomst opnieuw op te
    schrijven. Een assertie als `"openaicompatible" not in naam` kan per constructie niet rood
    worden zodra de verwachte waarde er al naast staat -- dat is bij de Gate 2-review betrapt.
    """
    provider = _provider()
    afleiding_uit_klassenaam = LLMProvider.provider_name.fget(provider)  # type: ignore[attr-defined]

    assert afleiding_uit_klassenaam == "openaicompatible"
    assert provider.provider_name != afleiding_uit_klassenaam


def test_zonder_label_valt_de_naam_terug_op_de_host() -> None:
    assert _provider().provider_name == "voorbeeld.test"


def test_een_regeleinde_in_het_label_kan_geen_tweede_logregel_vervalsen() -> None:
    """De naam gaat naar een logregel; een `\\n` erin maakt een verzonnen tweede regel."""
    naam = _provider(
        extra_params={"provider_label": "deepseek\nWAARSCHUWING vervalst"}
    ).provider_name

    assert "\n" not in naam
    assert " " not in naam


def test_een_lang_label_wordt_afgekapt() -> None:
    """De grens bestaat om een logregel niet te laten volstromen.

    Zonder deze test verdwijnt de afkapping ongemerkt bij de eerste herschrijving -- precies
    het soort regel dat stil sneuvelt. Gemeld bij Gate 2, ronde 2.
    """
    naam = _provider(extra_params={"provider_label": "a" * 50}).provider_name

    assert len(naam) == 32


def test_inloggegevens_in_het_adres_worden_geweigerd() -> None:
    """Anders staat het wachtwoord in het log zodra de aanroep faalt.

    `_translate` logt met `exc_info=True`, en de foutmelding van httpx draagt de VOLLEDIGE
    url. Gemeten bij Gate 2, ronde 2: `https://gebruiker:geheimpje@host/v1` zette het
    wachtwoord in de traceback.
    """
    with pytest.raises(ValueError, match="inloggegevens"):
        _provider(base_url="https://gebruiker:" + NEP_LANG + "@voorbeeld.test/v1")


@pytest.mark.parametrize(
    "adres",
    [
        "https://voorbeeld.test/v1?key=" + NEP_LANG,
        "https://voorbeeld.test/v1#" + NEP_LANG,
    ],
)
def test_een_query_of_fragment_in_het_adres_wordt_geweigerd(adres: str) -> None:
    """Twee gevolgen tegelijk, allebei gemeten bij Gate 2, ronde 3.

    Een sleutel in de query belandt via `exc_info=True` in het log, EN het adres wordt stil
    verkeerd: `/chat/completions` komt dan achter de query te staan, dus het pad blijft `/v1`
    en het eindpunt krijgt onzin binnen.
    """
    with pytest.raises(ValueError, match="query of fragment"):
        _provider(base_url=adres)


def test_een_label_zonder_bruikbare_tekens_valt_terug_op_de_host() -> None:
    assert _provider(extra_params={"provider_label": "!!!"}).provider_name == "voorbeeld.test"


# --------------------------------------------------------------------------- configuratie


def test_zonder_adres_weigert_de_provider_dienst() -> None:
    """Er staat met opzet geen standaardadres in de code."""
    with pytest.raises(ValueError, match="base_url"):
        _provider(base_url=None)


def test_zonder_model_weigert_de_provider_dienst() -> None:
    with pytest.raises(ValueError, match="model"):
        _provider(model="")


@pytest.mark.parametrize(
    "adres",
    ["file:///etc/passwd", "javascript:iets", "169.254.169.254", "ftp://ergens/v1", "/v1"],
)
def test_alleen_http_en_https_worden_geaccepteerd(adres: str) -> None:
    """Zonder deze eis gaat de sleutel als bearer naar een ongetoetste bestemming."""
    with pytest.raises(ValueError, match="schema"):
        _provider(base_url=adres)


def test_een_lokaal_adres_blijft_toegestaan() -> None:
    """Het lokale model is de bodem van de keten; dat mag deze controle niet slopen."""
    provider = _provider(base_url="http://127.0.0.1:11434/v1")
    assert provider._chat_url.startswith("http://127.0.0.1:11434/v1")


def test_een_afsluitende_schuine_streep_verdubbelt_niet_in_het_pad() -> None:
    assert _provider(base_url=EINDPUNT + "/")._chat_url == EINDPUNT + "/chat/completions"


def test_zonder_sleutel_gaat_er_geen_authorization_kop_mee() -> None:
    """Een lokaal eindpunt heeft geen sleutel; een verzonnen placeholder is erger."""
    assert "Authorization" not in _provider(api_key=None)._headers()


def test_met_sleutel_gaat_de_kop_wel_mee() -> None:
    assert _provider()._headers()["Authorization"] == "Bearer " + NEP


# --------------------------------------------------------------------------- het antwoord


@pytest.mark.asyncio
async def test_een_geldig_antwoord_wordt_uitgelezen() -> None:
    provider = _met_antwoord(
        _provider(),
        _antwoord(
            choices=[{"message": {"content": "hallo"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            model="een-model",
        ),
    )
    antwoord = await provider.generate([LLMMessage(role="user", content="hoi")])

    assert antwoord.content == "hallo"
    assert antwoord.total_tokens == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("naam", "lichaam"),
    [
        ("geen choices", {"iets": "anders"}),
        ("lege choices", {"choices": []}),
        ("content is null", {"choices": [{"message": {"content": None}}]}),
        ("content is leeg", {"choices": [{"message": {"content": "   "}}]}),
        ("bericht ontbreekt", {"choices": [{"finish_reason": "stop"}]}),
    ],
)
async def test_een_antwoord_buiten_het_protocol_is_een_fout_en_geen_leeg_succes(
    naam: str, lichaam: dict[str, object]
) -> None:
    """Anders bouwt de agent verder op niets -- de faalvorm waar ADR-036 over gaat.

    `content: null` is geen exotisch geval: elk OpenAI-compatibel eindpunt zet dat veld op null
    bij een tool_calls-antwoord of een weigering.
    """
    provider = _met_antwoord(_provider(), _antwoord(**lichaam))
    with pytest.raises(LLMServiceError) as fout:
        await provider.generate([LLMMessage(role="user", content="hoi")])

    # Exact dit type: een vertaalde transportfout (timeout, 401) is ook een LLMServiceError,
    # dus zonder deze regel zou de test ook groen blijven als het antwoord nooit werd gelezen.
    assert type(fout.value) is LLMServiceError


@pytest.mark.asyncio
async def test_een_geweigerde_inhoud_is_een_EIGEN_fout_en_geen_storing() -> None:
    """Een weigering mag de failoverketen NIET in.

    Deze klasse is het enige providertype dat een klantrij kan opleveren, en tot 2026-09-24
    gooide hij `LLMContentFilterError` nergens. `FailoverProvider` beloofde in zijn docstring
    dat een inhoudsweigering niet doorvalt -- die belofte hing volledig aan een fout die niet
    bestond. Zonder deze test is die belofte weer leeg zodra iemand de controle weghaalt.

    Wat er zonder de controle gebeurt, gemeten: de weigering komt binnen als `content: null`,
    valt in de generieke `LLMServiceError` hieronder, en gaat als gewone storing naar
    leverancier 2 en 3 -- dezelfde tekst tot er een ja zegt. En hij telt als storing op de
    breaker van een kerngezond eindpunt.
    """
    provider = _met_antwoord(
        _provider(),
        _antwoord(choices=[{"message": {"content": None}, "finish_reason": "content_filter"}]),
    )
    with pytest.raises(LLMContentFilterError):
        await provider.generate([LLMMessage(role="user", content="hoi")])


@pytest.mark.asyncio
async def test_een_ANDERE_reden_met_lege_inhoud_blijft_een_gewone_storing() -> None:
    """De tegenrichting: de controle kijkt naar de REDEN, niet naar de aanwezigheid ervan.

    Zonder deze helft is "elke finish_reason met lege inhoud is een inhoudsweigering" een
    geldige implementatie, en dan valt een afgekapt antwoord (`length`) niet meer door naar de
    volgende schakel terwijl dat juist wel hoort.
    """
    provider = _met_antwoord(
        _provider(),
        _antwoord(choices=[{"message": {"content": None}, "finish_reason": "length"}]),
    )
    with pytest.raises(LLMServiceError) as fout:
        await provider.generate([LLMMessage(role="user", content="hoi")])

    assert not isinstance(fout.value, LLMContentFilterError)


@pytest.mark.asyncio
@pytest.mark.parametrize("gebruik", ["kapot", None, {"total_tokens": None}, 42])
async def test_een_onbruikbaar_usage_veld_laat_geen_ongevangen_fout_ontsnappen(
    gebruik: object,
) -> None:
    """De basisklasse belooft dat alles als LLMServiceError-familie naar buiten komt.

    Gemeten voor de reparatie: `usage` als tekst gaf een ONGEVANGEN AttributeError, omdat het
    uitlezen van de tokenvelden buiten het try-blok stond.
    """
    provider = _met_antwoord(
        _provider(),
        _antwoord(choices=[{"message": {"content": "ok"}}], usage=gebruik),
    )
    antwoord = await provider.generate([LLMMessage(role="user", content="hoi")])

    assert antwoord.content == "ok"
    assert antwoord.total_tokens == 0


# --------------------------------------------------------------------------- de payload


def _opgevangen_payload(provider: OpenAICompatibleProvider) -> dict[str, object]:
    """Vang het verzoek op dat werkelijk de deur uit gaat."""
    gezien: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        gezien.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _met_antwoord(provider, handler)
    asyncio.run(provider.generate([LLMMessage(role="user", content="x")]))
    return gezien


def test_een_eigen_veld_van_de_aanroeper_gaat_mee_naar_het_eindpunt() -> None:
    """Zonder dit is "werkt met elk OpenAI-compatibel eindpunt" onwaar, en wel stil.

    OpenAI heeft `max_tokens` afgeschaft; de redeneermodellen weigeren hem en eisen
    `max_completion_tokens`. Gemeten voor de reparatie: dat veld werd weggegooid en er ging
    alsnog `max_tokens: 1000` de deur uit.
    """
    payload = _opgevangen_payload(_provider(extra_params={"max_completion_tokens": 100}))

    assert payload["max_completion_tokens"] == 100


def test_een_veld_op_None_verwijdert_het_uit_de_payload() -> None:
    """Nodig omdat `max_tokens` en `max_completion_tokens` samen een weigering opleveren."""
    payload = _opgevangen_payload(
        _provider(extra_params={"max_completion_tokens": 100, "max_tokens": None})
    )

    assert "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 100


def test_het_label_lekt_niet_in_de_payload() -> None:
    """`provider_label` is onze administratie, geen veld voor de leverancier."""
    payload = _opgevangen_payload(_provider(extra_params={"provider_label": "moonshot"}))

    assert "provider_label" not in payload


@pytest.mark.parametrize("sleutel", ["messages", "stream"])
def test_de_vorm_van_het_verzoek_is_niet_te_overschrijven(sleutel: str) -> None:
    """Dat zijn geen instellingen maar de structuur; overschrijven breekt de aanroep."""
    payload = _opgevangen_payload(_provider(extra_params={sleutel: "onzin"}))

    assert payload.get(sleutel) != "onzin"


# --------------------------------------------------------------------------- foutvertaling


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "verwacht"),
    [
        (401, LLMAuthenticationError),
        (403, LLMAuthenticationError),
        (429, LLMRateLimitError),
        (500, LLMServiceError),
    ],
)
async def test_een_http_fout_wordt_het_juiste_fouttype(
    code: int, verwacht: type[Exception]
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text="kapot")

    provider = _met_antwoord(_provider(), handler)
    with pytest.raises(verwacht) as fout:
        await provider.generate([LLMMessage(role="user", content="hoi")])

    # Het EXACTE type, niet alleen "een familielid". `LLMAuthenticationError` is een subklasse
    # van `LLMServiceError`, dus zonder deze regel blijft de rij voor 500 groen als de
    # vertaling daar per ongeluk een authenticatiefout van maakt. Gemeld bij Gate 2, ronde 2.
    assert type(fout.value) is verwacht


@pytest.mark.asyncio
async def test_een_tijdsoverschrijding_wordt_een_timeoutfout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("te traag")

    provider = _met_antwoord(_provider(), handler)
    with pytest.raises(LLMTimeoutError):
        await provider.generate([LLMMessage(role="user", content="hoi")])


@pytest.mark.asyncio
async def test_de_sleutel_komt_niet_in_een_foutmelding_terecht() -> None:
    """Foutmeldingen belanden in logs en in de LLM-context; een sleutel hoort daar nooit."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="kapot")

    provider = _met_antwoord(_provider(api_key=NEP_LANG), handler)
    with pytest.raises(LLMServiceError) as fout:
        await provider.generate([LLMMessage(role="user", content="hoi")])

    assert NEP_LANG not in str(fout.value)
    assert "500" in str(fout.value)


# --------------------------------------------------------------------------- de stroom


def _sse(*regels: str) -> object:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="".join(regel + "\n\n" for regel in regels))

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("naam", "regels"),
    [
        ("met spatie", ['data: {"choices":[{"delta":{"content":"hallo"}}]}', "data: [DONE]"]),
        ("zonder spatie", ['data:{"choices":[{"delta":{"content":"hallo"}}]}', "data:[DONE]"]),
    ],
)
async def test_de_stroom_leest_beide_schrijfwijzen_van_het_scheidingsteken(
    naam: str, regels: list[str]
) -> None:
    """De SSE-specificatie staat `data:` zonder spatie toe en meerdere servers sturen het zo.

    Gemeten voor de reparatie: zo'n stroom leverde een LEGE lijst op, zonder fout en zonder
    log. In een laag die per definitie met onbekende servers praat is dat het hoofdgeval.
    """
    provider = _met_antwoord(_provider(), _sse(*regels))
    brokken = [deel async for deel in provider.stream([LLMMessage(role="user", content="x")])]

    assert brokken == ["hallo"]


@pytest.mark.asyncio
async def test_de_stroom_slaat_onleesbare_brokken_over_en_stopt_bij_done() -> None:
    provider = _met_antwoord(
        _provider(),
        _sse(
            "data: geen-json",
            'data: {"choices":[{"delta":{"content":"een"}}]}',
            "data: [DONE]",
            'data: {"choices":[{"delta":{"content":"komt-nooit"}}]}',
        ),
    )
    brokken = [deel async for deel in provider.stream([LLMMessage(role="user", content="x")])]

    assert brokken == ["een"]


@pytest.mark.asyncio
async def test_een_fout_tijdens_de_stroom_wordt_ook_vertaald() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rustig aan")

    provider = _met_antwoord(_provider(), handler)
    with pytest.raises(LLMRateLimitError):
        async for _ in provider.stream([LLMMessage(role="user", content="x")]):
            pass
