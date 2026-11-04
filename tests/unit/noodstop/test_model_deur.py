"""Bij een stilgezette klant gaat er via GEEN modelpad iets naar een taalmodel (ronde 3).

Besluit A (ronde 2) sloot de chat. Dit sluit de rest: elke client, provider en dienst die een taalmodel
aanroept controleert de stand OP HET PUNT van de aanroep. Per stapel (services/llm, llm, shared, als) een
echte subklasse van de echte basisklasse, zodat de controle van de BASIS wordt gemeten en niet van een
nagemaakt object. De losse modelpaden (fallback-keten, embeddings, leerproviders, ...) worden bij naam
aangeroepen op een kaal exemplaar: de controle moet gooien VOOR het lichaam draait.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from src.core.noodstop import guard
from src.core.noodstop.guard import KlantStilgezet

STIL, ACTIEF, STORING = 7, 8, 9


@pytest.fixture(autouse=True)
def _schone_context() -> Any:
    clear_tenant_context()
    yield
    clear_tenant_context()


@pytest.fixture
def lezer(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    gelezen: list[int] = []

    async def lees(tenant_id: int) -> bool:
        gelezen.append(tenant_id)
        if tenant_id == STORING:
            raise ConnectionError("db weg")
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lees)
    return gelezen


async def _leeg(stroom: Any) -> list[Any]:
    return [x async for x in stroom]


# --- de vier stapels: een echte subklasse van de echte basis --------------------------------------


def _stapel_b(spion: list[str]) -> list[tuple[str, Callable[[], Awaitable[object]]]]:
    from src.core.services.llm.base import LLMConfig, LLMMessage, LLMProvider

    class Prov(LLMProvider):
        def _validate_config(self) -> None:
            return None

        async def generate(self, messages, temperature=None, max_tokens=None):  # type: ignore[no-untyped-def]
            spion.append("b.generate")
            return "antwoord"

        async def stream(self, messages, temperature=None, max_tokens=None):  # type: ignore[no-untyped-def]
            spion.append("b.stream")
            yield "brok"

        async def get_embeddings(self, text):  # type: ignore[no-untyped-def]
            spion.append("b.embed")
            return [0.1]

    p = Prov(LLMConfig(model="m"))
    msgs = [LLMMessage(role="user", content="klantgegevens")]
    return [
        ("b.generate", lambda: p.generate(msgs)),
        ("b.stream", lambda: _leeg(p.stream(msgs))),
        ("b.embed", lambda: p.get_embeddings("klantgegevens")),
    ]


def _stapel_a(spion: list[str]) -> list[tuple[str, Callable[[], Awaitable[object]]]]:
    from src.core.llm.llm_client import LLMClient

    class Client(LLMClient):
        def __init__(self) -> None:  # geen config nodig: alleen de aanroepen tellen
            return None

        async def chat_completion(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            spion.append("a.chat")
            return "x"

        async def text_completion(self, prompt, **kwargs):  # type: ignore[no-untyped-def]
            spion.append("a.text")
            return "x"

    c = Client()
    c._gdpr_enforcer = SimpleNamespace(  # type: ignore[attr-defined]
        redact_pii=lambda tekst: (tekst, {}), detokenize=lambda tekst, kaart: tekst
    )
    return [
        ("a.chat", lambda: c.chat_completion([])),
        ("a.text", lambda: c.text_completion("klantgegevens")),
        ("a.generate_response", lambda: c.generate_response("klantgegevens")),
    ]


def _stapel_shared(spion: list[str]) -> list[tuple[str, Callable[[], Awaitable[object]]]]:
    from src.core.shared.llm_client import LLMClient

    class Client(LLMClient):
        def __init__(self) -> None:
            return None

        async def chat_completion(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            spion.append("s.chat")
            return "x"

        async def text_completion(self, prompt, **kwargs):  # type: ignore[no-untyped-def]
            spion.append("s.text")
            return "x"

    c = Client()
    return [
        ("s.chat", lambda: c.chat_completion([])),
        ("s.text", lambda: c.text_completion("klantgegevens")),
        ("s.generate_response", lambda: c.generate_response("klantgegevens")),
    ]


def _stapel_als(spion: list[str]) -> list[tuple[str, Callable[[], Awaitable[object]]]]:
    from src.core.als.llm_integration.providers import LLMProvider

    class Prov(LLMProvider):
        @property
        def name(self) -> str:
            return "x"

        async def generate(self, prompt, system_prompt=None, temperature=0.7, max_tokens=1000):  # type: ignore[no-untyped-def]
            spion.append("e.generate")
            return {"success": True}

    p = Prov()
    return [("e.generate", lambda: p.generate("klantgegevens"))]


STAPELS = [_stapel_b, _stapel_a, _stapel_shared, _stapel_als]


def _alle(spion: list[str]) -> list[tuple[str, Callable[[], Awaitable[object]]]]:
    return [x for bouw in STAPELS for x in bouw(spion)]


def _namen() -> list[str]:
    return [n for n, _ in _alle([])]


@pytest.mark.parametrize("naam", _namen())
async def test_een_stilgezette_klant_bereikt_het_model_niet(naam: str, lezer: list[int]) -> None:
    spion: list[str] = []
    aanroep = dict(_alle(spion))[naam]
    set_tenant_id(STIL)
    with pytest.raises(KlantStilgezet) as fout:
        await aanroep()
    assert not fout.value.onbekend
    assert spion == [], f"het model is toch aangeroepen: {spion}"


@pytest.mark.parametrize("naam", _namen())
async def test_een_onleesbare_stand_weigert_ook_het_model(naam: str, lezer: list[int]) -> None:
    spion: list[str] = []
    aanroep = dict(_alle(spion))[naam]
    set_tenant_id(STORING)
    with pytest.raises(KlantStilgezet) as fout:
        await aanroep()
    assert fout.value.onbekend
    assert spion == []


@pytest.mark.parametrize("naam", _namen())
async def test_een_actieve_klant_komt_langs(naam: str, lezer: list[int]) -> None:
    spion: list[str] = []
    aanroep = dict(_alle(spion))[naam]
    set_tenant_id(ACTIEF)
    await aanroep()
    assert spion, "de aanroep zelf moet doorgaan"


@pytest.mark.parametrize("naam", _namen())
async def test_zonder_klant_in_de_context_is_het_een_systeemtaak(
    naam: str, lezer: list[int]
) -> None:
    spion: list[str] = []
    aanroep = dict(_alle(spion))[naam]
    await aanroep()
    assert spion
    assert lezer == [], "zonder klant is er niets te lezen"


async def test_een_aanroep_binnen_een_aanroep_leest_de_stand_een_keer(lezer: list[int]) -> None:
    spion: list[str] = []
    aanroep = dict(_alle(spion))["a.generate_response"]
    set_tenant_id(ACTIEF)
    await aanroep()  # generate_response (bewaakt) roept text_completion (bewaakt) aan
    assert lezer == [ACTIEF]


# --- het ene taalmodel van een klant: TenantTaalmodel en LLMService.for_tenant --------------------


@pytest.mark.parametrize(
    "methode",
    [
        "tekst",
        "chat_completion",
        "generate_response",
        "complete_json",
        "async_prompt",
        # Ronde 4: de vormen die `origin/develop` (BE-LLM-007) erbij zette.
        "text_completion",
        "generate",
        "generate_with_tools",
    ],
)
async def test_tenant_taalmodel_van_een_stilgezette_klant_haalt_geen_model_op(
    methode: str, lezer: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.services.llm.service import LLMService
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    bouw = AsyncMock()
    monkeypatch.setattr(LLMService, "for_tenant", bouw)
    deur = TenantTaalmodel(STIL)  # GEEN tenant in de context: de deur kent zijn klant zelf
    functie = getattr(deur, methode)
    args: list[Any] = [[]]
    if methode in {"tekst", "generate_response", "text_completion"}:
        args = ["klantgegevens"]
    with pytest.raises(KlantStilgezet):
        await functie(*args)
    bouw.assert_not_called()


async def test_tenant_taalmodel_van_een_actieve_klant_werkt_nog(
    lezer: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.services.llm.service import LLMService
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    dienst = AsyncMock()
    dienst.generate = AsyncMock(return_value="ok")
    dienst.provider.provider_name = "mistral"
    dienst.provider.config.model = "m"
    monkeypatch.setattr(LLMService, "for_tenant", AsyncMock(return_value=dienst))
    assert await TenantTaalmodel(ACTIEF).tekst("hoi") == "ok"
    assert lezer == [ACTIEF]


async def test_tenant_suggestieprovider_van_een_stilgezette_klant_stuurt_niets_naar_het_model(
    lezer: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """De leerprovider van de tenant (BE-LLM-007) weigert hard, hij geeft geen stille lege suggestie."""
    from src.core.learning.interfaces.llm_provider import TenantSuggestionProvider
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    gebruik = AsyncMock()
    monkeypatch.setattr(TenantTaalmodel, "tekst_met_gebruik", gebruik)
    with pytest.raises(KlantStilgezet):
        await TenantSuggestionProvider(STIL).suggest({}, {})
    gebruik.assert_not_called()


async def test_llm_service_voor_een_stilgezette_klant_belt_de_provider_niet(
    lezer: list[int],
) -> None:
    from src.core.services.llm.service import LLMService

    provider = AsyncMock()
    dienst = LLMService(provider_instance=provider)
    dienst.noodstop_tenant_id = STIL
    with pytest.raises(KlantStilgezet):
        await dienst.generate([])
    provider.generate.assert_not_called()


def test_for_tenant_geeft_de_dienst_op_elk_uitgangspunt_zijn_klant_mee() -> None:
    """Elke `return` van `for_tenant` komt direct na `<dienst>.noodstop_tenant_id = tenant_id`."""
    import ast
    import textwrap

    from src.core.services.llm.service import LLMService

    bron = textwrap.dedent(inspect.getsource(LLMService.for_tenant.__func__))  # type: ignore[attr-defined]
    functie = ast.parse(bron).body[0]
    assert isinstance(functie, ast.AsyncFunctionDef)
    returns = 0
    for knoop in ast.walk(functie):
        for lijst in (getattr(knoop, "body", None), getattr(knoop, "orelse", None)):
            if not isinstance(lijst, list):
                continue
            for i, stmt in enumerate(lijst):
                if not isinstance(stmt, ast.Return):
                    continue
                returns += 1
                assert isinstance(stmt.value, ast.Name), "for_tenant geeft een naam terug"
                vorige = lijst[i - 1] if i else None
                assert (
                    isinstance(vorige, ast.Assign)
                    and isinstance(vorige.targets[0], ast.Attribute)
                    and vorige.targets[0].attr == "noodstop_tenant_id"
                    and isinstance(vorige.targets[0].value, ast.Name)
                    and vorige.targets[0].value.id == stmt.value.id
                ), "elke uitgang van for_tenant zet eerst noodstop_tenant_id"
    assert returns >= 2


# --- de poort en haar adapter -------------------------------------------------------------------


def test_het_laden_van_de_adapter_meldt_de_controle_aan() -> None:
    """Het opstartpunt importeert de adapter; die registreert de echte controle en de tenantcontext."""
    from src.core.noodstop import model_deur as adapter
    from src.core.shared import model_deur as poort

    assert poort._adapter() == (adapter.eis_model_actief, adapter._klant_uit_context)


async def test_zonder_aangemelde_adapter_blijft_de_deur_dicht(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Geen registratie: de poort laadt niets zelf en weigert (fail-closed), ook zonder klant."""
    from src.core.shared import model_deur as poort

    monkeypatch.setattr(poort, "_controleur", None)
    monkeypatch.setattr(poort, "_klantlezer", None)
    aangeroepen: list[int] = []

    @poort.bewaakt_model_aanroep
    async def model(self: object) -> None:
        aangeroepen.append(1)

    with pytest.raises(poort.ModelDeurNietBeschikbaar):
        await model(object())
    assert aangeroepen == []


# --- de losse modelpaden: bij naam, op een kaal exemplaar --------------------------------------

LOSSE_PADEN = [
    ("src.core.llm.fallback_chain", "LLMFallbackChain", "generate"),
    ("src.core.knowledge.embedding_service", "EmbeddingService", "generate_embedding"),
    ("src.core.knowledge.embedding_service", "EmbeddingService", "generate_embeddings_batch"),
    ("src.core.learning.interfaces.llm_provider", "GeminiSuggestionProvider", "suggest"),
    ("src.core.learning.interfaces.llm_provider", "ClaudeSuggestionProvider", "suggest"),
    ("src.core.learning.interfaces.llm_provider", "LocalSuggestionProvider", "suggest"),
    ("src.core.llm.local_provider", "LocalLLMProvider", "generate_response"),
    ("src.core.llm.ollama_client", "RobustOllamaClient", "chat"),
    ("src.core.llm.ollama_client", "RobustOllamaClient", "embed"),
    ("src.core.agents.router_agent_service", "RouterAgentService", "route_request"),
    ("src.core.agents.router_agent_service", "RouterAgentService", "execute_request"),
    ("src.core.llm.llm_service", "LLMService", "generate_response"),
    ("src.core.llm.llm_service", "LLMService", "complete_json"),
    ("src.core.llm.llm_service", "LLMService", "generate_with_tools"),
    ("src.core.llm.llm_config", "GuaranteedLLMService", "generate_response"),
    ("src.core.strategy.llm_client", "StrategyLLMClient", "generate_response"),
    ("src.core.workflow.providers", "ProductionLLMProvider", "generate"),
]


@pytest.mark.parametrize(("module", "klasse", "methode"), LOSSE_PADEN)
async def test_een_los_modelpad_gooit_voor_het_lichaam_draait(
    module: str, klasse: str, methode: str, lezer: list[int]
) -> None:
    cls = getattr(importlib.import_module(module), klasse)
    kaal = object.__new__(cls)
    functie = getattr(kaal, methode)
    verplicht = [
        "klantgegevens"
        for p in inspect.signature(functie).parameters.values()
        if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    set_tenant_id(STIL)
    with pytest.raises(KlantStilgezet):
        resultaat = functie(*verplicht)
        if inspect.isasyncgen(resultaat):
            await _leeg(resultaat)
        else:
            await resultaat
