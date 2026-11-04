"""SP-API-010 backlog: architecture tests voor FA-001/FA-002/FA-003 (SP-API-009 Dag 2)
+ P2a import-linter *_router.py coverage (SP-API-010 Dag 1 stop-conditie).

Tests zijn xfail(strict=True): ze MOGEN rood zijn totdat SP-API-010 de items fixt.
Als een test onverwacht groen wordt: CI faalt -> verwijder dan de xfail marker.

  FA-001 / FA-003: lokale caches consolideren naar dependencies.py + clear_tenant_cache callers
  FA-002: stats_router cross-router imports redirecten naar dependencies.py
  P2a: import-linter Contract 1 uitbreiden naar alle *_router.py bestanden (44 violations te fixen)
"""

import ast
from pathlib import Path

import pytest


DEPENDENCIES_FILE = "src/core/api/v1/orchestration/dependencies.py"
STATS_ROUTER_FILE = "src/core/api/v1/orchestration/stats_router.py"

SIBLING_ROUTERS = [
    "health_router",
    "workflow_router",
    "critic_router",
]


def _find_callers(function_name: str, exclude_definition_file: str) -> list[str]:
    """Geeft alle src/-bestanden terug die function_name aanroepen (excl. definitie-bestand)."""
    callers = []
    for f in Path("src").rglob("*.py"):
        if str(f).replace("\\", "/") == exclude_definition_file.replace("\\", "/"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"{function_name}(" in text:
            callers.append(str(f))
    return callers


def _get_sibling_router_imports(filepath: str) -> list[str]:
    """Geeft lijst van sibling-router imports in filepath."""
    tree = ast.parse(Path(filepath).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        for sibling in SIBLING_ROUTERS:
            if module.endswith(sibling):
                found.append(module)
    return found


def test_clear_tenant_cache_has_callers_in_src() -> None:
    """TODO(SP-API-010): clear_tenant_cache() MOET worden aangeroepen vanuit tenant suspend/delete.

    Nu: geen enkele caller in src/ -- tenant-agents worden nooit geevict bij suspensie of verwijdering.
    Fix: voeg caller toe in tenant suspend/delete service en consolideer de 4 cache-dicts.
    """
    callers = _find_callers("clear_tenant_cache", DEPENDENCIES_FILE)
    assert len(callers) > 0, (
        "clear_tenant_cache() heeft geen callers in src/ -- "
        "tenant-cache wordt nooit geevict. Fix: SP-API-010 (caller toevoegen vanuit suspend/delete flow)"
    )


def test_stats_router_does_not_import_from_sibling_routers() -> None:
    """TODO(SP-API-010): stats_router mag NIET importeren van sibling routers.

    Nu: importeert get_health_monitor, get_agent_router, get_master_orchestrator
    uit health_router.py en workflow_router.py voor cache-coherentie.
    Fix: consolideer factories naar dependencies.py -- dan verdwijnen de cross-router imports.
    """
    cross_imports = _get_sibling_router_imports(STATS_ROUTER_FILE)
    assert cross_imports == [], (
        f"stats_router.py importeert van sibling routers: {cross_imports} -- "
        "Fix: SP-API-010 (factories naar dependencies.py consolideren)"
    )


def test_star_router_files_have_no_forbidden_imports() -> None:
    """TODO(SP-API-010-P2a): alle *_router.py bestanden mogen geen directe verboden imports hebben.

    SP-API-010 Dag 1 stop-conditie: P2a scan vond 44 bestanden met violations (> 20 grens).
    Fix: verplaats verboden imports naar <domein>/dependencies.py (ADR-033 par.2),
    daarna .importlinter Contract 1 uitbreiden naar alle *_router.py bestanden.
    """
    import ast

    FORBIDDEN = [
        "src.core.database",
        "src.core.governance",
        "src.core.learning",
        "src.core.agents",
        "src.core.workflow",
        "src.core.llm",
    ]
    violations: list[str] = []
    fouten: list[str] = []
    gescand = 0
    router_files = sorted(Path("src/core/api/v1").rglob("*_router.py"))
    for f in router_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{f}: {exc}")
            continue
        gescand += 1
        viols = [
            n.module
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom)
            and any((n.module or "").startswith(fb) for fb in FORBIDDEN)
        ]
        if viols:
            violations.append(f"{f}: {viols}")

    assert len(router_files) >= 100, (
        f"Slechts {len(router_files)} *_router.py bestanden gevonden onder "
        "src/core/api/v1 -- dat lijkt een (bijna) lege scan. Deze guard controleert dan "
        "vrijwel niets."
    )
    assert not fouten, (
        "Deze *_router.py bestanden konden niet gelezen/geparsed worden en zijn NIET "
        f"gecontroleerd op verboden imports (gescand: {gescand}):\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )
    assert violations == [], (
        f"TODO(SP-API-010-P2a): {len(violations)} *_router.py bestanden met verboden imports "
        "(fix door imports naar dependencies.py te verplaatsen -- ADR-033 par.2):\n"
        + "\n".join(violations[:5])
    )


@pytest.mark.unit
def test_orchestration_routers_have_no_local_caches() -> None:
    """TODO(SP-API-010): agent-caches mogen NIET lokaal in router-bestanden staan.

    Nu: critic_router, health_router en workflow_router bevatten elk eigen module-level
    cache-dicts naast de caches in dependencies.py. clear_tenant_cache() raakt deze niet.
    Fix: consolideer alle 4 cache-populaties naar dependencies.py.
    """
    router_files = [
        "src/core/api/v1/orchestration/critic_router.py",
        "src/core/api/v1/orchestration/health_router.py",
        "src/core/api/v1/orchestration/workflow_router.py",
    ]
    routers_with_local_cache = []
    for filepath in router_files:
        text = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                # Zoek naar module-level dict[int, <Agent>] annotaties
                if isinstance(node.annotation, ast.Subscript):
                    ann = ast.unparse(node.annotation)
                    if ann.startswith("dict[int,") and "Agent" in ann:
                        routers_with_local_cache.append(
                            f"{filepath}:{node.col_offset} -- {ast.unparse(node.target)}: {ann}"
                        )

    assert routers_with_local_cache == [], (
        f"Lokale agent-caches gevonden in router-bestanden: {routers_with_local_cache} -- "
        "Fix: SP-API-010 (consolideer naar dependencies.py)"
    )
