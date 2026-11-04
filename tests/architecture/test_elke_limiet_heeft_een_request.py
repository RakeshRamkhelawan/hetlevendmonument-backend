"""Elke functie met een limietdecorator heeft een `Request`-parameter.

Brief 2026-10-25 (rate limit faalt dicht). De limietdecorators zoeken de `Request` tussen de
argumenten en deden bij een route zonder `Request` stilletjes niets: 38 routes hadden geen
limiet. De decorators falen nu zelf bij het decoreren (`vereis_request_parameter`); deze test is
de tweede laag en vindt de overtreding zonder dat de module hoeft te worden geimporteerd.

**Wat hij toetst: STRUCTUUR, geen tekst.** AST over alle bestanden in `src/`: een
`FunctionDef`/`AsyncFunctionDef` met een decorator uit de benoemde verzameling en geen enkele
parameter met annotatie `Request`. De verzameling is: `privacy_rate_limit`, elke publieke
`*_limit` in beide rate_limiter-modules, en de aliassen die elders van die namen zijn afgeleid
(`bonnen_read_limit = privacy_rate_limit(...)`, `from ... import x as _x`, een wrapper
`def x(func): return _x(func)`).
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LIMITER_MODULES = (
    SRC / "core" / "shared" / "rate_limiter.py",
    SRC / "core" / "governance" / "rate_limiter.py",
)
# Ondergrens: de brief mat 109 routes; minder betekent dat de zoeker iets mist.
MIN_GEVONDEN = 100


def _basisnamen() -> set[str]:
    namen = {"privacy_rate_limit"}
    for module in LIMITER_MODULES:
        for node in ast.parse(module.read_text(encoding="utf-8")).body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.endswith("_limit")
                and not node.name.startswith(("check_", "_"))
            ):
                namen.add(node.name)
    return namen


def _noemt(node: ast.AST, namen: set[str]) -> bool:
    for kind in ast.walk(node):
        if isinstance(kind, ast.Name) and kind.id in namen:
            return True
        if isinstance(kind, ast.Attribute) and kind.attr in namen:
            return True
    return False


def _met_aliassen(
    bomen: dict[str, ast.Module], basis: set[str], uitzondering: set[str]
) -> set[str]:
    namen = set(basis)
    while True:
        voor = len(namen)
        for pad, boom in bomen.items():
            if pad in uitzondering:
                continue
            for node in ast.walk(boom):
                if isinstance(node, ast.ImportFrom):
                    namen.update(a.asname for a in node.names if a.name in namen and a.asname)
                elif (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and _noemt(node.value, namen)
                ):
                    namen.add(node.targets[0].id)
                elif (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not node.decorator_list
                    and node.name.endswith("_limit")
                    and len(node.args.args) <= 2
                    and any(_noemt(b, namen) for b in node.body)
                ):
                    namen.add(node.name)
        if len(namen) == voor:
            return namen


def _decoratornaam(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    return None


def _heeft_request(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    argumenten = functie.args
    for parameter in [*argumenten.posonlyargs, *argumenten.args, *argumenten.kwonlyargs]:
        annotatie = parameter.annotation
        if isinstance(annotatie, ast.Name) and annotatie.id == "Request":
            return True
        if isinstance(annotatie, ast.Attribute) and annotatie.attr == "Request":
            return True
        if (
            isinstance(annotatie, ast.Constant)
            and isinstance(annotatie.value, str)
            and annotatie.value.split(".")[-1] == "Request"
        ):
            return True
    return False


def zoek_limietfuncties(
    bomen: dict[str, ast.Module], basis: set[str], uitzondering: frozenset[str] = frozenset()
) -> tuple[int, list[str]]:
    """(aantal functies met een limietdecorator, de namen van degene ZONDER `Request`)."""
    namen = _met_aliassen(bomen, basis, set(uitzondering))
    totaal, zonder = 0, []
    for pad, boom in bomen.items():
        if pad in uitzondering:
            continue
        for node in ast.walk(boom):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _decoratornaam(d) in namen for d in node.decorator_list
            ):
                totaal += 1
                if not _heeft_request(node):
                    zonder.append(f"{pad}:{node.lineno} {node.name}")
    return totaal, sorted(zonder)


@functools.cache
def _bomen_van_src() -> dict[str, ast.Module]:
    """Alle bomen van `src/`, een keer per module-run; de tests lezen ze alleen."""
    bomen: dict[str, ast.Module] = {}
    for bestand in sorted(SRC.rglob("*.py")):
        try:
            bomen[bestand.relative_to(ROOT).as_posix()] = ast.parse(
                bestand.read_text(encoding="utf-8")
            )
        except SyntaxError:
            continue
    return bomen


def _uitzondering() -> frozenset[str]:
    return frozenset(p.relative_to(ROOT).as_posix() for p in LIMITER_MODULES)


def _bron(tekst: str) -> dict[str, ast.Module]:
    return {"synthetisch.py": ast.parse(tekst)}


def test_geen_enkele_limietroute_mist_een_request() -> None:
    _, zonder = zoek_limietfuncties(_bomen_van_src(), _basisnamen(), _uitzondering())

    assert not zonder, (
        "Een route met een limietdecorator zonder `request: Request` krijgt geen limiet "
        f"(en de decorator weigert hem bij het importeren): {zonder}"
    )


def test_de_zoeker_vindt_een_redelijk_aantal_routes() -> None:
    """Zonder deze ondergrens is een lege zoeker een groene guard."""
    totaal, _ = zoek_limietfuncties(_bomen_van_src(), _basisnamen(), _uitzondering())

    assert totaal >= MIN_GEVONDEN


def test_de_verzameling_decorators_bevat_de_bekende_namen() -> None:
    namen = _basisnamen()

    assert {"privacy_rate_limit", "cva_chat_limit", "integration_write_limit"} <= namen


def test_de_zoeker_vindt_een_route_zonder_request() -> None:
    bron = "@privacy_rate_limit(max_requests=3, window_seconds=60)\nasync def f(x: int): ...\n"

    assert zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1] != []


def test_de_zoeker_laat_een_route_met_request_met_rust() -> None:
    bron = "@privacy_rate_limit()\nasync def f(request: Request, x: int): ...\n"

    assert zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1] == []


def test_de_zoeker_accepteert_request_als_tweede_parameter() -> None:
    bron = "@privacy_rate_limit()\nasync def f(x: int, http_request: Request): ...\n"

    assert zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1] == []


def test_de_zoeker_accepteert_request_als_string_en_als_modulepad() -> None:
    bron = (
        "@privacy_rate_limit()\nasync def f(r: 'Request'): ...\n"
        "@privacy_rate_limit()\nasync def g(r: starlette.requests.Request): ...\n"
    )

    assert zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1] == []


def test_de_zoeker_vindt_een_route_met_een_alias_van_de_decorator() -> None:
    bron = (
        "lees_limit = privacy_rate_limit(max_requests=60)\n@lees_limit\nasync def f(x: int): ...\n"
    )

    assert len(zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1]) == 1


def test_de_zoeker_vindt_een_route_met_een_wrapper_functie_van_de_decorator() -> None:
    bron = (
        "def lees_limit(func):\n    return privacy_rate_limit()(func)\n"
        "@lees_limit\nasync def f(x: int): ...\n"
    )

    assert len(zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1]) == 1


def test_een_parameter_met_een_andere_annotatie_telt_niet_als_request() -> None:
    bron = "@privacy_rate_limit()\nasync def f(request: dict): ...\n"

    assert len(zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"})[1]) == 1


def test_een_functie_zonder_limietdecorator_wordt_genegeerd() -> None:
    bron = "@router.get('/x')\nasync def f(x: int): ...\n"

    assert zoek_limietfuncties(_bron(bron), {"privacy_rate_limit"}) == (0, [])


ROUTE_METHODEN = {
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "websocket",
    "api_route",
    "head",
    "options",
}


def _is_routedecorator(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in ROUTE_METHODEN
    )


def zoek_limiet_boven_route(
    bomen: dict[str, ast.Module], basis: set[str], uitzondering: frozenset[str] = frozenset()
) -> list[str]:
    """Functies waar de limiet BOVEN de routedecorator staat.

    Decorators worden van onder naar boven toegepast. Staat de limiet boven `@router.get(...)`,
    dan registreert de router de ongewrapte functie en wordt de limiet nooit uitgevoerd -- ook
    niet met een `Request`. Gemeten 2026-10-26: zes routes in `admin_digital_twin.py` en
    `admin_learning_endpoints.py` (o.a. het wissen en exporteren van leergegevens).
    """
    namen = _met_aliassen(bomen, basis, set(uitzondering))
    gevonden = []
    for pad, boom in bomen.items():
        if pad in uitzondering:
            continue
        for node in ast.walk(boom):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            limieten = [i for i, d in enumerate(node.decorator_list) if _decoratornaam(d) in namen]
            routes = [i for i, d in enumerate(node.decorator_list) if _is_routedecorator(d)]
            if limieten and routes and min(limieten) < max(routes):
                gevonden.append(f"{pad}:{node.lineno} {node.name}")
    return sorted(gevonden)


def test_de_limiet_staat_onder_de_routedecorator() -> None:
    boven = zoek_limiet_boven_route(_bomen_van_src(), _basisnamen(), _uitzondering())

    assert not boven, (
        "De limiet staat BOVEN @router.<methode>: de router registreert dan de ongewrapte "
        f"functie en de limiet doet niets. Zet de limiet eronder: {boven}"
    )


def _regels(*regels: str) -> str:
    return "\n".join(regels) + "\n"


def test_de_volgordezoeker_vindt_een_limiet_boven_de_route() -> None:
    bron = _regels(
        "@privacy_rate_limit()",
        "@router.get('/x')",
        "async def f(request: Request): ...",
    )

    assert zoek_limiet_boven_route(_bron(bron), {"privacy_rate_limit"}) != []


def test_de_volgordezoeker_laat_een_limiet_onder_de_route_met_rust() -> None:
    bron = _regels(
        "@router.get('/x')",
        "@privacy_rate_limit()",
        "async def f(request: Request): ...",
    )

    assert zoek_limiet_boven_route(_bron(bron), {"privacy_rate_limit"}) == []


ECHTE_REQUEST_MODULES = {"fastapi", "fastapi.requests", "starlette.requests"}


def zoek_nep_request(bomen: dict[str, ast.Module]) -> list[str]:
    """Bestanden waar de naam `Request` NIET naar de echte klasse wijst.

    `_heeft_request` kijkt naar de NAAM van de annotatie; een eigen `class Request` of een import
    van die naam uit een ander pakket zou de controle laten slagen zonder dat de route een echte
    `Request` krijgt (brief 2026-10-27, L1). De runtimecontrole (`vereis_request_parameter`) toetst
    de klasse; deze toets vindt hetzelfde zonder de module te importeren.
    """
    gevonden = []
    for pad, boom in bomen.items():
        for node in ast.walk(boom):
            if isinstance(node, ast.ClassDef) and node.name == "Request":
                gevonden.append(f"{pad}:{node.lineno} class Request")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module not in ECHTE_REQUEST_MODULES
                and any((a.asname or a.name) == "Request" for a in node.names)
            ):
                gevonden.append(f"{pad}:{node.lineno} import Request uit {node.module}")
    return sorted(gevonden)


def test_de_naam_request_wijst_overal_naar_de_echte_klasse() -> None:
    nep = zoek_nep_request(_bomen_van_src())

    assert not nep, f"`Request` is hier niet de klasse van FastAPI/Starlette: {nep}"


def test_de_nepzoeker_vindt_een_eigen_klasse_request() -> None:
    assert zoek_nep_request(_bron("class Request:\n    pass\n")) != []


def test_de_nepzoeker_vindt_een_import_uit_een_ander_pakket() -> None:
    assert zoek_nep_request(_bron("from mijn_pakket import Request\n")) != []


def test_de_nepzoeker_laat_de_echte_imports_met_rust() -> None:
    bron = _regels(
        "from fastapi import Request",
        "from starlette.requests import Request as StarletteRequest",
    )

    assert zoek_nep_request(_bron(bron)) == []


MIN_SLOWAPI = 50  # gemeten 2026-10-27: 64 functies met een slowapi-limiet


def _limiternamen(bomen: dict[str, ast.Module]) -> set[str]:
    """Namen die in `src/` aan een `get_limiter(...)`-aanroep zijn toegewezen (slowapi)."""
    namen: set[str] = set()
    for boom in bomen.values():
        for node in ast.walk(boom):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and _decoratornaam(node.value) == "get_limiter"
            ):
                namen.add(node.targets[0].id)
    return namen


def _is_slowapi_limiet(decorator: ast.expr, limiters: set[str], fabrieken: set[str]) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    functie = decorator.func
    if isinstance(functie, ast.Name):
        return functie.id in fabrieken
    return (
        isinstance(functie, ast.Attribute)
        and functie.attr == "limit"
        and isinstance(functie.value, ast.Name)
        and functie.value.id in limiters
    )


def _slowapi_fabrieken(bomen: dict[str, ast.Module], limiters: set[str]) -> set[str]:
    """Functies die een slowapi-limiet teruggeven (`health_rate_limit` -> `limiter.limit(...)`)."""
    fabrieken: set[str] = set()
    for boom in bomen.values():
        for node in boom.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                _is_slowapi_limiet(kind, limiters, set())
                for kind in ast.walk(node)
                if isinstance(kind, ast.Call)
            ):
                fabrieken.add(node.name)
    return fabrieken


def zoek_slowapi_functies(bomen: dict[str, ast.Module]) -> tuple[int, list[str]]:
    """(aantal functies met een slowapi-limiet, die waar hij BOVEN de routedecorator staat).

    slowapi weigert zelf bij het decoreren een functie zonder `request` (gemeten 2026-10-27:
    `Exception: No "request" or "websocket" argument`), dus de `Request`-controle hoeft hier niet.
    De volgorde is wel een stille fout: staat de limiet boven `@router.get(...)`, dan registreert de
    router de ongewrapte functie en doet de limiet niets.
    """
    limiters = _limiternamen(bomen)
    fabrieken = _slowapi_fabrieken(bomen, limiters)
    totaal, boven = 0, []
    for pad, boom in bomen.items():
        for node in ast.walk(boom):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            limieten = [
                i
                for i, d in enumerate(node.decorator_list)
                if _is_slowapi_limiet(d, limiters, fabrieken)
            ]
            if not limieten:
                continue
            totaal += 1
            routes = [i for i, d in enumerate(node.decorator_list) if _is_routedecorator(d)]
            if routes and min(limieten) < max(routes):
                boven.append(f"{pad}:{node.lineno} {node.name}")
    return totaal, sorted(boven)


def test_geen_slowapi_limiet_staat_boven_de_routedecorator() -> None:
    _, boven = zoek_slowapi_functies(_bomen_van_src())

    assert not boven, (
        "Een slowapi-limiet BOVEN @router.<methode> doet niets: de router registreert de "
        f"ongewrapte functie. Zet de limiet eronder: {boven}"
    )


def test_de_slowapi_zoeker_vindt_een_redelijk_aantal_functies() -> None:
    """Zonder deze ondergrens is een lege zoeker een groene guard."""
    totaal, _ = zoek_slowapi_functies(_bomen_van_src())

    assert totaal >= MIN_SLOWAPI


def test_de_slowapi_zoeker_vindt_een_limiet_boven_de_route() -> None:
    bron = _regels(
        "mijn_limiter = get_limiter('x')",
        "@mijn_limiter.limit('5/minute')",
        "@router.get('/x')",
        "async def f(request: Request): ...",
    )

    assert zoek_slowapi_functies(_bron(bron))[1] != []


def test_de_slowapi_zoeker_laat_een_limiet_onder_de_route_met_rust() -> None:
    bron = _regels(
        "mijn_limiter = get_limiter('x')",
        "@router.get('/x')",
        "@mijn_limiter.limit('5/minute')",
        "async def f(request: Request): ...",
    )

    assert zoek_slowapi_functies(_bron(bron)) == (1, [])


def test_de_slowapi_zoeker_vindt_een_limiet_via_een_fabrieksfunctie_boven_de_route() -> None:
    bron = _regels(
        "mijn_limiter = get_limiter('x')",
        "def gezondheid_limiet(aantal):",
        "    return mijn_limiter.limit(aantal)",
        "@gezondheid_limiet('5/minute')",
        "@router.get('/x')",
        "async def f(request: Request): ...",
    )

    assert zoek_slowapi_functies(_bron(bron))[1] != []


def test_de_slowapi_zoeker_negeert_een_limit_methode_op_een_ander_object() -> None:
    bron = _regels(
        "@iets.limit('5/minute')",
        "@router.get('/x')",
        "async def f(request: Request): ...",
    )

    assert zoek_slowapi_functies(_bron(bron)) == (0, [])


def test_de_volgordezoeker_vindt_ook_een_meerregelige_routedecorator() -> None:
    bron = _regels(
        "@privacy_rate_limit()",
        "@router.put(",
        "    '/x',",
        "    status_code=200,",
        ")",
        "async def f(request: Request): ...",
    )

    assert zoek_limiet_boven_route(_bron(bron), {"privacy_rate_limit"}) != []
