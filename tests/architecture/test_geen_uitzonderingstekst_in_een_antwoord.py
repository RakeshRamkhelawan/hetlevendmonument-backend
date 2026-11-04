"""Een uitzonderingstekst komt niet in een antwoord, een HTTPException of een websocketbericht.

Brief 2026-10-21 (geen interne foutteksten naar de klant), `.claude/rules/error-handling.md`
"Production Safety". Drie security-reviews op ActivePieces vonden telkens nieuwe plekken van
dezelfde soort: `str(e)` van een httpx-, database- of taalmodelfout (die het interne adres, een
tabelnaam of een prompt noemt) belandde in `detail=`, een JSON-veld of een websocketbericht.
Plek voor plek repareren hield de soort in leven; deze guard sluit de SOORT.

**De regel.** In een `except ... as <var>`-tak mag de tekst van de uitzondering (`str(var)`,
`repr(var)`, een f-string of `%`/`.format` met `var`, `var.args`) NIET buiten een logregel
voorkomen. Naar buiten gaat een vaste tekst; details en soort staan in het log.

**Wat is toegestaan.**
- een tak die ALLEEN eigen uitzonderingsklassen vangt (gedefinieerd in het bestand of geimporteerd
  uit `src...`): die tekst is bewust door ons geformuleerd. Een kale `ValueError`, `KeyError` of
  `Exception` telt NIET: die kan ook uit een bibliotheek komen;
- een regel op `KNOWN_UITZONDERINGEN`: gedateerd, `bestand::functie`, met een reden per regel.

**De scope** is de antwoordlaag, bepaald op de code zelf en niet op een maplijst: elk bronbestand
onder `src/` dat een `APIRouter` aanmaakt of `WebSocket` importeert. Een nieuwe router in een
nieuwe map valt er dus vanzelf onder.

De unit van meten is de functie (sleutel `bestand::functie`, geneste functies met punt), nooit het
bestand: een uitzondering stelt EEN plek vrij waarvoor een reden is opgeschreven, niet elke plek
in dat bestand (zie quality-gates.md, aanscherping 2026-09-18).

**Mutatiebewijs (2026-10-22), beide richtingen en in een bestand dat al op de lijst staat.** Elke
regel hieronder is een eigen test met een tijdelijke bronboom (`tmp_path`); de echte boom wordt
niet gemuteerd:
- `str(e)`, `repr(e)`, `f"{e}"`, `"%s" % e`, `"{}".format(e)`, `e.args` in `detail=`, in een dict en
  in `websocket.send_json` -> betrapt (een test per vorm);
- dezelfde tekst BINNEN een logregel, of in een tak die alleen een eigen klasse vangt -> niet
  betrapt (de andere richting; zonder deze is "verbied alles" een geldige oplossing);
- een tweede functie in een bestand dat al op de lijst staat -> wel betrapt;
- een bestand zonder router -> buiten de scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

LOGMETHODEN = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log", "fatal"}
)
# Telemetrie (OpenTelemetry-span) gaat naar de tracingbackend, niet naar de klant.
TELEMETRIE = frozenset({"set_status", "record_exception", "add_event", "set_attribute"})
# Functies die naar een log of bestand schrijven en niet naar de klant.
# Attributen waarin een vreemde fout zijn tekst draagt (httpx: `response`, eigen: `message`).
TEKSTVELDEN = frozenset({"message", "detail", "reason", "msg", "response", "__cause__"})

LOGFUNCTIES = frozenset({"print", "log_to_file"})
# Deze namen zijn nooit "eigen": ze kunnen ook uit een bibliotheek of het OS komen.
BUILTIN_FOUTEN = frozenset(
    {
        "Exception",
        "BaseException",
        "ValueError",
        "KeyError",
        "TypeError",
        "RuntimeError",
        "OSError",
        "IOError",
        "AttributeError",
        "IndexError",
        "LookupError",
        "ConnectionError",
        "TimeoutError",
        "PermissionError",
        "FileNotFoundError",
        "NotImplementedError",
        "ImportError",
        "UnicodeDecodeError",
        "StopIteration",
        "AssertionError",
        "ArithmeticError",
    }
)

# Gedateerd, `bestand::functie`, een reden PER regel. Leeg is het doel.
# Bestanden zonder router die toch een antwoord vormen: ze leveren een model of dataclass dat een
# router ongefilterd doorgeeft. Gevonden in de Gate 2-review van 2026-10-22.
EXTRA_ANTWOORDBESTANDEN = frozenset(
    {
        "src/core/monitoring/health_checks.py",
        "src/core/services/focus_suggestion_service.py",
        "src/core/services/swarm_stream_service.py",
        "src/domains/flows/agentic_service.py",
    }
)

KNOWN_UITZONDERINGEN: dict[str, str] = {
    # 2026-10-22: de tekst gaat naar de beveiligingsauditlog (`_log_security_event`), een logkanaal
    # dat de guard niet als zodanig kent; de klant krijgt een vaste tekst.
    "src/core/security/security_middleware.py::SecurityMiddleware.__call__": (
        "str(e) gaat naar de beveiligingsauditlog, niet naar de klant"
    ),
    # 2026-10-22: opstartdiagnose zonder aanroepers in src/ (grep); het resultaat gaat nergens naar
    # een klant. Verdwijnt de functie, dan meldt de staleness-test dit.
    "src/core/security/security_middleware.py::validate_security_middleware_instantiation": (
        "opstartdiagnose zonder aanroeper; resultaat bereikt geen klant"
    ),
}


def _eigen_namen(boom: ast.Module) -> set[str]:
    namen: set[str] = set()
    for node in ast.walk(boom):
        if isinstance(node, ast.ClassDef):
            namen.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0 or (node.module or "").split(".")[0] == "src":
                namen.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "src":
                    namen.add((a.asname or a.name).split(".")[0])
    return namen


def _is_eigen_type(expr: ast.expr | None, eigen: set[str]) -> bool:
    if expr is None:
        return False
    if isinstance(expr, ast.Tuple):
        return bool(expr.elts) and all(_is_eigen_type(e, eigen) for e in expr.elts)
    if isinstance(expr, ast.Name):
        # HTTPException: de `detail` is de tekst die de eigen code zelf koos bij `raise`; een lek
        # via `detail=str(e)` wordt op die raise-plek gevangen.
        return (expr.id in eigen or expr.id == "HTTPException") and expr.id not in BUILTIN_FOUTEN
    if isinstance(expr, ast.Attribute):
        basis: ast.expr = expr
        while isinstance(basis, ast.Attribute):
            basis = basis.value
        return isinstance(basis, ast.Name) and basis.id in eigen
    return False


def _is_logcall(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    functie = node.func
    if isinstance(functie, ast.Attribute) and (
        functie.attr in LOGMETHODEN or functie.attr in TELEMETRIE
    ):
        return True
    if (
        isinstance(functie, ast.Attribute)
        and functie.attr == "write"
        and isinstance(functie.value, ast.Attribute)
        and functie.value.attr == "stderr"
    ):
        return True
    return isinstance(functie, ast.Name) and functie.id in LOGFUNCTIES


def _is_var(node: ast.AST, var: str) -> bool:
    return isinstance(node, ast.Name) and node.id == var


def _maakt_tekst(node: ast.AST, var: str) -> bool:
    """Maakt deze knoop de tekst van de uitzondering `var` (str/repr/f-string/%/format/args)?"""
    if isinstance(node, ast.Call):
        functie = node.func
        if isinstance(functie, ast.Name) and functie.id in {"str", "repr"} and node.args:
            eerste = node.args[0]
            if _is_var(eerste, var) or (
                isinstance(eerste, ast.Attribute)
                and _is_var(eerste.value, var)
                and eerste.attr == "args"
            ):
                return True
        if isinstance(functie, ast.Attribute) and functie.attr == "format":
            if any(_is_var(a, var) for a in node.args) or any(
                _is_var(k.value, var) for k in node.keywords
            ):
                return True
    if isinstance(node, ast.FormattedValue) and _is_var(node.value, var):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        rechts = node.right
        if _is_var(rechts, var) or (
            isinstance(rechts, ast.Tuple) and any(_is_var(e, var) for e in rechts.elts)
        ):
            return True
    if isinstance(node, ast.Attribute) and node.attr in TEKSTVELDEN and _is_var(node.value, var):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"format_exc", "format_exception", "format_tb"}:
            return True
    return isinstance(node, ast.Attribute) and node.attr == "args" and _is_var(node.value, var)


def _overtreding_in_handler(handler: ast.ExceptHandler, eigen: set[str]) -> bool:
    if handler.name is None or _is_eigen_type(handler.type, eigen):
        return False
    var = handler.name
    gevonden = False

    def loop(node: ast.AST, gelogd: bool) -> None:
        nonlocal gevonden
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        # Een vergelijking (`"x" in str(e)`, `str(e) == "..."`) is besturing, geen antwoord.
        nu_gelogd = gelogd or _is_logcall(node) or isinstance(node, ast.Compare)
        if not nu_gelogd and _maakt_tekst(node, var):
            gevonden = True
        for kind in ast.iter_child_nodes(node):
            loop(kind, nu_gelogd)

    for stmt in handler.body:
        loop(stmt, False)
    return gevonden


def _is_antwoordlaag(boom: ast.Module) -> bool:
    """Maakt dit bestand een router of gebruikt het een WebSocket?"""
    for node in ast.walk(boom):
        if isinstance(node, ast.Call):
            naam = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if naam in {"APIRouter", "FastAPI"}:
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                doel = deco.func if isinstance(deco, ast.Call) else deco
                if (
                    isinstance(doel, ast.Attribute)
                    and isinstance(doel.value, ast.Name)
                    and doel.value.id == "app"
                    and doel.attr in {"get", "post", "put", "patch", "delete", "websocket"}
                ):
                    return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {
            "fastapi",
            "starlette",
        }:
            if any(a.name == "WebSocket" for a in node.names):
                return True
    return False


def _functies_met_overtreding(boom: ast.Module) -> set[str]:
    """Qualnamen (`Klasse.methode`, `<module>`) van de functies met een overtreding."""
    eigen = _eigen_namen(boom)
    gevonden: set[str] = set()

    def loop(node: ast.AST, pad: tuple[str, ...]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            pad = (*pad, node.name)
        if isinstance(node, ast.ExceptHandler) and _overtreding_in_handler(node, eigen):
            gevonden.add(".".join(pad) if pad else "<module>")
        for kind in ast.iter_child_nodes(node):
            loop(kind, pad)

    loop(boom, ())
    return gevonden


def vind_overtredingen(root: Path) -> tuple[set[str], int]:
    """(`bestand::functie` per overtreding, aantal gescande antwoordlaag-bestanden)."""
    gevonden: set[str] = set()
    gescand = 0
    for pad in sorted((root / "src").rglob("*.py")):
        if pad.name.startswith("test_") or "tests" in pad.parts:
            continue
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        relatief = pad.relative_to(root).as_posix()
        if relatief not in EXTRA_ANTWOORDBESTANDEN and not _is_antwoordlaag(boom):
            continue
        gescand += 1
        for functie in _functies_met_overtreding(boom):
            gevonden.add(f"{relatief}::{functie}")
    return gevonden, gescand


def _schrijf(root: Path, relatief: str, tekst: str) -> None:
    doel = root / relatief
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_text(tekst, encoding="utf-8")


_ROUTER_KOP = "from fastapi import APIRouter, HTTPException\nrouter = APIRouter()\n\n"


def _router(handler: str) -> str:
    return (
        _ROUTER_KOP
        + "async def doe():\n    try:\n        x = 1\n    except Exception as e:\n"
        + "".join(f"        {regel}\n" for regel in handler.splitlines())
    )


def test_buiten_de_uitzonderingen_staat_er_geen_uitzonderingstekst_in_een_antwoord() -> None:
    gevonden, gescand = vind_overtredingen(REPO_ROOT)

    nieuw = sorted(gevonden - set(KNOWN_UITZONDERINGEN))

    assert gescand >= 100, f"Slechts {gescand} antwoordlaag-bestanden gevonden; is de scope kapot?"
    assert not nieuw, (
        f"{len(nieuw)} plekken zetten een uitzonderingstekst in een antwoord: "
        + ", ".join(nieuw[:15])
        + (" ..." if len(nieuw) > 15 else "")
        + ". Geef een vaste tekst terug en zet details en soort in het log."
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    gevonden, _ = vind_overtredingen(REPO_ROOT)

    verouderd = sorted(sleutel for sleutel in KNOWN_UITZONDERINGEN if sleutel not in gevonden)

    assert not verouderd, (
        "Deze uitzondering is opgelost of hernoemd en hoort uit de lijst: " + ", ".join(verouderd)
    )


def test_elke_uitzondering_heeft_een_reden() -> None:
    zonder = [sleutel for sleutel, reden in KNOWN_UITZONDERINGEN.items() if not reden.strip()]

    assert not zonder


@pytest.mark.parametrize(
    "uitdrukking",
    [
        "raise HTTPException(status_code=500, detail=str(e))",
        "raise HTTPException(status_code=500, detail=repr(e))",
        'raise HTTPException(status_code=500, detail=f"fout: {e}")',
        'raise HTTPException(status_code=500, detail="fout: %s" % e)',
        'raise HTTPException(status_code=500, detail="fout: %s" % (e,))',
        'raise HTTPException(status_code=500, detail="fout: {}".format(e))',
        "raise HTTPException(status_code=500, detail=str(e.args))",
        "raise HTTPException(status_code=500, detail=e.message)",
        "raise HTTPException(status_code=500, detail=traceback.format_exc())",
        "raise HTTPException(status_code=500, detail=e.args[0])",
        'return {"error": str(e)}',
        'await websocket.send_json({"type": "error", "message": str(e)})',
    ],
)
def test_een_uitzonderingstekst_in_een_antwoord_wordt_betrapt(
    tmp_path: Path, uitdrukking: str
) -> None:
    _schrijf(tmp_path, "src/core/x/slecht.py", _router(uitdrukking))

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/slecht.py::doe"}


@pytest.mark.parametrize(
    "handler",
    [
        'logger.error("mislukt: %s", e)\nraise HTTPException(status_code=500, detail="Interne fout")',
        'logger.error(f"mislukt: {e}", exc_info=True)\nraise HTTPException(status_code=500, detail="x")',
        'logging.warning("mislukt: " + str(e))\nraise HTTPException(status_code=500, detail="x")',
        "raise HTTPException(status_code=500, detail=type(e).__name__)",
        'raise HTTPException(status_code=500, detail="Interne fout") from e',
        "span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))",
        'if "unique" in str(e).lower():\n    raise HTTPException(status_code=409, detail="Bestaat al")',
        'if str(e) == "Setup mode is disabled":\n    raise HTTPException(status_code=403, detail="Uit")',
        'if "x" in str(e):\n    raise HTTPException(status_code=409, detail="Bestaat al")',
        'if "x" in e.args[0]:\n    raise HTTPException(status_code=409, detail="Bestaat al")',
        'sys.stderr.write("fout: %s\n" % e)',
        'log_to_file(f"fout: {e}")',
    ],
)
def test_dezelfde_tekst_in_een_logregel_of_zonder_tekst_wordt_niet_betrapt(
    tmp_path: Path, handler: str
) -> None:
    _schrijf(tmp_path, "src/core/x/netjes.py", _router(handler))

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == set()


def test_een_tak_die_alleen_een_eigen_klasse_vangt_mag_zijn_tekst_tonen(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/eigen.py",
        _ROUTER_KOP
        + "class NietToegestaneStap(Exception):\n    pass\n\n"
        + "async def doe():\n    try:\n        x = 1\n    except NietToegestaneStap as e:\n"
        + "        raise HTTPException(status_code=422, detail=str(e)) from e\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == set()


def test_een_geimporteerde_eigen_klasse_uit_src_telt_als_eigen(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/eigen.py",
        "from src.core.activepieces.stappencontrole import NietToegestaneStap\n"
        + _ROUTER_KOP
        + "async def doe():\n    try:\n        x = 1\n    except NietToegestaneStap as e:\n"
        + "        raise HTTPException(status_code=422, detail=str(e)) from e\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == set()


@pytest.mark.parametrize("vangt", ["ValueError", "Exception", "(ValueError, KeyError)", "OSError"])
def test_een_kale_builtin_telt_niet_als_eigen(tmp_path: Path, vangt: str) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/kaal.py",
        _ROUTER_KOP
        + f"async def doe():\n    try:\n        x = 1\n    except {vangt} as e:\n"
        + "        raise HTTPException(status_code=400, detail=str(e)) from e\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/kaal.py::doe"}


def test_een_bibliotheekklasse_telt_niet_als_eigen(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/lib.py",
        "import httpx\n"
        + _ROUTER_KOP
        + "async def doe():\n    try:\n        x = 1\n    except httpx.HTTPError as e:\n"
        + "        raise HTTPException(status_code=502, detail=str(e)) from e\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/lib.py::doe"}


def test_een_uitzondering_geldt_voor_een_functie_niet_voor_het_bestand(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/gemengd.py",
        _ROUTER_KOP
        + "async def toegestaan():\n    try:\n        x = 1\n    except Exception as e:\n"
        + "        return {'error': str(e)}\n\n"
        + "async def nieuw_en_slecht():\n    try:\n        x = 1\n    except Exception as e:\n"
        + "        return {'error': str(e)}\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)
    toegestaan = {"src/core/x/gemengd.py::toegestaan"}

    assert gevonden - toegestaan == {"src/core/x/gemengd.py::nieuw_en_slecht"}


def test_een_methode_in_een_klasse_krijgt_de_klassenaam_in_de_sleutel(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/klasse.py",
        _ROUTER_KOP
        + "class Dienst:\n    async def doe(self):\n        try:\n            x = 1\n"
        + "        except Exception as e:\n            return {'error': str(e)}\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/klasse.py::Dienst.doe"}


def test_een_bestand_zonder_router_of_websocket_valt_buiten_de_scope(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/service.py",
        "async def doe():\n    try:\n        x = 1\n    except Exception as e:\n"
        "        return {'error': str(e)}\n",
    )

    gevonden, gescand = vind_overtredingen(tmp_path)

    assert (gevonden, gescand) == (set(), 0)


def test_een_bestand_met_een_websocket_valt_wel_binnen_de_scope(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/ws.py",
        "from fastapi import WebSocket\n\n"
        "async def doe(websocket: WebSocket):\n    try:\n        x = 1\n    except Exception as e:\n"
        "        await websocket.send_json({'message': str(e)})\n",
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/ws.py::doe"}


def test_een_vergelijking_beschermt_een_lek_ernaast_niet(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/lek.py",
        _router(
            'if "unique" in str(e):'
            + chr(10)
            + "    raise HTTPException(status_code=409, detail=str(e))"
            + chr(10)
            + 'raise HTTPException(status_code=500, detail="x")'
        ),
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/lek.py::doe"}


def test_een_bestand_met_een_app_route_valt_binnen_de_scope(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/app_route.py",
        (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "\n"
            "@app.post('/x')\n"
            "async def doe():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception as e:\n"
            "        return {'error': str(e)}\n"
        ),
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/x/app_route.py::doe"}


def test_een_genoemd_extra_antwoordbestand_valt_binnen_de_scope(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/monitoring/health_checks.py",
        (
            "def doe():\n"
            "    try:\n"
            "        x = 1\n"
            "    except Exception as e:\n"
            "        return {'error': str(e)}\n"
        ),
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == {"src/core/monitoring/health_checks.py::doe"}


def test_een_httpexception_met_eigen_tekst_mag_worden_doorgegeven(tmp_path: Path) -> None:
    _schrijf(
        tmp_path,
        "src/core/x/doorgeven.py",
        (
            "from fastapi import APIRouter, HTTPException\n"
            "router = APIRouter()\n"
            "\n"
            "async def doe():\n"
            "    try:\n"
            "        x = 1\n"
            "    except HTTPException as e:\n"
            "        return {'message': str(e.detail)}\n"
        ),
    )

    gevonden, _ = vind_overtredingen(tmp_path)

    assert gevonden == set()
