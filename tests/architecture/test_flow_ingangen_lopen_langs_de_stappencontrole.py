"""Elke ingang die een ActivePieces-flow opslaat, publiceert, aanzet of uitvoert loopt langs de
rolcontrole `workflows:publish` en langs de stappencontrole (wfb-dag1 stap 1).

Waarom: een AP-flow voert zijn stappen zelf uit, buiten de ToolBroker en de HITL om
(docs/workflowbuilder-debiteuren.md). Tot er per `piece.actie` een risicoregel bestaat (ADR-040
B12) mag een flow alleen stappen zonder gevolg naar buiten hebben. Deze guard bewaakt de twee
plekken waar dat hangt:

1. ROUTES. Elke schrijvende route in de flowrouters staat in FLOW_SCHRIJFROUTES en heeft een
   `require_resource_permission("workflows", "publish")` in zijn dependencies (gelezen uit de
   closure, want elke rolcontrole heet `permission_checker`). Een NIEUWE schrijvende route in die
   routers zonder vermelding maakt de guard rood. Gemeten op de echte app (`create_test_app()`).
2. UITGANG. `ActivePiecesClient.create_flow`, `update_flow`, `trigger_flow` en `retry_run`
   roepen `controleer_flowdefinitie` aan, en nergens anders in `src/` wordt met `_make_request`
   naar een `/flows`-pad geschreven of een run herhaald (`/flow-runs/.../retry`, Gate 2 HIGH-1). Zo loopt elke route -- ook een toekomstige -- die een flow naar AP
   stuurt, via de controle.

3. WEBSOCKETS en 4. PROXY: zie het blok onderaan (bevindingen A en B).

Wat dit NIET bewaakt: eigen HTTP-code buiten `_make_request` die AP aanroept (de focus-builder-
proxy in remote-modus stuurt naar een aparte dienst, niet naar AP); en dat de diensten de controle
VOOR het lokaal opslaan doen -- dat meten de route- en integratietests.

Sleutel is `module::functie` (zie quality-gates.md, aanscherping OP-258).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

REPO = Path(__file__).resolve().parents[2]

FLOWROUTER_MODULES: frozenset[str] = frozenset(
    {
        "src.core.api.v1.activepieces.flows_router",
        "src.core.api.v1.activepieces.execution_router",
        "src.core.api.v1.focus_builder.flows_router",
        "src.core.api.v1.focus_builder.execution_router",
        "src.core.api.v1.workflow.workflow_execution_ap_router",
    }
)

FLOW_SCHRIJFROUTES: frozenset[str] = frozenset(
    {
        "src.core.api.v1.activepieces.flows_router::create_flow",
        "src.core.api.v1.activepieces.flows_router::update_flow",
        "src.core.api.v1.activepieces.flows_router::delete_flow",
        "src.core.api.v1.activepieces.flows_router::toggle_flow",
        "src.core.api.v1.activepieces.execution_router::execute_flow",
        "src.core.api.v1.activepieces.execution_router::retry_flow_run",
        "src.core.api.v1.activepieces.execution_router::cancel_flow_run",
        "src.core.api.v1.focus_builder.flows_router::create_flow",
        "src.core.api.v1.focus_builder.flows_router::update_flow",
        "src.core.api.v1.focus_builder.flows_router::delete_flow",
        "src.core.api.v1.focus_builder.execution_router::execute_flow",
        "src.core.api.v1.workflow.workflow_execution_ap_router::execute_workflow",
    }
)

KNOWN_SCHRIJVEND_ZONDER_PUBLICATIERECHT: dict[str, str] = {
    "src.core.api.v1.activepieces.flows_router::validate_flow_endpoint": (
        "2026-10-08: valideert alleen een definitie, slaat niets op en stuurt niets naar AP"
    ),
}

UITGANG_MET_CONTROLE: frozenset[str] = frozenset(
    {"create_flow", "update_flow", "trigger_flow", "retry_run"}
)
CLIENT = REPO / "src" / "core" / "activepieces" / "client.py"
SCHRIJVENDE_METHODEN = frozenset({"POST", "PUT", "PATCH"})


def _sleutel(call: Callable[..., Any]) -> str:
    return f"{call.__module__}::{call.__name__}"


def _dependencies(dependant: Any) -> Iterator[Callable[..., Any]]:
    for sub in getattr(dependant, "dependencies", None) or []:
        if sub.call is not None:
            yield sub.call
        yield from _dependencies(sub)


def vraagt_publicatierecht(dependant: Any) -> bool:
    """True als een dependency `require_resource_permission("workflows", "publish")` is."""
    for call in _dependencies(dependant):
        if getattr(call, "__name__", "") != "permission_checker":
            continue
        vrij = inspect.getclosurevars(call).nonlocals
        if (vrij.get("resource"), vrij.get("action")) == ("workflows", "publish"):
            return True
    return False


@lru_cache(maxsize=1)
def _schrijvende_flowroutes() -> dict[str, list[Any]]:
    """endpoint-sleutel -> dependants, voor elke schrijvende route in de flowrouters."""
    from src.main import create_test_app

    gevonden: dict[str, list[Any]] = {}
    for route in create_test_app().routes:
        if not isinstance(route, APIRoute) or route.endpoint.__module__ not in FLOWROUTER_MODULES:
            continue
        if not (route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        gevonden.setdefault(_sleutel(route.endpoint), []).append(route.dependant)
    return gevonden


def test_de_flowroutes_worden_gevonden() -> None:
    """Vangnet: een lege enumeratie maakt de rest vacuous groen."""
    assert len(_schrijvende_flowroutes()) >= len(FLOW_SCHRIJFROUTES)


def test_elke_schrijvende_flowroute_vraagt_het_publicatierecht() -> None:
    zonder = sorted(
        sleutel
        for sleutel, dependants in _schrijvende_flowroutes().items()
        if sleutel not in KNOWN_SCHRIJVEND_ZONDER_PUBLICATIERECHT
        and not all(vraagt_publicatierecht(d) for d in dependants)
    )
    assert not zonder, f"Schrijvende flowroutes zonder `workflows:publish`: {zonder}"


def test_er_is_geen_onbekende_schrijvende_flowroute() -> None:
    """Een nieuwe ingang moet bewust in de lijst: met recht en controle, of met een reden."""
    bekend = FLOW_SCHRIJFROUTES | set(KNOWN_SCHRIJVEND_ZONDER_PUBLICATIERECHT)
    nieuw = sorted(set(_schrijvende_flowroutes()) - bekend)
    assert not nieuw, f"Nieuwe schrijvende flowroute(s), niet in FLOW_SCHRIJFROUTES: {nieuw}"


def test_de_lijsten_zijn_niet_stale() -> None:
    gevonden = set(_schrijvende_flowroutes())
    weg = sorted((FLOW_SCHRIJFROUTES | set(KNOWN_SCHRIJVEND_ZONDER_PUBLICATIERECHT)) - gevonden)
    assert not weg, f"Lijstregels zonder route: {weg}"


def test_flowroutermodules_bestaan() -> None:
    for module in sorted(FLOWROUTER_MODULES):
        importlib.import_module(module)


def _functies(boom: ast.AST) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return {
        n.name: n for n in ast.walk(boom) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _roept_aan(functie: ast.AST, naam: str) -> bool:
    for knoop in ast.walk(functie):
        if isinstance(knoop, ast.Call):
            doel = knoop.func
            gevonden = doel.id if isinstance(doel, ast.Name) else getattr(doel, "attr", None)
            if gevonden == naam:
                return True
    return False


def test_de_uitgang_naar_ap_controleert_de_stappen() -> None:
    functies = _functies(ast.parse(CLIENT.read_text(encoding="utf-8")))
    ontbreekt = sorted(UITGANG_MET_CONTROLE - set(functies))
    zonder = sorted(
        naam
        for naam in UITGANG_MET_CONTROLE & set(functies)
        if not _roept_aan(functies[naam], "controleer_flowdefinitie")
    )
    assert not ontbreekt, f"Uitgangsmethoden bestaan niet (meer) in client.py: {ontbreekt}"
    assert not zonder, f"Uitgangsmethoden zonder controleer_flowdefinitie: {zonder}"


def schrijft_naar_flows(knoop: ast.Call) -> bool:
    """`_make_request("POST", "/flows...")` of met trefwoorden `method=` en `endpoint=`."""
    doel = knoop.func
    if getattr(doel, "attr", getattr(doel, "id", None)) != "_make_request":
        return False
    args: dict[str, ast.expr] = dict(zip(("method", "endpoint"), knoop.args))
    args.update({k.arg: k.value for k in knoop.keywords if k.arg})
    methode, pad = args.get("method"), args.get("endpoint")
    if not (isinstance(methode, ast.Constant) and methode.value in SCHRIJVENDE_METHODEN):
        return False
    if isinstance(pad, ast.Constant) and isinstance(pad.value, str):
        tekst = pad.value
    elif isinstance(pad, ast.JoinedStr):
        tekst = "".join(
            str(deel.value) if isinstance(deel, ast.Constant) else "{}" for deel in pad.values
        )
    else:
        return False
    return tekst.startswith("/flows") or (tekst.startswith("/flow-runs") and tekst.endswith("/retry"))


def _kandidaten() -> list[Path]:
    """Bestanden in src/ die `_make_request` noemen (git grep: geen repo-brede parse)."""
    uit = subprocess.run(
        ["git", "grep", "-l", "_make_request", "--", "src"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO / regel for regel in uit.stdout.splitlines() if regel.endswith(".py")]


def test_alleen_de_client_schrijft_flows_naar_ap() -> None:
    kandidaten = _kandidaten()
    assert CLIENT in kandidaten, "vangnet: git grep vond client.py niet; de scan meet niets"
    overtreders = sorted(
        f"{pad.relative_to(REPO).as_posix()}:{knoop.lineno}"
        for pad in kandidaten
        if pad != CLIENT
        for knoop in ast.walk(ast.parse(pad.read_text(encoding="utf-8")))
        if isinstance(knoop, ast.Call) and schrijft_naar_flows(knoop)
    )
    assert not overtreders, (
        "Flows naar AP schrijven buiten ActivePiecesClient om (dus zonder stappencontrole): "
        f"{overtreders}"
    )


def _call(code: str) -> ast.Call:
    knoop = ast.parse(code).body[0]
    assert isinstance(knoop, ast.Expr) and isinstance(knoop.value, ast.Call)
    return knoop.value


def test_herkenner_ziet_een_schrijfactie_naar_flows() -> None:
    zien = [
        'c._make_request("POST", f"/flows/{x}", "toggle_flow")',
        'c._make_request(method="POST", endpoint="/flows", operation_name="x")',
        'c._make_request("POST", f"/flow-runs/{x}/retry", "retry_run")',
    ]

    assert all(schrijft_naar_flows(_call(c)) for c in zien)


def test_herkenner_laat_lezen_en_stoppen_met_rust() -> None:
    niet = [
        'c._make_request("GET", f"/flows/{x}", "get_flow")',
        'c._make_request("POST", f"/flow-runs/{x}/stop", "cancel_run")',
    ]

    assert not any(schrijft_naar_flows(_call(c)) for c in niet)


# --------------------------------------------------------------------------------------------
# 3. WEBSOCKETS. Een websocket heeft geen dependency per bericht: de focus-builder-chat schreef
#    bij `accept_proposal` een flow weg zonder `workflows:publish` (bevinding A). Elke
#    websocket-handler in de flowmodules wordt hier geparsed: elk berichttype (`msg_type == "x"`)
#    waarvan de tak een flow wegschrijft of uitvoert, moet in SCHRIJVENDE_BERICHTTYPEN van die
#    module staan, en de handler moet die typen langs `mag_flows_publiceren` sturen.
# 4. PROXY. De remote-modus-proxy (focus_builder/proxy.py) staat niet in `create_test_app()`
#    (embedded modus); zijn schrijvende routes worden op `create_proxy_router()` zelf gemeten.
# --------------------------------------------------------------------------------------------

WS_FLOWMODULE_PREFIXEN: tuple[str, ...] = (
    "src.core.api.v1.focus_builder.",
    "src.core.api.v1.activepieces.",
    "src.core.api.v1.workflow.",
)
REPOSITORY_SCHRIJFMETHODEN = frozenset({"create", "update", "delete"})
FLOW_SCHRIJFAANROEPEN = frozenset(
    {"accept_proposal", "save_accepted_workflow", "execute_flow", "create_flow", "update_flow"}
)
WS_POORT = "mag_flows_publiceren"


def _aanroepnaam(knoop: ast.Call) -> str | None:
    doel = knoop.func
    return doel.id if isinstance(doel, ast.Name) else getattr(doel, "attr", None)


def tak_schrijft_een_flow(tak: list[ast.stmt]) -> bool:
    """`*.repository.create/update/delete(...)` of een bekende flow-schrijfaanroep."""
    for stmt in tak:
        for knoop in ast.walk(stmt):
            if not isinstance(knoop, ast.Call):
                continue
            doel = knoop.func
            if (
                isinstance(doel, ast.Attribute)
                and doel.attr in REPOSITORY_SCHRIJFMETHODEN
                and isinstance(doel.value, ast.Attribute)
                and doel.value.attr == "repository"
            ):
                return True
            if _aanroepnaam(knoop) in FLOW_SCHRIJFAANROEPEN:
                return True
    return False


def schrijvende_berichttypen(handler: ast.AST) -> set[str]:
    """Berichttypen uit `if msg_type == "x":`-takken die een flow wegschrijven."""
    gevonden: set[str] = set()
    for knoop in ast.walk(handler):
        if not isinstance(knoop, ast.If) or not isinstance(knoop.test, ast.Compare):
            continue
        links, rechts = knoop.test.left, knoop.test.comparators
        if not (
            isinstance(links, ast.Name)
            and links.id == "msg_type"
            and len(rechts) == 1
            and isinstance(rechts[0], ast.Constant)
            and isinstance(rechts[0].value, str)
        ):
            continue
        if tak_schrijft_een_flow(knoop.body):
            gevonden.add(rechts[0].value)
    return gevonden


@lru_cache(maxsize=1)
def _flow_websockets() -> dict[str, Callable[..., Any]]:
    from fastapi.routing import APIWebSocketRoute

    from src.main import create_test_app

    return {
        _sleutel(route.endpoint): route.endpoint
        for route in create_test_app().routes
        if isinstance(route, APIWebSocketRoute)
        and route.endpoint.__module__.startswith(WS_FLOWMODULE_PREFIXEN)
    }


def _handler_ast(endpoint: Callable[..., Any]) -> ast.AST:
    import textwrap

    return ast.parse(textwrap.dedent(inspect.getsource(endpoint)))


def test_de_flowchat_websocket_wordt_gevonden_en_schrijft() -> None:
    """Vangnet: zonder deze ingang (of zonder herkende schrijftakken) meet de guard niets."""
    sleutel = "src.core.api.v1.focus_builder.ws_chat_router::focus_builder_ws_chat"
    websockets = _flow_websockets()
    assert sleutel in websockets, sorted(websockets)
    assert {"accept_proposal", "execute"} <= schrijvende_berichttypen(
        _handler_ast(websockets[sleutel])
    )


def test_elke_schrijvende_websocketbericht_vraagt_het_publicatierecht() -> None:
    fouten: list[str] = []
    for sleutel, endpoint in sorted(_flow_websockets().items()):
        handler = _handler_ast(endpoint)
        schrijvend = schrijvende_berichttypen(handler)
        if not schrijvend:
            continue
        module = importlib.import_module(endpoint.__module__)
        bewaakt: frozenset[str] = getattr(module, "SCHRIJVENDE_BERICHTTYPEN", frozenset())
        if schrijvend - bewaakt:
            fouten.append(f"{sleutel}: niet in SCHRIJVENDE_BERICHTTYPEN: {sorted(schrijvend - bewaakt)}")
        if not _roept_aan(handler, WS_POORT):
            fouten.append(f"{sleutel}: roept {WS_POORT} niet aan")
    assert not fouten, f"Websocketberichten die een flow schrijven zonder `workflows:publish`: {fouten}"


def test_de_websocketpoort_vraagt_workflows_publish() -> None:
    """De poort zelf: roept `controleer_resource_recht(..., "workflows", "publish")` aan."""
    from src.core.api.v1.focus_builder import ws_chat_router

    poort = _handler_ast(ws_chat_router.mag_flows_publiceren)
    aanroepen = [
        k
        for k in ast.walk(poort)
        if isinstance(k, ast.Call) and _aanroepnaam(k) == "controleer_resource_recht"
    ]
    assert aanroepen, "mag_flows_publiceren roept controleer_resource_recht niet aan"
    constanten = [a.value for a in aanroepen[0].args if isinstance(a, ast.Constant)]
    assert constanten[-2:] == ["workflows", "publish"], constanten


def test_herkenner_ziet_een_schrijvend_berichttype() -> None:
    code = (
        "async def h():\n"
        "    if msg_type == 'a':\n        await service.repository.update(1, {})\n"
        "    elif msg_type == 'b':\n        await agent.accept_proposal('p')\n"
        "    elif msg_type == 'c':\n        await websocket.send_json({})\n"
        "    elif msg_type == 'd':\n        d.update({})\n"
    )

    assert schrijvende_berichttypen(ast.parse(code)) == {"a", "b"}


PROXY_SCHRIJFROUTES: frozenset[str] = frozenset(
    {"proxy_create_flow", "proxy_update_flow", "proxy_delete_flow", "proxy_execute_flow"}
)


def test_de_proxy_vraagt_het_publicatierecht_op_flowschrijfroutes() -> None:
    from src.core.api.v1.focus_builder.proxy import create_proxy_router

    routes = {
        r.endpoint.__name__: r
        for r in create_proxy_router().routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/focus-builder/flows")
        and r.methods & {"POST", "PUT", "PATCH", "DELETE"}
    }
    assert set(routes) == PROXY_SCHRIJFROUTES, sorted(routes)
    zonder = sorted(n for n, r in routes.items() if not vraagt_publicatierecht(r.dependant))
    assert not zonder, f"Proxy-flowroutes zonder `workflows:publish`: {zonder}"
