"""De pauzeerknop voor agents mag geen succes melden dat hij niet levert (ADR-036, golf 1 WS1).

**De bevinding, gemeten 2026-08-31.** `POST /api/v1/agents/{agent_id}/pause` schreef een logregel
en retourneerde `{"status": "success", "message": "Agent X paused"}`. Er werd geen agent, geen
wachtrij en geen circuit breaker aangeraakt. Hetzelfde gold voor `resume` en `restart`. Een
toezichtsknop die altijd slaagt en nooit werkt is misleidender dan geen knop: een operator die een
ontsporende agent stilzet krijgt een groene bevestiging terwijl de agent doorloopt.

**Waarom de fix een 501 is en niet een echte pauze.** Het enige bestaande per-(tenant, agent)
mechanisme is `AgentCircuitBreaker` (`als/infrastructure/agent_circuit_breaker.py`, sleutel
`circuit:{tenant_id}:{agent_id}`). Die is als operator-hold ONBRUIKBAAR, om twee gemeten redenen:

1. Openen kan alleen via de private `_open_circuit()`, en die zet `last_failure_time = now`.
   `allow()` (:86-93) draait een OPEN circuit daarna zelf naar HALF_OPEN zodra
   `reset_timeout_seconds` verstreken is. Die default van 30 seconden staat op TWEE plekken en
   `agent_runner.py:39` is geen van beide: de breker zelf zet hem
   (`agent_circuit_breaker.py:31`), de runner heeft zijn eigen default die hem doorgeeft
   (`agent_runner.py:18`, `circuit_reset_timeout: int = 30`), en regel 39 is alleen de
   doorgeefplek. Een
   "pauze" via de breker zou dus na een halve minuut stil vervallen. Dat is een tweede stille
   leugen in plaats van de eerste.
2. De breker wordt op precies een plek geraadpleegd (`agent_runner.py:82`, de pacemaker-loop). Hij
   is een faalteller met auto-herstel, geen hold.

Daarbij hebben de endpoints geen `tenant_id`, geen redis-pool en geen agent-registry om `agent_id`
tegen te resolven (`get_agents_status` levert drie hardgecodeerde agents). Een echte pauze vereist
dus een NIEUW, duurzaam hold-mechanisme. Tot dat ontworpen is, is fail-loud het eerlijke antwoord
(dezelfde afweging als OP-74: liever expliciet weigeren dan stil doen alsof).

**Beide modules staan in de parametrisatie, want ze zijn beide bereikbaar.** De GESERVEERDE
handler is `v1/management/agents_router.py` (`src.main` -> `router_registry.register_all_routers`
-> `registries/auth_admin.py:50`). `management_endpoints.py` wordt gemount door
`api/setup/router_registry.py:374` via `api/main.py:160` -- een tweede app-object dat onder TESTING
tot een no-op is gestubd, maar in een `uvicorn src.core.api.main:app`-start wel de oude handlers
serveert. Zolang die mount bestaat, moet de leugen op BEIDE plekken weg.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

import pytest
from fastapi import HTTPException

#: De drie besturingsknoppen, per module. Beide modules bevatten alle drie -- dus negen
#: mutatiepunten, niet drie. De guard in
#: `tests/architecture/test_agent_control_endpoints_do_not_fake_success.py` itereert over dezelfde
#: verzameling.
CONTROL_HANDLERS = [
    ("src.core.api.v1.management.agents_router", "pause_agent"),
    ("src.core.api.v1.management.agents_router", "resume_agent"),
    ("src.core.api.v1.management.agents_router", "restart_agent"),
    ("src.core.api.management_endpoints", "pause_agent"),
    ("src.core.api.management_endpoints", "resume_agent"),
    ("src.core.api.management_endpoints", "restart_agent"),
]

_AGENT_ID = "cva_main"


class _FakeUser:
    id = 42
    email = "operator@example.com"


def _load_handler(module_name: str, handler_name: str) -> Any:
    from importlib import import_module

    return getattr(import_module(module_name), handler_name)


async def _call(handler: Any) -> Any:
    """Roep de handler rechtstreeks aan met de dependency-waarden die FastAPI zou injecteren."""
    return await handler(_AGENT_ID, current_user=_FakeUser(), _=0)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(("module_name", "handler_name"), CONTROL_HANDLERS)
async def test_control_endpoint_refuses_instead_of_reporting_unbacked_success(
    module_name: str, handler_name: str
) -> None:
    """De knop MOET weigeren zolang hij niets kan stilzetten -- niet 'success' melden.

    Dit is de poort op de fix. ROOD voor de fix (de handler retourneerde 200 met
    `status="success"`), GROEN erna (501 NOT_IMPLEMENTED).
    """
    handler = _load_handler(module_name, handler_name)

    with pytest.raises(HTTPException) as excinfo:
        await _call(handler)

    assert excinfo.value.status_code == 501, (
        f"{module_name}.{handler_name} antwoordt met status {excinfo.value.status_code} in plaats "
        "van 501. Deze endpoint raakt geen agent, geen wachtrij en geen circuit breaker aan; elk "
        "ander antwoord dan een expliciete weigering is een bevestiging die niet gedekt is."
    )


@pytest.mark.unit
@pytest.mark.parametrize(("module_name", "handler_name"), CONTROL_HANDLERS)
def test_control_endpoint_leaves_the_circuit_breaker_untouched(
    module_name: str, handler_name: str
) -> None:
    """Karakterisering, GEEN bewijs: de handler raakt geen per-agent mechanisme aan.

    Twee Gate 2-rondes van 2026-08-31 hebben deze test uitgekleed, en wat eruit ging is
    leerzamer dan wat erin bleef.

    Ronde 1 haalde de assertie `client.hashes == {}` op een nagemaakte redis-client weg: die
    KAN niet falen, want de handler heeft geen referentie naar die client, die pool of die
    breker, dus er is niets dat ernaar zou kunnen schrijven. Deze zes tests waren groen voor
    EN na de fix.

    Ronde 2 haalde vervolgens de VERVANGING weg, die dezelfde fout in nettere kleren was: een
    echte `AgentCircuitBreaker` opbouwen, `get_state()` voor en na de aanroep vergelijken, en
    beide keren CLOSED meten. Ook dat kan niet falen, om precies dezelfde reden. Een docstring
    die eerlijk opschrijft dat een assertie niets bewijst, maakt hem niet nuttig -- hij hoort
    weg. Wat overblijft is de structurele toets hieronder, en die is dan ook de enige inhoud.

    Wat hier WEL kan falen: zodra iemand een echt hold-mechanisme in de handler draadt, wordt
    deze test rood en MOET hij herschreven worden om dat mechanisme te toetsen -- in plaats van
    stil te blijven slagen terwijl hij niets meer beschrijft.

    Het eigenlijke bewijs van de bevinding staat in
    `test_control_endpoint_refuses_instead_of_reporting_unbacked_success`, dat hard op een
    HTTPException asserteert en pre-fix aantoonbaar rood was (9 failed / 9 passed op dit bestand).
    """
    handler = _load_handler(module_name, handler_name)

    # Deze toets KAN rood worden, in tegenstelling tot de twee weggehaalde asserties: hij leest
    # de daadwerkelijke body van de handler in plaats van een losstaande dubbel.
    #
    # STRUCTUUR en niet tekst, en dat is hier gemeten en niet bedacht: een eerste versie deed
    # `"hold" in inspect.getsource(handler).lower()` en werd rood op alle zes handlers -- niet door
    # de code maar door het woord "hold-mechanisme" in de `responses`-beschrijving van de
    # decorator. Precies de valkuil die
    # tests/architecture/test_agent_control_endpoints_do_not_fake_success.py documenteert. Daarom:
    # decorators eraf, docstring eraf, en alleen NAMEN uit de body -- geen tekenreeksen.
    fn = ast.parse(textwrap.dedent(inspect.getsource(handler))).body[0]
    assert isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
    lichaam = fn.body
    if (
        lichaam
        and isinstance(lichaam[0], ast.Expr)
        and isinstance(lichaam[0].value, ast.Constant)
        and isinstance(lichaam[0].value.value, str)
    ):
        lichaam = lichaam[1:]  # docstring telt niet mee
    verwijzingen: set[str] = set()
    for stmt in lichaam:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name):
                verwijzingen.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                verwijzingen.add(node.attr.lower())
    # TOKENS vergelijken, geen substrings. Substring-matching gaf gemeten valse positieven:
    # `"hold" in "threshold"` is waar, en `"queue" in "dequeue"` ook. Een toekomstige handler met
    # een lokale `threshold` zou dan falen met de melding "er is een echt mechanisme
    # bijgekomen" -- en een regel met valse positieven wordt uitgezet in plaats van gevolgd.
    # Gevonden door de onafhankelijke Gate 2 van 2026-08-31, in precies de test die in de regels
    # hierboven afzweert dat je tekst matcht waar structuur telt.
    tokens = {deel for verwijzing in verwijzingen for deel in verwijzing.split("_") if deel}
    aanwijzingen = sorted(
        {"pause_store"} & verwijzingen
        | {naam for naam in ("circuit", "breaker", "redis", "hold", "queue") if naam in tokens}
    )
    assert not aanwijzingen, (
        f"{module_name}.{handler_name} verwijst nu naar {aanwijzingen} -- er is dus een echt "
        "mechanisme bijgekomen. Deze test KARAKTERISEERT de afwezigheid daarvan en beschrijft de "
        "code niet meer. Herschrijf hem zodat hij het nieuwe mechanisme toetst (en werk "
        "tests/architecture/test_agent_control_endpoints_do_not_fake_success.py bij)."
    )


@pytest.mark.unit
@pytest.mark.parametrize("action", ["pause", "resume", "restart"])
def test_the_control_route_is_still_served(action: str) -> None:
    """Weigeren mag geen wegnemen worden: een 404 is hier net zo misleidend als een vals succes.

    De operator moet TE HOREN krijgen dat de functie niet bestaat. Een verdwenen route laat een
    frontend-knop stil op een generieke fout lopen.
    """
    from src.main import create_test_app

    path_template = "/api/v1/agents/{agent_id}/" + action
    served = {getattr(route, "path", None) for route in create_test_app().routes}

    assert path_template in served, (
        f"{path_template} wordt niet meer geserveerd. De fix hoort de route te BEHOUDEN en 501 te "
        "antwoorden, niet de route te verwijderen."
    )


@pytest.mark.unit
@pytest.mark.parametrize("action", ["pause", "resume", "restart"])
def test_the_refusal_reaches_the_client_as_501(action: str) -> None:
    """De 501 moet door de ASGI-stack heen komen, MET de echte exception-handlers erop.

    Bewust op een app met alleen de echte router en niet de volledige app: die zet een
    authenticatie-middleware voor de dependencies (gemeten: 401 voordat een override wordt
    bereikt), en die muur is niet wat deze test wil meten.

    Wel MET `register_exception_handlers`, en dat is een correctie na Gate 2 (2026-08-31). De
    eerste versie bouwde een kale `FastAPI()` zonder handlers en asserteerde
    `ERROR_CODE in response.text`. Die twee samen maakten de test blind voor wat hij beweerde te
    meten: het platform herschrijft de body (`src/core/exceptions/handlers.py:72-82` stopt het
    dict-detail in `error.message`), en een substring-toets slaagt in beide vormen -- en ook
    wanneer de code in een stacktrace of een ander veld opduikt. Nu wordt op het JSON-PAD
    getoetst, zodat de test faalt als de vorm verandert.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.core.api.agent_control_unavailable import ERROR_CODE
    from src.core.api.v1.management.agents_router import router
    from src.core.exceptions.handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    path_template = "/api/v1/agents/{agent_id}/" + action
    route = next(r for r in app.routes if getattr(r, "path", None) == path_template)
    for sub in route.dependant.dependencies:
        call = sub.call
        if call is None:
            continue
        if "current_user" in getattr(call, "__name__", ""):
            app.dependency_overrides[call] = lambda: _FakeUser()
        else:
            app.dependency_overrides[call] = lambda: 0

    with TestClient(app) as client:
        response = client.post(f"/api/v1/agents/{_AGENT_ID}/{action}")

    assert response.status_code == 501, (
        f"POST /api/v1/agents/{_AGENT_ID}/{action} gaf {response.status_code} "
        f"({response.text[:200]}). Verwacht 501: de knop kan niets stilzetten en moet dat zeggen."
    )
    body = response.json()
    # Het JSON-PAD, niet een substring. Gemeten met de echte handlers: het platform levert
    # `{"error": {"error_code": "HTTP_ERROR", "message": <detail>, ...}, "detail": <detail>}`,
    # dus de foutcode staat op body["detail"]["error"]["code"] en NIET op body["error"]["code"].
    assert body.get("detail", {}).get("error", {}).get("code") == ERROR_CODE, (
        "De foutcode staat niet op het verwachte JSON-pad body['detail']['error']['code']. Een "
        "operator (of een gegenereerde client) kan dan niet zien WAAROM de knop weigerde. "
        f"Antwoord was: {response.text[:300]}"
    )
