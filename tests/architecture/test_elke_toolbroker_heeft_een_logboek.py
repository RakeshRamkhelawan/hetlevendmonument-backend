"""Elke plek die een `ToolBrokerService` bouwt, sluit het toollogboek aan of kiest er bewust niet voor.

F7 (brief 2026-10-25). `ToolBrokerService` schrijft zijn eigen ketenregel (ADR-019, tabel
`tool_audit_logs`) alleen als hij een `audit_session_factory` heeft (of het oudere paar
`audit_repository` plus `db_session`). Alle vijf de plekken die de broker bouwden gaven geen van
beide mee: het logboek werd in productie nooit geschreven, en niets faalde, want `None` is een
geldige waarde. Een nieuwe plek die dezelfde fout herhaalt moet hier rood worden.

De regel, per aanmaakplek (sleutel `bestand::functie`, zo vindt een lezer hem terug):

1. de aanroep geeft `audit_session_factory=` mee, en de waarde is een TOEGELATEN VORM
   (`TOEGELATEN_FABRIEKEN`, nu alleen `db_manager.get_session`). Er wordt dus niet achter
   None-vormen aangejaagd (parameterdefault, conditie, `getattr`, `.get`, een attribuut dat None
   is, walrus, ...): alles wat geen toegelaten vorm is, is een gebrek, tenzij de plek in
   `AFWIJKENDE_FABRIEKEN` staat met datum en reden. Ook `db_manager` zelf mag in die functie of
   module niet aan None gebonden zijn. `audit_repository=` is in `src` een gebrek (zie onder); OF
2. de plek staat in `ZONDER_LOGBOEK` met een reden. Dat is de bewuste, gedocumenteerde uitzondering.
   Een uitzondering voor een plek die wel een logboek meegeeft, of die niet meer bestaat, is zelf een
   fout: de lijst mag niet stilletjes verouderen.

AST (`ast.Call`) en geen tekstzoeken: een opmerking of een docstring die "audit_repository=" noemt
(zoals `redaction.py` dat deed) telt niet, en een aanroep over meerdere regels of via een alias wel.
Een `**kwargs`-aanroep is niet te beoordelen en faalt, net als een subklasse van de broker.

`audit_repository=`: het oudere paar (`audit_repository` + `db_session`) wordt in `src` door niemand
meer gebruikt en schrijft buiten het slot van de ketenvolgorde om. Daarom is het in `src` geen
toegelaten vorm maar een gebrek, zonder uitzonderingsroute: dat is het eenvoudigst (een regel) en het
strengst (geen tweede vorm om te bewaken). Tests bouwen de broker rechtstreeks en vallen buiten deze
scan, dus voor tests hoeft er niets te worden toegelaten. `db_session=` blijft gewoon geldig: de
HITL-ticketcommit gebruikt hem, los van het logboek.

Er is een ONDERGRENS: de scan moet de vijf bekende plekken vinden. Een scan die niets ziet (een
hernoemde klasse, een verplaatste map) is anders groen op een lege verzameling.

De regel zelf wordt op synthetische fragmenten getoetst in BEIDE richtingen (wat moet falen, faalt;
wat moet slagen, slaagt). Het mutatiebewijs op de echte code staat in het rapport van deze bundel.
"""

from __future__ import annotations

import ast
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
KLASSE = "ToolBrokerService"
LOGBOEK_SLEUTELS = frozenset({"audit_repository", "audit_session_factory"})

#: De ENIGE vormen die als `audit_session_factory=` in `src` mogen staan (als puntpad). Alle vijf de
#: echte plekken gebruiken `db_manager.get_session`. Een nieuwe vorm hoort hier bewust bij, niet via
#: een uitzondering op een plek, tenzij het echt een eenmalige afwijking is.
TOEGELATEN_FABRIEKEN = frozenset({"db_manager.get_session"})

#: Bewust zonder logboek: `bestand::functie` -> de reden. Leeg sinds F7 (2026-10-26): elke plek
#: schrijft. Een nieuwe uitzondering heeft een reden in gewone taal nodig, niet alleen een sleutel.
ZONDER_LOGBOEK: dict[str, str] = {}

#: De plekken die er bij het aansluiten waren. Dit is de ondergrens: verdwijnt er een, dan is het of
#: een bewuste verwijdering (pas deze lijst aan) of een scan die iets mist.
BEKENDE_PLEKKEN = frozenset(
    {
        "src/core/tool_broker/dependencies.py::initialize_async",
        "src/core/tool_broker/dependencies.py::get_service",
        "src/core/tool_broker/workflow_identiteit.py::bouw_workflow_broker",
        "src/core/agents/base_agent.py::_create_tool_broker",
        "src/core/als/agents/specialist_base.py::__init__",
    }
)


@dataclass(frozen=True)
class Uitzondering:
    """Een bewuste, gedateerde uitzondering met een reden in gewone taal."""

    datum: str
    reden: str


#: Verwijzingen naar de klasse die GEEN directe aanroep zijn (een alias, `functools.partial`, een
#: `getattr`-string, ...) en die toch bewust zijn: `bestand::functie` -> datum + reden. Zo'n
#: verwijzing laat de aanroep zelf buiten het bereik van de scan; daarom is elke zo'n plek een
#: gebrek tenzij hij hier staat. Leeg: in `src` bestaat er geen (2026-10-27).
ANDERE_VERWIJZINGEN: dict[str, Uitzondering] = {}

#: Een plek met een `audit_session_factory=` die GEEN toegelaten vorm is maar bewust zo hoort:
#: `bestand::functie` -> datum + reden. Leeg (2026-10-27): alle vijf gebruiken `db_manager.get_session`.
AFWIJKENDE_FABRIEKEN: dict[str, Uitzondering] = {}


@dataclass(frozen=True)
class Plek:
    sleutel: str
    regel: int
    gebreken: tuple[str, ...]
    soort: str = "aanroep"
    #: De deelverzameling van `gebreken` die een gedateerde afwijking mag dekken (alleen een
    #: niet-toegelaten fabrieksvorm). Al het andere is nooit excuseerbaar.
    vorm_gebreken: tuple[str, ...] = ()


def _namen_voor_klasse(boom: ast.AST) -> frozenset[str]:
    """De namen waaronder de klasse in dit bestand bereikbaar is (ook `import ... as alias`)."""
    namen = {KLASSE}
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom):
            for alias in knoop.names:
                if alias.name == KLASSE and alias.asname:
                    namen.add(alias.asname)
    return frozenset(namen)


def _is_klasse_aanroep(aanroep: ast.Call, namen: frozenset[str]) -> bool:
    doel = aanroep.func
    if isinstance(doel, ast.Name):
        return doel.id in namen
    return isinstance(doel, ast.Attribute) and doel.attr in namen


def _is_letterlijk_none(waarde: ast.expr) -> bool:
    return isinstance(waarde, ast.Constant) and waarde.value is None


def _binnen_scope(scope: ast.AST) -> Iterator[ast.AST]:
    """De knopen van deze functie (of van de module), zonder in andere functies af te dalen."""
    stapel = list(ast.iter_child_nodes(scope))
    while stapel:
        knoop = stapel.pop()
        yield knoop
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stapel.extend(ast.iter_child_nodes(knoop))


def _is_none_toewijzing(knoop: ast.AST, naam: str) -> bool:
    if isinstance(knoop, ast.Assign) and _is_letterlijk_none(knoop.value):
        return any(isinstance(d, ast.Name) and d.id == naam for d in knoop.targets)
    if isinstance(knoop, (ast.AnnAssign, ast.NamedExpr)):
        return (
            knoop.value is not None
            and _is_letterlijk_none(knoop.value)
            and isinstance(knoop.target, ast.Name)
            and knoop.target.id == naam
        )
    return False


def _naam_is_none(naam: str, scope: ast.AST, boom: ast.AST) -> bool:
    """Is `naam` in deze functie of in de module aan een letterlijke None gebonden?

    Ook als parameter met default None. Dit is GEEN opsporing van None-vormen voor de fabriek zelf
    (dat doet de toelaatlijst): het bewaakt alleen dat de toegelaten wortelnaam `db_manager` niet
    stiekem op None is gezet.
    """
    for s in (scope, boom):
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = s.args
            positioneel = [*a.posonlyargs, *a.args]
            defaults: list[ast.expr | None] = [None] * (len(positioneel) - len(a.defaults))
            defaults.extend(a.defaults)
            paren = [*zip(positioneel, defaults), *zip(a.kwonlyargs, a.kw_defaults)]
            if any(
                arg.arg == naam and d is not None and _is_letterlijk_none(d) for arg, d in paren
            ):
                return True
        if any(_is_none_toewijzing(k, naam) for k in _binnen_scope(s)):
            return True
    return False


def _puntpad(waarde: ast.expr) -> str | None:
    """`a.b.c` als tekst; None voor al het andere (aanroep, indexering, conditie, walrus, ...)."""
    if isinstance(waarde, ast.Name):
        return waarde.id
    if isinstance(waarde, ast.Attribute):
        voor = _puntpad(waarde.value)
        return None if voor is None else f"{voor}.{waarde.attr}"
    return None


def _fabriek_gebrek(sleutel: str, waarde: ast.expr, scope: ast.AST, boom: ast.AST) -> str | None:
    """Waarom deze waarde geen toegelaten logboekfabriek is, of None als hij het wel is."""
    pad = _puntpad(waarde)
    if pad is None or pad not in TOEGELATEN_FABRIEKEN:
        return (
            f"{sleutel}={ast.unparse(waarde)} is geen toegelaten vorm"
            f" (toegelaten: {', '.join(sorted(TOEGELATEN_FABRIEKEN))})"
        )
    wortel = pad.split(".")[0]
    if _naam_is_none(wortel, scope, boom):
        return f"{sleutel}={pad}: {wortel} wordt in deze functie of module aan None gebonden"
    return None


def _annotatieknopen(boom: ast.AST) -> frozenset[int]:
    """De id's van alle knopen die in een typeannotatie staan (argument, retour, `x: T = ...`)."""
    wortels: list[ast.AST] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if knoop.returns is not None:
                wortels.append(knoop.returns)
            a = knoop.args
            for arg in (*a.posonlyargs, *a.args, *a.kwonlyargs, a.vararg, a.kwarg):
                if arg is not None and arg.annotation is not None:
                    wortels.append(arg.annotation)
        elif isinstance(knoop, ast.AnnAssign):
            wortels.append(knoop.annotation)
    return frozenset(id(n) for w in wortels for n in ast.walk(w))


def _isinstanceknopen(boom: ast.AST) -> frozenset[int]:
    """De id's van de knopen in het tweede argument van `isinstance`/`issubclass`."""
    gevonden: set[int] = set()
    for knoop in ast.walk(boom):
        if (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Name)
            and knoop.func.id in ("isinstance", "issubclass")
            and len(knoop.args) >= 2
        ):
            gevonden.update(id(n) for n in ast.walk(knoop.args[1]))
    return frozenset(gevonden)


def _is_naam_string(waarde: object) -> bool:
    return isinstance(waarde, str) and (waarde == KLASSE or waarde.endswith("." + KLASSE))


def _string_verwijzing(knoop: ast.AST, namen: frozenset[str]) -> bool:
    """Wordt de klasse hier OP NAAM, als tekst, opgehaald (`getattr`, `__dict__[...]`, importpad)?

    Bewust smal: een kale tekst "ToolBrokerService" is op veel plekken legitiem (een componentnaam
    in een statuslijst, `__all__`). Alleen een ophaalvorm of een puntpad naar de klasse telt.
    """
    if isinstance(knoop, ast.Call):
        doel = knoop.func
        naam = doel.id if isinstance(doel, ast.Name) else getattr(doel, "attr", None)
        if naam in ("getattr", "hasattr") and len(knoop.args) >= 2:
            tweede = knoop.args[1]
            return isinstance(tweede, ast.Constant) and (
                tweede.value in namen or _is_naam_string(tweede.value)
            )
    if isinstance(knoop, ast.Subscript):
        sleutel = knoop.slice
        return isinstance(sleutel, ast.Constant) and (
            sleutel.value in namen or _is_naam_string(sleutel.value)
        )
    if isinstance(knoop, ast.Constant):
        return isinstance(knoop.value, str) and "." in knoop.value and _is_naam_string(knoop.value)
    return False


def beoordeel_bron(bestand: str, bron: str) -> list[Plek]:
    """Alle aanmaakplekken en omwegen in deze bron, elk met wat er aan ontbreekt (leeg is goed)."""
    boom = ast.parse(bron)
    namen = _namen_voor_klasse(boom)
    plekken: list[Plek] = []

    directe_func = frozenset(
        id(k.func)
        for k in ast.walk(boom)
        if isinstance(k, ast.Call) and _is_klasse_aanroep(k, namen)
    )
    annotaties = _annotatieknopen(boom)
    isinstances = _isinstanceknopen(boom)
    bases = frozenset(
        id(n)
        for k in ast.walk(boom)
        if isinstance(k, ast.ClassDef)
        for b in k.bases
        for n in ast.walk(b)
    )
    docstrings = frozenset(
        id(k.value)
        for k in ast.walk(boom)
        if isinstance(k, ast.Expr) and isinstance(k.value, ast.Constant)
    )

    def verwijzing(knoop: ast.AST, functie: str) -> None:
        if id(knoop) in directe_func or id(knoop) in annotaties:
            return
        if id(knoop) in isinstances or id(knoop) in bases:
            return
        if isinstance(knoop, ast.Name):
            treft = knoop.id in namen
        elif isinstance(knoop, ast.Attribute):
            treft = knoop.attr in namen
        else:
            return
        if not treft or not isinstance(getattr(knoop, "ctx", None), ast.Load):
            return
        plekken.append(
            Plek(
                f"{bestand}::{functie}",
                getattr(knoop, "lineno", 0),
                (f"verwijst naar {KLASSE} zonder hem direct aan te roepen (alias, partial, ...)",),
                "verwijzing",
            )
        )

    def loop(knoop: ast.AST, functie: str, scope: ast.AST) -> None:
        for kind in ast.iter_child_nodes(knoop):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                loop(kind, kind.name, kind)
                continue
            if isinstance(kind, ast.ClassDef):
                gebreken = []
                for basis in kind.bases:
                    naam = basis.id if isinstance(basis, ast.Name) else getattr(basis, "attr", None)
                    if naam in namen:
                        gebreken.append(f"subklasse {kind.name} van {KLASSE}: niet te beoordelen")
                if gebreken:
                    plekken.append(Plek(f"{bestand}::{kind.name}", kind.lineno, tuple(gebreken)))
                loop(kind, functie, scope)
                continue
            if isinstance(kind, (ast.Name, ast.Attribute)):
                verwijzing(kind, functie)
            if id(kind) not in docstrings and _string_verwijzing(kind, namen):
                plekken.append(
                    Plek(
                        f"{bestand}::{functie}",
                        getattr(kind, "lineno", 0),
                        (
                            f"haalt {KLASSE} op naam op (getattr/__dict__/importpad): niet te beoordelen",
                        ),
                        "verwijzing",
                    )
                )
            if isinstance(kind, ast.Call) and _is_klasse_aanroep(kind, namen):
                gebreken = []
                vorm: list[str] = []
                sleutels = {k.arg: k.value for k in kind.keywords if k.arg is not None}
                if any(k.arg is None for k in kind.keywords):
                    gebreken.append("geeft **kwargs mee: niet te beoordelen")
                gegeven = [s for s in sleutels if s in LOGBOEK_SLEUTELS]
                if not gegeven and not any(k.arg is None for k in kind.keywords):
                    gebreken.append("geeft geen audit_repository en geen audit_session_factory mee")
                if "audit_repository" in sleutels:
                    gebreken.append(
                        "audit_repository= is in src niet toegelaten: het oudere paar wordt niet"
                        " meer gebruikt en schrijft buiten het slot van de ketenvolgorde om;"
                        " gebruik audit_session_factory=db_manager.get_session"
                    )
                if "audit_session_factory" in sleutels:
                    gebrek = _fabriek_gebrek(
                        "audit_session_factory", sleutels["audit_session_factory"], scope, boom
                    )
                    if gebrek:
                        gebreken.append(gebrek)
                        vorm.append(gebrek)
                if len(kind.args) > 0:
                    gebreken.append("positionele argumenten: niet te beoordelen")
                plekken.append(
                    Plek(
                        f"{bestand}::{functie}",
                        kind.lineno,
                        tuple(gebreken),
                        vorm_gebreken=tuple(vorm),
                    )
                )
            loop(kind, functie, scope)

    loop(boom, "<module>", boom)
    return plekken


def beoordeel_alles(
    plekken: list[Plek],
    uitzonderingen: dict[str, str],
    verwijzingen: dict[str, Uitzondering] | None = None,
    afwijkingen: dict[str, Uitzondering] | None = None,
) -> list[str]:
    """De overtredingen over alle plekken, inclusief een verouderde of reploze uitzondering."""
    verwijzingen = verwijzingen or {}
    afwijkingen = afwijkingen or {}
    fouten: list[str] = []
    gezien = {p.sleutel for p in plekken if p.soort == "aanroep"}
    gezien_verwijzing = {p.sleutel for p in plekken if p.soort == "verwijzing"}
    for plek in plekken:
        if plek.soort == "verwijzing":
            if plek.sleutel in verwijzingen:
                continue
            for gebrek in plek.gebreken:
                fouten.append(f"{plek.sleutel} (regel {plek.regel}): {gebrek}")
            continue
        if plek.sleutel in uitzonderingen:
            if not plek.gebreken:
                fouten.append(
                    f"{plek.sleutel}: staat in ZONDER_LOGBOEK maar geeft wel een logboek mee"
                    " -- haal de uitzondering weg"
                )
            continue
        for gebrek in plek.gebreken:
            if plek.sleutel in afwijkingen and gebrek in plek.vorm_gebreken:
                continue
            fouten.append(f"{plek.sleutel} (regel {plek.regel}): {gebrek}")
    for sleutel, reden in uitzonderingen.items():
        if not reden.strip():
            fouten.append(f"{sleutel}: een uitzondering zonder reden")
        if sleutel not in gezien:
            fouten.append(f"{sleutel}: staat in ZONDER_LOGBOEK maar bestaat niet meer")
    for sleutel, uitzondering in verwijzingen.items():
        try:
            date.fromisoformat(uitzondering.datum)
        except ValueError:
            fouten.append(
                f"{sleutel}: een verwijzingsuitzondering zonder geldige datum (JJJJ-MM-DD)"
            )
        if not uitzondering.reden.strip():
            fouten.append(f"{sleutel}: een verwijzingsuitzondering zonder reden")
        if sleutel not in gezien_verwijzing:
            fouten.append(f"{sleutel}: staat in ANDERE_VERWIJZINGEN maar bestaat niet meer")
    met_vorm = {p.sleutel for p in plekken if p.soort == "aanroep" and p.vorm_gebreken}
    for sleutel, uitzondering in afwijkingen.items():
        try:
            date.fromisoformat(uitzondering.datum)
        except ValueError:
            fouten.append(f"{sleutel}: een fabrieksafwijking zonder geldige datum (JJJJ-MM-DD)")
        if not uitzondering.reden.strip():
            fouten.append(f"{sleutel}: een fabrieksafwijking zonder reden")
        if sleutel not in met_vorm:
            fouten.append(
                f"{sleutel}: staat in AFWIJKENDE_FABRIEKEN maar heeft geen afwijkende fabriek meer"
            )
    return fouten


def _bronbestanden() -> list[str]:
    resultaat = subprocess.run(
        ["git", "grep", "-l", "-I", "-F", KLASSE, "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultaat.returncode in (0, 1), resultaat.stderr
    return sorted(r for r in resultaat.stdout.splitlines() if r.endswith(".py"))


def _echte_plekken() -> list[Plek]:
    plekken: list[Plek] = []
    for bestand in _bronbestanden():
        bron = (REPO_ROOT / bestand).read_text(encoding="utf-8")
        plekken.extend(beoordeel_bron(bestand, bron))
    return plekken


# --- de echte code -----------------------------------------------------------------------------


@pytest.mark.architecture
def test_elke_toolbroker_in_src_heeft_een_logboek_of_een_reden() -> None:
    fouten = beoordeel_alles(
        _echte_plekken(), ZONDER_LOGBOEK, ANDERE_VERWIJZINGEN, AFWIJKENDE_FABRIEKEN
    )
    assert not fouten, "ToolBrokerService zonder toollogboek:\n  " + "\n  ".join(fouten)


@pytest.mark.architecture
def test_de_scan_vindt_de_bekende_plekken() -> None:
    """Ondergrens: een scan die de plekken niet meer ziet is groen op niets."""
    gevonden = {p.sleutel for p in _echte_plekken()}
    ontbreekt = BEKENDE_PLEKKEN - gevonden
    assert not ontbreekt, f"de scan vindt deze bekende plekken niet meer: {sorted(ontbreekt)}"
    assert len(gevonden) >= len(BEKENDE_PLEKKEN)


# --- de regel zelf, op synthetische fragmenten (beide richtingen) -------------------------------

_ZONDER = "def maak():\n    return ToolBrokerService(serena_client=a, hitl_store=h)\n"
_MET_FABRIEK = "def maak():\n    return ToolBrokerService(serena_client=a, audit_session_factory=db_manager.get_session)\n"
_MET_REPO = "def maak():\n    return ToolBrokerService(audit_repository=r, db_session=d)\n"


@pytest.mark.architecture
def test_regel_een_aanroep_zonder_logboek_faalt() -> None:
    plekken = beoordeel_bron("p.py", _ZONDER)
    assert [p.sleutel for p in plekken] == ["p.py::maak"]
    assert plekken[0].gebreken


@pytest.mark.architecture
@pytest.mark.parametrize("bron", [_MET_FABRIEK])
def test_regel_een_aanroep_met_logboek_slaagt(bron: str) -> None:
    plekken = beoordeel_bron("p.py", bron)
    assert len(plekken) == 1 and not plekken[0].gebreken


@pytest.mark.architecture
def test_regel_none_is_geen_logboek() -> None:
    bron = "def maak():\n    return ToolBrokerService(audit_repository=None)\n"
    assert beoordeel_bron("p.py", bron)[0].gebreken


@pytest.mark.architecture
def test_regel_een_aanroep_over_meerdere_regels_en_via_module_wordt_gezien() -> None:
    bron = (
        "def maak():\n"
        "    return service.ToolBrokerService(\n"
        "        serena_client=a,\n"
        "        hitl_store=h,\n"
        "    )\n"
    )
    assert beoordeel_bron("p.py", bron)[0].gebreken


@pytest.mark.architecture
def test_regel_een_alias_wordt_gezien() -> None:
    bron = (
        "from src.core.tool_broker.service import ToolBrokerService as Broker\n"
        "def maak():\n    return Broker(serena_client=a)\n"
    )
    plekken = beoordeel_bron("p.py", bron)
    assert len(plekken) == 1 and plekken[0].gebreken


@pytest.mark.architecture
def test_regel_een_opmerking_of_docstring_telt_niet() -> None:
    bron = (
        'def maak():\n    """Geeft audit_repository= mee, zegt deze tekst."""\n'
        "    # audit_repository=r\n    return ToolBrokerService(serena_client=a)\n"
    )
    assert beoordeel_bron("p.py", bron)[0].gebreken


@pytest.mark.architecture
def test_regel_kwargs_en_subklasse_zijn_niet_te_beoordelen() -> None:
    assert beoordeel_bron("p.py", "def m():\n    return ToolBrokerService(**opties)\n")[0].gebreken
    sub = "class Eigen(ToolBrokerService):\n    pass\n"
    assert beoordeel_bron("p.py", sub)[0].gebreken


@pytest.mark.architecture
def test_regel_de_sleutel_is_bestand_en_functie() -> None:
    bron = "class K:\n    def _bouw(self):\n        return ToolBrokerService(x=1)\n"
    assert beoordeel_bron("a/b.py", bron)[0].sleutel == "a/b.py::_bouw"
    assert beoordeel_bron("a/b.py", "b = ToolBrokerService(x=1)\n")[0].sleutel == "a/b.py::<module>"


@pytest.mark.architecture
def test_regel_een_gedocumenteerde_uitzondering_slaagt_en_veroudert_niet_stil() -> None:
    zonder = beoordeel_bron("p.py", _ZONDER)
    assert not beoordeel_alles(zonder, {"p.py::maak": "alleen lezen, geen klant"})
    # Een uitzondering zonder reden, voor een plek die er niet meer is, of voor een plek die wel
    # een logboek meegeeft, is zelf een fout.
    assert beoordeel_alles(zonder, {"p.py::maak": "  "})
    assert beoordeel_alles(zonder, {"p.py::maak": "reden", "q.py::weg": "reden"})
    met = beoordeel_bron("p.py", _MET_FABRIEK)
    assert beoordeel_alles(met, {"p.py::maak": "reden"})


# --- N1 (Gate 2 ronde 3): de toelaatlijst en het oudere paar ------------------------------------


@pytest.mark.architecture
@pytest.mark.parametrize(
    "bron",
    [
        "def maak():\n    return ToolBrokerService(audit_repository=r)\n",
        "def maak():\n    return ToolBrokerService(audit_repository=r, db_session=d)\n",
        (
            "def maak():\n    return ToolBrokerService(audit_repository=r, db_session=d,"
            " audit_session_factory=db_manager.get_session)\n"
        ),
        "def maak():\n    return ToolBrokerService(audit_repository=None)\n",
    ],
    ids=[
        "repository_alleen",
        "repository_met_sessie",
        "repository_naast_fabriek",
        "repository_none",
    ],
)
def test_regel_audit_repository_is_in_src_altijd_een_gebrek(bron: str) -> None:
    """Het oudere paar is in `src` ongebruikt en niet toegelaten, ook niet met een sessie erbij."""
    plekken = beoordeel_bron("p.py", bron)
    assert plekken[0].gebreken
    assert any("audit_repository" in f for f in beoordeel_alles(plekken, {}))
    # Zelfs een afwijking voor de fabrieksvorm dekt dit niet.
    ok = {"p.py::maak": Uitzondering("2026-10-27", "reden")}
    assert any("audit_repository" in f for f in beoordeel_alles(plekken, {}, None, ok))


@pytest.mark.architecture
def test_regel_db_session_blijft_geldig_naast_de_fabriek() -> None:
    bron = (
        "def maak(db):\n    return ToolBrokerService(db_session=db,"
        " audit_session_factory=db_manager.get_session)\n"
    )
    plekken = beoordeel_bron("p.py", bron)
    assert not any(p.gebreken for p in plekken)


#: Elke vorm van een ontbrekende of onbruikbare fabriek. Geen daarvan staat in de toelaatlijst, dus
#: elk is rood; de scan hoeft er geen van te kennen. Eerst een letterlijke None, dan de omwegen.
ONTOEGELATEN_FABRIEKEN = {
    "letterlijke_none": "def maak():\n    return ToolBrokerService(audit_session_factory=None)\n",
    "parameterdefault_none": (
        "def maak(f=None):\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "parameterdefault_none_getypeerd": (
        "def maak(f: object = None):\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "parameter_kwonly_default_none": (
        "def maak(*, f=None):\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "conditie_met_none_direct": (
        "def maak(c):\n    return ToolBrokerService(audit_session_factory=g if c else None)\n"
    ),
    "conditie_met_none_via_naam": (
        "def maak(c, g):\n    f = g if c else None\n"
        "    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "getattr_met_default_none": (
        "def maak(db_manager):\n    return ToolBrokerService("
        'audit_session_factory=getattr(db_manager, "x", None))\n'
    ),
    "dict_get": ('def maak(d):\n    return ToolBrokerService(audit_session_factory=d.get("f"))\n'),
    "dict_opzoeking": (
        'def maak(d):\n    return ToolBrokerService(audit_session_factory=d["f"])\n'
    ),
    "module_attribuut_none": (
        "FABRIEK = None\ndef maak():\n    return ToolBrokerService(audit_session_factory=FABRIEK)\n"
    ),
    "klasse_attribuut_none": (
        "class K:\n    fabriek = None\n"
        "    def maak(self):\n        return ToolBrokerService(audit_session_factory=self.fabriek)\n"
    ),
    "klasse_attribuut_via_klasse": (
        "class K:\n    fabriek = None\n"
        "    def maak(self):\n        return ToolBrokerService(audit_session_factory=K.fabriek)\n"
    ),
    "walrus": ("def maak():\n    return ToolBrokerService(audit_session_factory=(f := None))\n"),
    "walrus_via_naam": (
        "def maak():\n    (f := None)\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "gewone_naam": "def maak(f):\n    return ToolBrokerService(audit_session_factory=f)\n",
    "aanroep_in_plaats_van_verwijzing": (
        "def maak():\n    return ToolBrokerService(audit_session_factory=db_manager.get_session())\n"
    ),
    "ander_attribuut": (
        "def maak():\n    return ToolBrokerService(audit_session_factory=db_manager.sessie)\n"
    ),
    "lambda": ("def maak():\n    return ToolBrokerService(audit_session_factory=lambda: None)\n"),
    "db_manager_lokaal_none": (
        "def maak():\n    db_manager = None\n"
        "    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
    "db_manager_parameter_default_none": (
        "def maak(db_manager=None):\n"
        "    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
    "db_manager_module_none": (
        "db_manager = None\n"
        "def maak():\n    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
}


@pytest.mark.architecture
@pytest.mark.parametrize(
    "bron", list(ONTOEGELATEN_FABRIEKEN.values()), ids=list(ONTOEGELATEN_FABRIEKEN)
)
def test_regel_elke_niet_toegelaten_fabriek_is_een_gebrek(bron: str) -> None:
    plekken = beoordeel_bron("p.py", bron)
    assert any(p.gebreken for p in plekken), "deze vorm glipt door de scan"
    assert beoordeel_alles(plekken, {}), "en dus ook door de beoordeling"


@pytest.mark.architecture
def test_regel_een_gedateerde_fabrieksafwijking_slaagt_en_veroudert_niet_stil() -> None:
    bron = ONTOEGELATEN_FABRIEKEN["gewone_naam"]
    plekken = beoordeel_bron("p.py", bron)
    ok = {"p.py::maak": Uitzondering("2026-10-27", "een testdouble die zelf de fabriek levert")}
    assert not beoordeel_alles(plekken, {}, None, ok)
    assert beoordeel_alles(plekken, {}, None, {"p.py::maak": Uitzondering("morgen", "reden")})
    assert beoordeel_alles(plekken, {}, None, {"p.py::maak": Uitzondering("2026-10-27", " ")})
    assert beoordeel_alles(plekken, {}, None, {"q.py::weg": Uitzondering("2026-10-27", "reden")})
    standaard = beoordeel_bron("p.py", _MET_FABRIEK)
    assert beoordeel_alles(standaard, {}, None, ok), "een afwijking voor de standaardvorm"
    # Een andere fout op dezelfde plek (geen fabriek meegegeven) blijft rood.
    zonder = beoordeel_bron("p.py", _ZONDER)
    assert beoordeel_alles(zonder, {}, None, ok)


@pytest.mark.architecture
def test_regel_de_toelaatlijst_is_klein_en_expliciet() -> None:
    assert TOEGELATEN_FABRIEKEN == frozenset({"db_manager.get_session"})


#: Elke omweg waarmee de aanroep buiten het bereik van de scan kon vallen (C2). Elk moet rood zijn.
OMZEILVORMEN = {
    "alias_variabele": "def maak():\n    cls = ToolBrokerService\n    return cls(audit_session_factory=f)\n",
    "functools_partial": (
        "import functools\n"
        "def maak():\n"
        "    return functools.partial(ToolBrokerService, serena_client=a)()\n"
    ),
    "getattr_op_naam": (
        'def maak(module):\n    return getattr(module, "ToolBrokerService")(audit_session_factory=f)\n'
    ),
    "attribuut_in_variabele": (
        "def maak(sv):\n    x = sv.ToolBrokerService\n    return x(audit_session_factory=f)\n"
    ),
    "fabriek_is_naam_die_none_is": (
        "def maak():\n    f = None\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "fabriek_is_getypeerde_naam_die_none_is": (
        "def maak():\n    f: object = None\n    return ToolBrokerService(audit_session_factory=f)\n"
    ),
    "fabriek_is_conditie_met_none": (
        "def maak(c):\n    return ToolBrokerService(audit_session_factory=f if c else None)\n"
    ),
    "fabriek_is_or_met_none": (
        "def maak(g):\n    return ToolBrokerService(audit_session_factory=g and None)\n"
    ),
    "dict_opzoeking": (
        'def maak():\n    return globals()["ToolBrokerService"](audit_session_factory=f)\n'
    ),
    "importpad_als_tekst": (
        "def maak():\n"
        '    return import_string("src.core.tool_broker.service.ToolBrokerService")('
        "audit_session_factory=f)\n"
    ),
    "alias_import_in_variabele": (
        "from src.core.tool_broker.service import ToolBrokerService as B\n"
        "def maak():\n    c = B\n    return c(audit_session_factory=f)\n"
    ),
}


@pytest.mark.architecture
@pytest.mark.parametrize("bron", list(OMZEILVORMEN.values()), ids=list(OMZEILVORMEN))
def test_regel_elke_omzeilvorm_is_een_gebrek(bron: str) -> None:
    plekken = beoordeel_bron("p.py", bron)
    assert any(p.gebreken for p in plekken), "deze omweg glipt door de scan"
    assert beoordeel_alles(plekken, {}), "en dus ook door de beoordeling"


#: Wat GEEN omweg is en dus groen moet blijven: precies de verwijzingen die in `src` echt voorkomen.
LEGITIEME_VERWIJZINGEN = {
    "annotaties": (
        "from typing import Optional\n"
        "class A:\n"
        "    _s: ToolBrokerService | None = None\n"
        "    def f(self, s: ToolBrokerService, t: Optional[ToolBrokerService] = None)"
        " -> ToolBrokerService: ...\n"
        '    def g(self) -> "ToolBrokerService | None": ...\n'
        "def h(*a: ToolBrokerService, **k: ToolBrokerService) -> None: ...\n"
    ),
    "isinstance": (
        "def f(x):\n    return isinstance(x, ToolBrokerService) or"
        " isinstance(x, (int, ToolBrokerService))\n"
    ),
    "import_en_docstring": (
        "from src.core.tool_broker.service import ToolBrokerService\n"
        'def f():\n    """Bouwt een ToolBrokerService; zie ToolBrokerService.execute_tool."""\n'
    ),
    "componentnaam_en_all": (
        '__all__ = ["ToolBrokerService"]\n'
        'def f(log):\n    log("ToolBrokerService", "FAILED")\n'
        '    return {"naam": "ToolBrokerService"}\n'
    ),
    "terugval_na_importfout": (
        "try:\n    from x import ToolBrokerService\nexcept ImportError:\n"
        "    ToolBrokerService = None\n"
    ),
    "toegelaten_fabriek_twee_keer": (
        "def maak(db_manager):\n"
        "    a = ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
        "    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
    "toegelaten_fabriek_via_lokale_naam": (
        "def maak(_db_mod):\n    db_manager = _db_mod.db_manager\n"
        "    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
    "none_in_andere_functie": (
        "def a():\n    db_manager = None\n    return db_manager\n"
        "def b(db_manager):\n"
        "    return ToolBrokerService(audit_session_factory=db_manager.get_session)\n"
    ),
}


@pytest.mark.architecture
@pytest.mark.parametrize(
    "bron", list(LEGITIEME_VERWIJZINGEN.values()), ids=list(LEGITIEME_VERWIJZINGEN)
)
def test_regel_legitieme_verwijzingen_blijven_groen(bron: str) -> None:
    plekken = beoordeel_bron("p.py", bron)
    assert not any(p.gebreken for p in plekken), [p for p in plekken if p.gebreken]
    assert not beoordeel_alles(plekken, {})


@pytest.mark.architecture
def test_regel_een_gedateerde_verwijzingsuitzondering_slaagt_en_veroudert_niet_stil() -> None:
    plekken = beoordeel_bron("p.py", OMZEILVORMEN["alias_variabele"])
    ok = {"p.py::maak": Uitzondering("2026-10-27", "alleen voor een test van de alias")}
    # De aanroep `cls(...)` is geen directe aanroep; de verwijzing is wat de uitzondering dekt.
    assert not [f for f in beoordeel_alles(plekken, {}, ok) if "verwijst naar" in f]
    assert beoordeel_alles(plekken, {}, {"p.py::maak": Uitzondering("morgen", "reden")})
    assert beoordeel_alles(plekken, {}, {"p.py::maak": Uitzondering("2026-10-27", "  ")})
    assert beoordeel_alles([], {}, ok), "een uitzondering voor een verwijzing die weg is"
