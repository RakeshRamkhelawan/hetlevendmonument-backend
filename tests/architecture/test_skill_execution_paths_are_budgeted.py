"""Architecture test: elk skill-uitvoerpad loopt door het budget (ADR-036 D10 stap 5).

Achtergrond (BE-AGT-041, 2026-08-01). Deze guard bestaat vanwege een concreet incident, niet
uit voorzorg.

`_execute_task()` deed altijd al `PranaGuard.check_budget()` en `charge_prana()`. In Fase A
dag 5 kwam er een tweede uitvoerpad bij -- `execute_with_manifest_prompt()`, om `orient()` te
omzeilen -- en dat pad nam de governance niet mee. Vanaf dat moment liep het productiepad van
de piloot (`packs.py:337`) buiten elke financiele controle en zonder tijdslimiet, zonder dat
iets dat meldde.

De les is niet "iemand vergat een aanroep" maar dat een tweede pad naast een bestaand pad
onvermijdelijk uiteenloopt zolang niets de gelijkenis afdwingt. Deze test dwingt hem af: een
methode op een skill die zelf de LLM aanroept of `act()` aanstuurt, hoort dat te doen binnen
`_run_within_budget()`.

Bewust GEEN grep maar een AST-scan: een tekstuele zoekactie mist een aanroep die over
meerdere regels is geformatteerd, en `Path.rglob` heeft niet de blinde vlek die ripgrep wel
had (zie OP-17).
"""

import ast
from pathlib import Path

SKILLS_DIR = Path("src/core/als/agents/skills")
BASE_MODULE = Path("src/core/als/agents/specialist_base.py")

BUDGET_HELPER = "_run_within_budget"

# Aanroepen die aangeven dat een methode zelf werk uitvoert in plaats van te delegeren.
WORK_MARKERS = {"_get_llm_service", "generate"}

# Methoden die bewust buiten de budget-helper vallen, met reden per regel.
# Leeg bij oplevering van BE-AGT-041: elk uitvoerpad loopt door de helper.
KNOWN_UNBUDGETED: dict[str, str] = {}


def _method_calls(node: ast.AST) -> set[str]:
    """Namen van alle aangeroepen functies/attributen binnen deze node."""
    found: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute):
            found.add(func.attr)
        elif isinstance(func, ast.Name):
            found.add(func.id)
    return found


def _executing_methods(path: Path) -> list[tuple[str, set[str]]]:
    """(methodenaam, aangeroepen namen) voor elke async methode in een skill-bestand."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    out: list[tuple[str, set[str]]] = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for item in cls.body:
            if isinstance(item, ast.AsyncFunctionDef):
                out.append((f"{path.as_posix()}::{cls.name}.{item.name}", _method_calls(item)))
    return out


def test_skill_execution_paths_run_within_budget() -> None:
    """Een skill-methode die zelf de LLM aanroept moet dat binnen het budget doen."""
    violations: list[str] = []

    for path in sorted(SKILLS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for qualname, calls in _executing_methods(path):
            if qualname in KNOWN_UNBUDGETED:
                continue
            if not (calls & WORK_MARKERS):
                continue  # delegeert of doet geen eigen werk
            if BUDGET_HELPER not in calls:
                violations.append(qualname)

    assert not violations, (
        "Deze skill-methoden voeren zelf werk uit zonder door "
        f"`{BUDGET_HELPER}()` te lopen. Zonder die helper geldt er geen tijdslimiet, geen "
        "tenant-budgetcheck en geen afrekening -- precies het gat dat het piloot-pad had "
        "tussen Fase A dag 5 en 2026-08-01:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nLaat de methode door de helper lopen, of voeg hem met datum en reden toe aan "
        "KNOWN_UNBUDGETED."
    )


def test_budget_helper_still_exists() -> None:
    """Vangnet: hernoemen van de helper mag deze guard niet stilzwijgend vacuum maken.

    Zonder deze test zou een rename van `_run_within_budget` de scan hierboven laten slagen
    voor iedereen -- de marker komt dan immers nergens meer voor, maar hij wordt ook nergens
    meer gezocht. Dat is precies hoe een guard stilletjes zijn waarde verliest.
    """
    source = BASE_MODULE.read_text(encoding="utf-8")

    assert f"async def {BUDGET_HELPER}(" in source, (
        f"`{BUDGET_HELPER}` bestaat niet meer in {BASE_MODULE}. Is hij hernoemd, werk dan "
        "BUDGET_HELPER in deze guard bij -- anders controleert hij niets meer."
    )


def test_known_unbudgeted_list_is_not_stale() -> None:
    """Een uitzondering voor een methode die niet meer bestaat is dode ballast."""
    existing = {q for p in SKILLS_DIR.glob("*.py") for q, _ in _executing_methods(p)}
    stale = sorted(set(KNOWN_UNBUDGETED) - existing)

    assert not stale, f"Deze uitzonderingen gelden methoden die niet meer bestaan: {stale}"
