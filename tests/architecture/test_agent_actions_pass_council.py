"""Architecture test: een agent-actie gaat langs de Council-poort (ADR-036 D10 stap 6 / D2).

Achtergrond (BE-AGT-042, 2026-08-02). Deze guard bestaat om een concrete reden.

`request_council_decision_for_agent()` was compleet, unit- EN integratie-getest, en had
**nul productie-aanroepers**. Precies zoals de 27 gedeclareerde tools nergens uitvoerbaar
waren en het manifest-budget nergens werd gehandhaafd: netjes gebouwd volgens specificatie,
daarna niet aangesloten, en geen symptoom dat het verraadt.

Deze test dwingt de aansluiting af. Wie `execute_tool()` aanroept vanuit de agent-laag doet
dat binnen dezelfde methode waarin ook de Council-poort staat -- anders ontstaat er een
tweede uitvoerpad dat de poort mist, en dat is letterlijk wat er gebeurde toen
`execute_with_manifest_prompt()` naast `_execute_task()` kwam te staan.

AST en geen grep: een aanroep die over meerdere regels is geformatteerd ontsnapt aan een
tekstuele zoekactie. `Path.rglob` heeft bovendien niet de blinde vlek die ripgrep had
(OP-17).

**Aangescherpt na de Gate 2-review (BE-AGT-043, 2026-08-02), drie punten:**

1. `src/core/agents` viel buiten de scan, waardoor de geerfde `EnhancedBaseAgent.execute_tool`
   onzichtbaar bleef. Alle 135 skills erven die methode, dus `self.execute_tool(...)` was een
   bypass van de hele poort die deze guard niet kon zien. Nu in scope, met een gedateerde
   uitzondering (OP-24).
2. De paden waren CWD-relatief. Draaide pytest vanuit een andere map, dan bestond geen enkele
   root, vond de scan niets en slaagde de test vacuum. Nu vanaf `__file__`.
3. De volgordetest knipte de broncode op `"async def act("` en zocht in de HELE rest van het
   bestand. Een latere methode die de markers noemt zou de test groen houden nadat de aanroep
   uit `act()` verdween. Nu via AST op de body van `act` zelf.

**OP-24 GESLOTEN (2026-08-26).** `EnhancedBaseAgent.execute_tool()` heeft nu een
initiator-eis + directe `request_council_decision_for_agent()`-aanroep (achter de
`enhanced_base_agent_initiator_check`-feature-flag, default False -- Taak 0-impact-
analyse vond geen levende externe aanroeper op de ~20 betrokken subklassen buiten de
ALS-boom). `KNOWN_UNGATED` is leeg. `COUNCIL_MARKERS` erkent zowel `_council_rejection`
(de ALS-wrapper) als `request_council_decision_for_agent` (de directe aanroep hier) als
geldig bewijs van Council-consultatie -- beide roepen uiteindelijk dezelfde onderliggende
garantie aan.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De bomen waarin een agent een tool kan uitvoeren.
#:
#: **Waarom hier drie mappen bij zijn gekomen (ADR-036 OP-24, 2026-08-30).** De scope was
#: `src/core/als/**` toen OP-24 gevonden werd, en juist daarom zag de guard `EnhancedBaseAgent`
#: zelf niet -- die staat in `src/core/agents/`. Die les geldt breder: `als/supervisors`,
#: `scheduling` en `company` bevatten klassen die van `EnhancedBaseAgent`/`SymbioticAgent`
#: erven, en een `self.execute_tool(...)` daar zou vandaag onzichtbaar zijn.
#:
#: Gemeten op 2026-08-30: in die drie mappen staat op dit moment GEEN enkele
#: `execute_tool`-aanroep. Ze staan er dus preventief in, en dat is de bedoeling -- de eerste
#: aanroep die er ooit bij komt moet meteen langs deze poort, niet pas bij de volgende audit.
AGENT_ROOTS = (
    REPO_ROOT / "src/core/als/agents",
    REPO_ROOT / "src/core/als/enterprise",
    REPO_ROOT / "src/core/als/supervisors",
    REPO_ROOT / "src/core/agents",
    REPO_ROOT / "src/core/scheduling",
    REPO_ROOT / "src/core/company",
)

BASE_MODULE = REPO_ROOT / "src/core/als/agents/specialist_base.py"

COUNCIL_MARKER = "_council_rejection"
# ADR-036 OP-24 (2026-08-26, BE-SEC-048): EnhancedBaseAgent.execute_tool() roept de
# Council-consultatie DIRECT aan (`request_council_decision_for_agent`), zonder een
# tussenliggende `_council_rejection`-achtige wrapper -- specialist_base.py se D4-002-
# floor/manifest-logica is hier niet van toepassing (geen SkillManifest op deze
# basisklasse). `request_council_decision_for_agent` is de daadwerkelijke, onderliggende
# functie die de Council-garantie biedt (dezelfde functie die `_council_rejection` zelf
# ook aanroept), dus een directe aanroep is minstens even sterk bewijs van
# Council-consultatie als de indirecte vorm. Alleen gebruikt door de generieke
# `AGENT_ROOTS`-scan hieronder -- de ALS-specifieke `test_denylist_precedes_the_council_in_act`
# blijft op de enkele `COUNCIL_MARKER` staan, want die test scant uitsluitend
# `specialist_base.py::act()`, waar de wrapper wel bestaat.
COUNCIL_MARKERS = {COUNCIL_MARKER, "request_council_decision_for_agent"}
DENYLIST_MARKER = "_reject_before_council"
EXECUTE_MARKER = "execute_tool"

# Methoden die `execute_tool` aanroepen zonder poort, met datum en reden.
KNOWN_UNGATED: dict[str, str] = {}


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def _scan_agent_root_files() -> tuple[list[tuple[str, set[str]]], list[str]]:
    """(methode-treffers, bestanden die niet parseerden) over alle AGENT_ROOTS."""
    hits: list[tuple[str, set[str]]] = []
    failures: list[str] = []
    for root in AGENT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                failures.append(_relative(path))
                continue
            for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
                for item in cls.body:
                    if not isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)):
                        continue
                    calls = _called_names(item)
                    if EXECUTE_MARKER in calls:
                        hits.append((f"{_relative(path)}::{cls.name}.{item.name}", calls))
    return hits, failures


def _methods_calling_execute_tool() -> list[tuple[str, set[str]]]:
    """(gekwalificeerde naam, aangeroepen namen) voor elke methode die execute_tool gebruikt."""
    return _scan_agent_root_files()[0]


def _act_body() -> ast.AsyncFunctionDef:
    """De AST-body van `BaseSpecialistAgent.act`, niet de rest van het bestand."""
    tree = ast.parse(BASE_MODULE.read_text(encoding="utf-8"))
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for item in cls.body:
            if isinstance(item, ast.AsyncFunctionDef) and item.name == "act":
                return item
    raise AssertionError(f"`async def act` niet gevonden in {_relative(BASE_MODULE)}")


def _first_call_line(node: ast.AST, name: str) -> int | None:
    lines = [
        child.lineno
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == name
    ]
    return min(lines) if lines else None


def test_agent_roots_exist() -> None:
    """Vangnet: een hernoemde map mag deze guard niet stilzwijgend vacuum maken."""
    missing = [str(root) for root in AGENT_ROOTS if not root.exists()]

    assert not missing, (
        f"Deze scanpaden bestaan niet: {missing}. Verplaatst of hernoemd? Werk AGENT_ROOTS "
        "bij -- anders scant deze guard niets meer en slaagt hij altijd."
    )


def test_all_agent_root_files_parse() -> None:
    """Vangnet: een onparseerbaar bestand mag deze guard niet stilzwijgend blind maken.

    De hoofdscan slaat een bestand met een syntax- of encodingfout stil over
    (`except (SyntaxError, UnicodeDecodeError)`). Een half samengevoegd bestand met
    precies het defect dat deze guard moet vangen -- een ongepoorte tooluitvoering --
    zou zo onopgemerkt blijven. Dit vangnet maakt dat luid.
    """
    _, failures = _scan_agent_root_files()
    assert not failures, (
        "Deze bestanden in AGENT_ROOTS parseren niet en worden daardoor NIET gecontroleerd "
        "op een ongepoorte tooluitvoering:\n" + "\n".join(f"  - {f}" for f in failures)
    )


def test_agent_tool_execution_passes_the_council() -> None:
    """Elke methode die een tool uitvoert, raadpleegt in diezelfde methode de Council."""
    violations: list[str] = []

    for qualname, calls in _methods_calling_execute_tool():
        if qualname in KNOWN_UNGATED:
            continue
        if not (COUNCIL_MARKERS & calls):
            violations.append(qualname)

    assert not violations, (
        "Deze methoden voeren een tool uit zonder de Council-poort in dezelfde methode. "
        "Dan ontstaat een tweede uitvoerpad dat de poort mist -- precies wat er gebeurde "
        "toen execute_with_manifest_prompt naast _execute_task kwam te staan:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nLaat de aanroep langs de poort lopen, of voeg de methode met datum en reden "
        "toe aan KNOWN_UNGATED."
    )


def test_denylist_precedes_the_council_in_act() -> None:
    """De D5-volgorde is onderdeel van het contract, niet van de opmaak.

    Zou de Council eerst oordelen, dan kan een menselijke goedkeuring een 'nooit
    aanraken'-actie alsnog doorlaten. Getoetst op de AST-body van `act` en niet op de
    tekst na `"async def act("`: die tekstvariant zocht in de hele rest van het bestand en
    zou groen blijven als een latere methode de markers toevallig noemt.
    """
    act = _act_body()

    denylist_at = _first_call_line(act, DENYLIST_MARKER)
    council_at = _first_call_line(act, COUNCIL_MARKER)

    assert denylist_at is not None, f"`{DENYLIST_MARKER}` wordt niet aangeroepen in act()"
    assert council_at is not None, f"`{COUNCIL_MARKER}` wordt niet aangeroepen in act()"

    assert denylist_at < council_at, (
        f"De harde denylist (ADR-036 D5) staat op regel {denylist_at} en de Council-poort op "
        f"{council_at}. De denylist moet EERST -- anders kan een goedkeuring een 'nooit "
        "aanraken'-actie alsnog doorlaten."
    )


def test_gate_helpers_still_exist() -> None:
    """Vangnet: hernoemen mag deze guard niet stilzwijgend vacuum maken."""
    source = BASE_MODULE.read_text(encoding="utf-8")

    for marker in (COUNCIL_MARKER, DENYLIST_MARKER):
        assert f"def {marker}(" in source, (
            f"`{marker}` bestaat niet meer in {_relative(BASE_MODULE)}. Hernoemd? Werk dan de "
            "markers in deze guard bij -- anders controleert hij niets meer."
        )


def test_known_ungated_list_is_not_stale() -> None:
    """Een uitzondering voor een methode die niet meer bestaat is dode ballast."""
    existing = {q for q, _ in _methods_calling_execute_tool()}
    stale = sorted(set(KNOWN_UNGATED) - existing)

    assert not stale, f"Deze uitzonderingen gelden methoden die niet meer bestaan: {stale}"
