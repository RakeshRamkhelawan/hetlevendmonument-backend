"""Tracking-architecture-tests voor bevindingen die tijdens de Gate-2-review van de
18-failures-fix (2026-07) zijn gevonden maar BEWUST buiten scope van die fix bleven.

Deze tests zijn ROOD zolang de onderliggende gaten bestaan -- conform
.claude/rules/quality-gates.md ("elke FA-bevinding die niet direct gefixed wordt,
VEREIST een falende architecture test in dezelfde commit"). Ze zijn geen backlog-notitie
zonder gevolg: zolang ze rood staan, is dit zichtbaar in elke suite-run.

Update 2026-07-09: het duplicate-_execute_task-gat in code_agent.py/research_agent.py
is inmiddels gefixed (elders, buiten deze test) -- test_agent_has_exactly_one_execute_task_definition
is niet langer xfail. Het task_action-classificatiegat hieronder staat nog open.

Update 2026-07-31 (OP-11 dag 2): SP-GOV-ENTRYPOINT-AUDIT is AFGEROND. Rakesh heeft alle
zeven gevonden task_action-strings geclassificeerd als toegestane dispatch-actie; zes zijn
toegevoegd aan AGENT_ENTRYPOINT_ACTIONS en `stream` is op de call-site omgenoemd naar het
al bestaande `stream_execution`. De xfail-marker is daarom verwijderd: deze test is nu een
echte, groene guard. De live scan vond overigens zeven namen, niet de zes uit de originele
docstring -- `route_and_execute` was gemist.

Deze test blijft een onafhankelijke buitenboord-check met een HANDMATIGE kopie van de
allowlist. Complementair daaraan leest
tests/unit/test_policy_engine_entrypoint_classification.py de echte constanten uit, en
legt die het restrisico rond `autonomous_breakthrough` vast (start zonder menselijke
trigger; bewust geaccepteerd besluit).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

# Bestanden met het IDENTIEKE duplicate-_execute_task-patroon als
# executor_agent.py/security_agent.py/external_agent_bridge.py (18-failures fix) --
# beide inmiddels elders gefixed (elk precies 1 `_execute_task` nu). analyzer/agent.py
# en cva/agent.py zijn structureel anders (cva/agent.py heeft geen process_task om ooit
# naar te delegeren) en vallen buiten deze specifieke test.
FILES_WITH_KNOWN_DUPLICATE_EXECUTE_TASK = {
    "src/core/agents/code_agent.py": "CodeAgent",
    "src/core/agents/research_agent.py": "ResearchAgent",
}

# Reeds bekende, veilige action-namen (moeten in sync blijven met de echte constanten --
# bewust hier als losse kopie zodat deze test niet zelf de bron-van-waarheid wordt, maar
# een onafhankelijke buitenboord-check blijft).
KNOWN_SAFE_TASK_ACTIONS = {
    "process_task",
    "orchestrate_task",
    "breakthrough_session",
    "execute_workflow",
    "create_and_execute",
    "stream_execution",
    "delegate_sub_task",
    # SP-GOV-ENTRYPOINT-AUDIT afgerond -- besluit Rakesh 2026-07-31 (OP-11 dag 2).
    # Motivatie per naam staat bij PolicyEngine.AGENT_ENTRYPOINT_ACTIONS.
    "route_task",
    "critique_output",
    "route_and_execute",
    "execute_specialist",
    "start_swarm",
    "autonomous_breakthrough",
    "query",
    "analyze",
    "respond",
    "search",
    "retrieve",
    "list",
    "get",
    "read",
    "code_generation",
    "file_creation",
    "database_migration",
    "deployment",
    "config_change",
    "permission_change",
}

TASK_ACTION_LITERAL_RE = re.compile(r'task_action\s*=\s*"([a-zA-Z_][a-zA-Z0-9_]*)"')


def _count_method_defs(file_path: Path, class_name: str, method_name: str) -> int:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                ):
                    count += 1
    return count


@pytest.mark.unit
@pytest.mark.parametrize(
    ("relative_path", "class_name"),
    sorted(FILES_WITH_KNOWN_DUPLICATE_EXECUTE_TASK.items()),
)
def test_agent_has_exactly_one_execute_task_definition(relative_path: str, class_name: str) -> None:
    """Beide bestanden zijn inmiddels gefixed (niet meer xfail): CodeAgent en
    ResearchAgent hebben elk precies 1 `_execute_task`-definitie, identiek aan de
    18-failures-fix van executor_agent.py/security_agent.py/external_agent_bridge.py."""
    file_path = REPO_ROOT / relative_path
    assert file_path.exists(), f"Verwacht bestand niet gevonden: {relative_path}"

    count = _count_method_defs(file_path, class_name, "_execute_task")
    assert count == 1, (
        f"{relative_path}::{class_name} heeft {count} definities van `_execute_task` "
        f"(verwacht: 1). Een dubbele naam betekent dat Python stilzwijgend de eerste "
        f"definitie overschrijft met de tweede -- zie TODO(SP-GOV-ENTRYPOINT-AUDIT)."
    )


@pytest.mark.unit
def test_no_unclassified_task_action_strings_in_src() -> None:
    """ROOD zolang er `task_action="..."`-literals in src/ voorkomen die noch in
    AGENT_ENTRYPOINT_ACTIONS, noch in DEFAULT_ALLOW_ACTIONS, noch in
    OversightGate.BREAKTHROUGH_ACTIONS staan. Zulke acties worden vandaag stil
    DENY-BY-DEFAULT geweigerd door PolicyEngine -- als dat onbedoeld is, is dit een
    live productiegat, niet alleen een test-mismatch.

    TODO(SP-GOV-ENTRYPOINT-AUDIT): Rakesh-besluit nodig per gevonden actie: toevoegen
    aan een bestaande allowlist, of bevestigen dat de deny-by-default terecht is.
    Bekend bij het schrijven van deze test (2026-07): execute_specialist, route_task,
    critique_output, start_swarm, stream (mismatch met de test-naam stream_execution),
    autonomous_breakthrough (mismatch met de test-naam breakthrough_session)."""
    unclassified: set[str] = set()
    for py_file in SRC_ROOT.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in TASK_ACTION_LITERAL_RE.finditer(text):
            action_name = match.group(1)
            if action_name not in KNOWN_SAFE_TASK_ACTIONS:
                unclassified.add(action_name)

    assert unclassified == set(), (
        "Ongeklassificeerde task_action-strings gevonden in src/ (niet in een bekende "
        f"allowlist): {sorted(unclassified)}. Zie TODO(SP-GOV-ENTRYPOINT-AUDIT) in dit "
        "testbestand voor de vereiste vervolgstap."
    )
