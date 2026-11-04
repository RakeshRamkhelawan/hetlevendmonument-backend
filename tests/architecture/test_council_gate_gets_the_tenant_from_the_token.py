"""De tenant op de Council-poort komt uit het token, niet uit iets anders (ADR-036 OP-52).

**De bevinding.** `require_council_approval(tenant_id: int, ...)` heeft in zijn docstring staan
"Resolved tenant ID (from JWT/auth context ONLY)", maar de signatuur is een kale `int`. Een
verkeerde waarde is daar geen schoonheidsfout: de Council beslist erop, en het besluit gaat
over de verkeerde klant. De registerrij noemt dit een HYPOTHESE zonder afdwinging -- geen van
de aanroepen las de tenant uit een request body, maar niets belette dat.

Bij de hermeting van 2026-08-29 bleek er wel een reele zwakte: `agentic_flow_endpoints.py`
viel terug op `current_user.id` als `tenant_id` ontbrak. Die terugval is in golf 2 vervangen
door een 403. Deze guard maakt vast dat er geen nieuwe bijkomt.

**Waarom de scan transitief is.** De oppervlakte is groter dan de negen directe aanroepen. Twee
wrappers (`execute_cva_council_gate`, `require_agent_council_approval`) geven hun EIGEN
`tenant_id`-parameter door, en `cva_service` doet hetzelfde. Een guard die alleen naar de
directe aanroep kijkt, keurt zo'n doorgeefluik goed en controleert de echte herkomst nooit.
Daarom: een functie die haar eigen parameter doorgeeft aan de poort wordt zelf een poort, en
haar aanroepers worden op dezelfde eis getoetst. Dat loopt door tot de plek waar de waarde
daadwerkelijk ontstaat.

**Wat als "uit het token" telt.**
- `current_user.tenant_id` (of een andere `<iets>.tenant_id`) -- de auth-context;
- een parameter met `Depends(get_current_tenant_id)` als default -- de FastAPI-dependency;
- een lokale variabele die uit een van die twee is toegewezen.

**Wat NIET telt.** Een letterlijke waarde, iets uit `request`/`payload`/`body`, of een
uitdrukking waarvan de herkomst hier niet te bepalen is. Bij twijfel: rood, met de vindplaats.

**Mutatietest (2026-08-30, beide richtingen):**
- In `als_tasks_router.py` `tenant_id=tenant_id` vervangen door `tenant_id=request.tenant_id`
  -> ROOD, met die regel in de melding.
- Teruggezet -> GROEN.
- `execute_cva_council_gate` uit de transitieve set gehaald (door de doorgeefdetectie uit te
  zetten) -> de aanroepers van die wrapper vallen dan buiten de scan; de vacuiteitstest op de
  poortenverzameling wordt daarop ROOD.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

#: De poort zelf. De transitieve sluiting hieronder voegt de doorgeefluiken toe.
_BASIS_POORT = "require_council_approval"

#: Objecten waarvan `.tenant_id` als auth-context telt.
#:
#: **Waarom een ALLOWLIST en geen "elk `.tenant_id`".** De eerste opzet accepteerde elk
#: attribuut met die naam. Daarmee zou `request.tenant_id` -- de tenant uit een REQUEST BODY --
#: gewoon slagen, en dat is precies de vorm die OP-52 vreest. De naam van het attribuut zegt
#: niets over de herkomst; het object waar hij op zit wel.
_AUTHCONTEXT_OBJECTEN = frozenset({"current_user", "user", "gebruiker"})

#: De dependency die de tenant uit de auth-context haalt.
_TENANT_DEPENDENCY = "get_current_tenant_id"

#: Aanroepen waarvan de herkomst bewust niet uit het token komt, met datum en reden.
KNOWN_TENANT_NIET_UIT_TOKEN: dict[str, str] = {
    "src/core/tasks/cva_tasks.py:123": (
        "2026-08-30 -- ADR-036 OP-52: dit is een dramatiq-actor, geen verzoek. Er IS geen "
        "token; `tenant_id` komt uit `request_data` (de berichtinhoud) en wordt op regel 61 "
        "in de tenantcontext gezet. Bewust hier vastgelegd in plaats van weggeredeneerd: de "
        "registerrij stelt dat GEEN enkele aanroep de tenant uit een payload leest, en dat "
        "klopt niet -- deze doet het. Of dat aanvaardbaar is hangt af van wie berichten mag "
        "inleggen, en dat is een eigen vraag (wie publiceert op deze wachtrij, en wordt de "
        "tenant daar geverifieerd?). Niet opgelost, wel zichtbaar."
    ),
}


def _bestanden() -> list[Path]:
    return [p for p in sorted(SRC.rglob("*.py")) if "alembic" not in p.parts]


def _functies(boom: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        knoop
        for knoop in ast.walk(boom)
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _aangeroepen_naam(knoop: ast.Call) -> str:
    doel = knoop.func
    return doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", "")


def _parameters_met_tenant_dependency(functie: ast.AST) -> set[str]:
    """Parameternamen met `= Depends(get_current_tenant_id)` als default.

    Positionele defaults staan RECHTS uitgelijnd in `args.defaults`; die uitlijning is de
    reden dat een naieve `zip(args, defaults)` de verkeerde parameter aanwijst zodra er ook
    maar een parameter zonder default voor staat.
    """
    gevonden: set[str] = set()
    argumenten = functie.args  # type: ignore[attr-defined]

    paren: list[tuple[ast.arg, ast.expr | None]] = []
    aantal = len(argumenten.defaults)
    if aantal:
        paren.extend(zip(argumenten.args[-aantal:], argumenten.defaults))
    paren.extend(zip(argumenten.kwonlyargs, argumenten.kw_defaults))

    for parameter, standaard in paren:
        if standaard is None:
            continue
        if not isinstance(standaard, ast.Call) or _aangeroepen_naam(standaard) != "Depends":
            continue
        for binnen in ast.walk(standaard):
            if isinstance(binnen, ast.Name) and binnen.id == _TENANT_DEPENDENCY:
                gevonden.add(parameter.arg)
    return gevonden


def _is_authcontext_uitdrukking(waarde: ast.AST) -> bool:
    """Is dit aantoonbaar `<auth-object>.tenant_id`, in attribuut- of getattr-vorm?"""
    if isinstance(waarde, ast.Attribute) and waarde.attr == "tenant_id":
        basis = waarde.value
        return isinstance(basis, ast.Name) and basis.id in _AUTHCONTEXT_OBJECTEN
    if (
        isinstance(waarde, ast.Call)
        and _aangeroepen_naam(waarde) == "getattr"
        and len(waarde.args) >= 2
        and isinstance(waarde.args[0], ast.Name)
        and waarde.args[0].id in _AUTHCONTEXT_OBJECTEN
        and isinstance(waarde.args[1], ast.Constant)
        and waarde.args[1].value == "tenant_id"
    ):
        return True
    return False


def _parameternamen(functie: ast.AST) -> set[str]:
    argumenten = functie.args  # type: ignore[attr-defined]
    namen = {p.arg for p in list(argumenten.args) + list(argumenten.kwonlyargs)}
    if argumenten.vararg:
        namen.add(argumenten.vararg.arg)
    if argumenten.kwarg:
        namen.add(argumenten.kwarg.arg)
    return namen


def _namen_uit_de_authcontext(functie: ast.AST) -> set[str]:
    """Lokale namen die aantoonbaar uit `<iets>.tenant_id` zijn toegewezen."""
    gevonden: set[str] = set()
    for knoop in ast.walk(functie):
        if not isinstance(knoop, (ast.Assign, ast.AnnAssign)):
            continue
        waarde = knoop.value
        if waarde is None:
            continue
        doelen = knoop.targets if isinstance(knoop, ast.Assign) else [knoop.target]
        bron_is_authcontext = any(
            _is_authcontext_uitdrukking(binnen) for binnen in ast.walk(waarde)
        )
        if not bron_is_authcontext:
            continue
        for doel in doelen:
            if isinstance(doel, ast.Name):
                gevonden.add(doel.id)
    return gevonden


def _index() -> tuple[list[tuple[Path, ast.AST]], list[str]]:
    """(bestand+AST-paren, paden die niet parseerden)."""
    bomen: list[tuple[Path, ast.AST]] = []
    parsefouten: list[str] = []
    for pad in _bestanden():
        try:
            bomen.append((pad, ast.parse(pad.read_text(encoding="utf-8", errors="replace"))))
        except SyntaxError:
            parsefouten.append(pad.relative_to(REPO_ROOT).as_posix())
    return bomen, parsefouten


def _poorten(bomen: list[tuple[Path, ast.AST]]) -> set[str]:
    """De poort plus elke functie die haar EIGEN tenant-parameter eraan doorgeeft."""
    poorten = {_BASIS_POORT}
    veranderd = True
    while veranderd:
        veranderd = False
        for _pad, boom in bomen:
            for functie in _functies(boom):
                if functie.name in poorten:
                    continue
                parameters = _parameternamen(functie)
                for knoop in ast.walk(functie):
                    if not isinstance(knoop, ast.Call) or _aangeroepen_naam(knoop) not in poorten:
                        continue
                    for sleutelwoord in knoop.keywords:
                        if sleutelwoord.arg != "tenant_id":
                            continue
                        waarde = sleutelwoord.value
                        if isinstance(waarde, ast.Name) and waarde.id in parameters:
                            poorten.add(functie.name)
                            veranderd = True
    return poorten


def _aanroepen_met_onbepaalde_tenant() -> list[str]:
    bomen, _parsefouten = _index()
    poorten = _poorten(bomen)
    overtreders: list[str] = []

    for pad, boom in bomen:
        for functie in _functies(boom):
            parameters = _parameternamen(functie)
            uit_dependency = _parameters_met_tenant_dependency(functie)
            uit_authcontext = _namen_uit_de_authcontext(functie)
            functie_is_poort = functie.name in poorten

            for knoop in ast.walk(functie):
                if not isinstance(knoop, ast.Call) or _aangeroepen_naam(knoop) not in poorten:
                    continue
                for sleutelwoord in knoop.keywords:
                    if sleutelwoord.arg != "tenant_id":
                        continue
                    waarde = sleutelwoord.value
                    plek = f"{pad.relative_to(REPO_ROOT).as_posix()}:{knoop.lineno}"
                    # De bekende uitzonderingen worden hier BEWUST niet overgeslagen: de
                    # staleness-test hieronder moet kunnen zien of ze nog iets uitzonderen.
                    # Het filteren gebeurt in de assertie, niet in de meting.
                    if _is_authcontext_uitdrukking(waarde):
                        continue
                    if isinstance(waarde, ast.Name):
                        if waarde.id in uit_dependency or waarde.id in uit_authcontext:
                            continue
                        if waarde.id in parameters and functie_is_poort:
                            # Doorgeefluik: de herkomst wordt bij ZIJN aanroepers getoetst.
                            continue
                    overtreders.append(f"{plek} -> {ast.unparse(waarde)}")
    return sorted(set(overtreders))


def test_the_scan_finds_the_gate_and_its_forwarders() -> None:
    """Vangnet op een EXPLICIETE verzameling, niet op "de lijst is niet leeg"."""
    bomen, _parsefouten = _index()
    poorten = _poorten(bomen)

    ontbreekt = sorted(
        {_BASIS_POORT, "execute_cva_council_gate", "require_agent_council_approval"} - poorten
    )
    assert not ontbreekt, (
        f"Deze poortfuncties zitten niet in de transitieve verzameling: {ontbreekt}. Gevonden: "
        f"{sorted(poorten)}. Zonder de doorgeefluiken toetst deze guard alleen de doorgifte en "
        "nooit de herkomst -- precies het gat dat OP-52 beschrijft."
    )


def test_all_src_files_parse() -> None:
    """Vangnet: een onparseerbaar bestand mag deze guard niet stilzwijgend blind maken.

    `_index()` sloeg een bestand met een syntaxfout stil over (`except SyntaxError:
    continue`), zonder telling. Een half samengevoegd bestand met precies het defect dat
    deze guard moet vangen -- een Council-aanroep met een onbepaalde tenant-herkomst --
    zou zo onopgemerkt blijven.
    """
    _, parsefouten = _index()
    assert not parsefouten, (
        "Deze bestanden onder src/ parseren niet en worden daardoor NIET gecontroleerd "
        "op een Council-aanroep met onbepaalde tenant-herkomst:\n"
        + "\n".join(f"  - {f}" for f in parsefouten)
    )


def test_every_gate_call_gets_its_tenant_from_the_auth_context() -> None:
    """Elke aanroep van de poort krijgt een tenant waarvan de herkomst aantoonbaar is."""
    overtreders = [
        regel
        for regel in _aanroepen_met_onbepaalde_tenant()
        if regel.split(" -> ")[0] not in KNOWN_TENANT_NIET_UIT_TOKEN
    ]

    assert not overtreders, (
        "Bij deze aanroepen van de Council-poort is niet vast te stellen dat de tenant uit de "
        "auth-context komt:\n  " + "\n  ".join(overtreders) + "\n\n"
        "De Council beslist OP deze waarde; een verkeerde tenant is een besluit over de "
        "verkeerde klant. Gebruik `current_user.tenant_id` of een parameter met "
        f"`Depends({_TENANT_DEPENDENCY})`, of zet de aanroep met datum en reden in "
        "KNOWN_TENANT_NIET_UIT_TOKEN (ADR-036 OP-52)."
    )


def test_the_known_exceptions_are_not_stale() -> None:
    """Een uitzondering die niets meer uitzondert hoort weg."""
    huidig = {plek.split(" -> ")[0] for plek in _aanroepen_met_onbepaalde_tenant()}
    verlopen = sorted(plek for plek in KNOWN_TENANT_NIET_UIT_TOKEN if plek not in huidig)

    assert not verlopen, (
        "Deze uitzonderingen in KNOWN_TENANT_NIET_UIT_TOKEN zijn niet meer nodig:\n  "
        + "\n  ".join(verlopen)
        + "\n\nHaal ze weg; anders dekt de lijst iets af wat allang is opgelost."
    )
