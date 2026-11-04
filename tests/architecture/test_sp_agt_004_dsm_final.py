"""
SP-AGT-004 Dag 5: DSM finale -- ADR-034 boundary guards.

Bewakers die ROOD zijn voor de implementatie en GROEN na afronding.

Test 1 (ROOD voor): Contract 7 scope dekt de volledige src.core.agents package.
Test 2 (ROOD voor): Geen governance runtime-imports buiten TYPE_CHECKING in src/core/agents/.
Test 3 (altijd GROEN): DB violations in agents/ <= 11 (regressiebewaker).
Test 4 (altijd GROEN): UnifiedCapabilityRegistry operationeel (regressiebewaker).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_AGENTS_PKG = _REPO_ROOT / "src" / "core" / "agents"

# --- Test 1: Contract 7 scope ---
_IMPORTLINTER_CFG = _REPO_ROOT / ".importlinter"
_CONTRACT7_HEADER = "[importlinter:contract:agent_runtime_no_db]"

# --- Test 2: governance ceiling ---
# Bestanden in src/core/agents die NOCH governance importeren na Dag 5.
# Verwacht: 0 (na DI-fix van cva_autonomous_trigger, perfect_subagents_manager, unified_gateway).
GOV_CEILING_AGENTS = 0

# --- Test 3: DB regressiebewaker ---
# Huidig aantal DB violations in src/core/agents (baseline Dag 5, niet verhogen).
DB_REGRESSION_CEILING = 13  # +1 voor critique_store.py lazy DB-import (SP-AGT-005 Dag 1 Cat-B)
# +1 op 2026-09-16 (ADR-036 OP-153): `adapters/tenant_context.py`. Bewust in
# `adapters/`, want dat is per ADR-034 s5.5 de enige toegestane doorgang naar de
# databaselaag -- zelfde constructie als `redis_capability_cache.py`, dat al in dit
# getal zit. Reden: `seed_agent_registry.py` schrijft in `registered_agents`, en die
# tabel heeft een afschermingsregel (gemeten: relrowsecurity = t, een policy). Het
# alternatief was een uitzonderingsregel in `.importlinter` voor het script zelf; dat
# zou de grens een gat geven op een plek die GEEN adapter is.


def _is_type_checking_body(node: ast.If) -> bool:
    """Geef True als `if TYPE_CHECKING:` block (exclusie van runtime-scan)."""
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _parsed_agent_files() -> tuple[dict[Path, ast.AST], list[str]]:
    """(bestand -> AST voor elk bestand in _AGENTS_PKG, paden die niet gelezen/geparsed
    konden worden).

    Gedeeld door de twee ceiling-tests hieronder die eerder allebei onafhankelijk (en
    stil) hun eigen parse-fouten wegslikten. Bij een plafond van 0 (governance) of 12
    (database) is dat scherp: een bestand dat door een BOM niet parseert en juist een
    nieuwe verboden import bevat, verdwijnt volledig uit de telling -- en bij het
    plafond van 12 kunnen een verdwenen en een nieuwe overtreding elkaar zelfs opheffen.
    """
    bomen: dict[Path, ast.AST] = {}
    fouten: list[str] = []
    for f in _AGENTS_PKG.rglob("*.py"):
        rel = str(f.relative_to(_AGENTS_PKG)).replace("\\", "/")
        try:
            bomen[f] = ast.parse(f.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{rel}: {exc}")
    return bomen, fouten


def _get_type_checking_import_ids(tree: ast.AST) -> set[int]:
    """Collecteer ImportFrom nodes BINNEN een if TYPE_CHECKING: body (niet else-tak)."""
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_body(node):
            # Wandel alleen node.body -- NIET node.orelse (else-tak is runtime)
            for stmt in node.body:
                for child in ast.walk(stmt):
                    if isinstance(child, ast.ImportFrom):
                        excluded.add(id(child))
    return excluded


@pytest.mark.unit
def test_contract7_source_modules_expanded() -> None:
    """TODO(SP-AGT-004): Contract 7 (agent_runtime_no_db) moet de volledige
    src.core.agents package dekken -- uitbreiding van de huidige facade-only scope.

    ROOD voor Dag 5 (scope = src.core.agents.api).
    GROEN na uitbreiding van source_modules in .importlinter naar src.core.agents.
    """
    assert _IMPORTLINTER_CFG.exists(), (
        f"SP-AGT-004: .importlinter niet gevonden op {_IMPORTLINTER_CFG}"
    )
    config = _IMPORTLINTER_CFG.read_text(encoding="utf-8")
    idx = config.find(_CONTRACT7_HEADER)
    assert idx >= 0, f"Contract 7 sectie niet gevonden in {_IMPORTLINTER_CFG}"

    section = config[idx : idx + 800]

    # Gebruik regex: exacte regel "    src.core.agents" (zonder .api achtervoegsel)
    expanded = bool(re.search(r"^\s*src\.core\.agents\s*$", section, re.MULTILINE))
    assert expanded, (
        "SP-AGT-004 Dag 5: Contract 7 source_modules omvat nog geen volledige "
        "`src.core.agents` package -- breidt uit van `src.core.agents.api`.\n"
        f"Huidige sectie:\n{section}"
    )


@pytest.mark.unit
def test_dsm_gov_agents_at_zero() -> None:
    """Geen governance RUNTIME imports in src/core/agents/ na DI-reductie.

    TYPE_CHECKING imports worden uitgesloten (alleen voor type-checkers, niet runtime).
    TODO(SP-AGT-004): ROOD voor fix (3 bestanden: cva_autonomous_trigger,
    perfect_subagents_manager, unified_gateway). GROEN na DI/TYPE_CHECKING patroon.
    """
    violations: list[str] = []
    bomen, _fouten = _parsed_agent_files()
    for f, tree in bomen.items():
        rel = str(f.relative_to(_AGENTS_PKG)).replace("\\", "/")
        excluded = _get_type_checking_import_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("src.core.governance")
                and id(node) not in excluded
            ):
                violations.append(f"{rel}: {node.module}")
                break

    assert len(violations) <= GOV_CEILING_AGENTS, (
        f"SP-AGT-004 Dag 5: {len(violations)} bestanden in src/core/agents/ "
        f"bevatten governance runtime-imports (max {GOV_CEILING_AGENTS}).\n"
        "Bestanden:\n" + "\n".join(f"  {v}" for v in sorted(violations)) + "\n"
        "Fix: TYPE_CHECKING guard of Any|None DI-patroon (zie agent_registry.py Dag 4)."
    )


@pytest.mark.unit
def test_dsm_db_agents_no_regression() -> None:
    """DB violations in src/core/agents/ mogen niet toenemen boven de Dag-5 baseline.

    Regressiebewaker -- altijd GROEN. Stijging betekent ongedocumenteerde Cat-B toevoeging.
    """
    violations: list[str] = []
    bomen, _fouten = _parsed_agent_files()
    for f, tree in bomen.items():
        rel = str(f.relative_to(_AGENTS_PKG)).replace("\\", "/")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("src.core.database")
            ):
                violations.append(rel)
                break

    assert len(violations) <= DB_REGRESSION_CEILING, (
        f"SP-AGT-004 Dag 5: {len(violations)} DB violations in src/core/agents/ "
        f"(baseline was {DB_REGRESSION_CEILING} -- nieuwe Cat-B toegevoegd?).\n"
        "Files:\n" + "\n".join(f"  {v}" for v in sorted(violations))
    )


@pytest.mark.unit
def test_no_agent_file_is_silently_unparseable() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag beide plafonds hierboven niet
    blind maken. Bij een plafond van 0 verdwijnt een bestand met precies een nieuwe
    governance-import volledig uit de telling; bij een plafond van 12 kunnen een
    verdwenen en een nieuwe DB-overtreding elkaar zelfs opheffen.
    """
    _, fouten = _parsed_agent_files()
    assert not fouten, (
        "Deze bestanden in src/core/agents/ konden niet gelezen/geparsed worden en zijn "
        "NIET gecontroleerd op governance- of database-imports:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ucr_still_operational() -> None:
    """UnifiedCapabilityRegistry is importeerbaar en operationeel -- SP-AGT-004 regressie."""
    from src.core.agents.api import ICapabilityRegistry
    from src.core.agents.capability_registry import UnifiedCapabilityRegistry

    ucr = UnifiedCapabilityRegistry()
    assert isinstance(ucr, ICapabilityRegistry), (
        "SP-AGT-004: UCR voldoet niet meer aan ICapabilityRegistry Protocol"
    )
    result = await ucr.discover(query="", tenant_id=1)
    assert isinstance(result, list), "SP-AGT-004: discover() retourneerde geen list"
