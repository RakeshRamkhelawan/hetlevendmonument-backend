"""SP-GOV-ENTRYPOINT-AUDIT: elke task_action-literal in src/ moet geclassificeerd zijn.

Achtergrond (OP-11 dag 2, 2026-07-31):
- PolicyEngine.validate_action weigert onbekende acties deny-by-default (stap 8).
  Dat is correct als vangnet, maar zeven `task_action="..."`-literals in src/ stonden
  in geen enkele allowlist. Die dispatch-paden gaven daardoor stil 403 --
  `POST /api/v1/orchestrate/route` en `/critique` waren in productie onbruikbaar,
  zichtbaar in 7 rode integratietests die niemand draaide.
- De namen stonden sinds 2026-07 als openstaand gat in
  tests/unit/test_governance_entrypoint_gaps_tracked.py met
  TODO(SP-GOV-ENTRYPOINT-AUDIT): expliciet Rakesh-besluit vereist voor elke naam.

Besluit Rakesh 2026-07-31 (in chat, OP-11 dag 2): alle zeven gevonden acties worden
geclassificeerd als toegestane dispatch-actie. Zes namen zijn toegevoegd aan
AGENT_ENTRYPOINT_ACTIONS; `stream` is een naam-mismatch en is op de call-site
omgenoemd naar het al bestaande `stream_execution`.

RESTRISICO, expliciet vastgelegd op verzoek: `autonomous_breakthrough` is de enige
actie die start ZONDER menselijke trigger (src/core/agents/cva_autonomous_trigger.py).
Rakesh heeft die bewust meegenomen terwijl de autonomie-ladder uit ADR-031 nog niet
gewired is. De diepere poorten blijven onverminderd van kracht: AI Act-risicoclassificatie
(ai_act_classifier.classify_agent), OversightGate.BREAKTHROUGH_ACTIONS (human approval
voor code_generation/file_creation/database_migration/deployment/config_change/
permission_change) en de ShadowCEO-veto. Deze lijst geeft alleen toegang tot het
STARTEN van een pad, niet tot een destructieve eindoperatie.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.governance.oversight_gate import OversightGate
from src.core.governance.policy_engine import (
    ActionContext,
    PolicyEngine,
    PolicyRiskLevel,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
TASK_ACTION_LITERAL_RE = re.compile(r'task_action\s*=\s*"([a-zA-Z_][a-zA-Z0-9_]*)"')

# De zeven acties uit de audit, met hun call-site en waarom ze zijn toegestaan.
CLASSIFIED_ACTIONS = {
    "route_task": "read-only: kiest een agent, voert niets uit",
    "critique_output": "read-only: beoordeelt output, geeft score/issues",
    "route_and_execute": "dispatch: zelfde vorm als create_and_execute; doelagent doet eigen check",
    "execute_specialist": "dispatch: zelfde vorm als delegate_sub_task",
    "start_swarm": "dispatch: fan-out naar meerdere agents (budget/staplimiet = ADR-036 Fase 2)",
    "autonomous_breakthrough": "dispatch zonder menselijke trigger -- besluit Rakesh 2026-07-31",
    "stream_execution": "dispatch: streamt een agent-executie (call-site `stream` omgenoemd)",
}


def _unclassified_task_actions() -> set[str]:
    """Alle task_action-literals in src/ die in geen enkele allowlist staan."""
    allowed = (
        set(PolicyEngine.AGENT_ENTRYPOINT_ACTIONS)
        | set(PolicyEngine.DEFAULT_ALLOW_ACTIONS)
        | set(OversightGate.BREAKTHROUGH_ACTIONS)
    )
    found: set[str] = set()
    for py_file in SRC_ROOT.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in TASK_ACTION_LITERAL_RE.finditer(text):
            if match.group(1) not in allowed:
                found.add(match.group(1))
    return found


@pytest.mark.unit
def test_no_unclassified_task_action_literals_in_src() -> None:
    """Geen enkele task_action-literal mag stil deny-by-default worden geweigerd."""
    unclassified = _unclassified_task_actions()
    assert unclassified == set(), (
        "Ongeklassificeerde task_action-strings in src/: "
        f"{sorted(unclassified)}. Deze paden geven stil 403 (PolicyEngine stap 8, "
        "deny-by-default). Elke nieuwe naam vereist een expliciet besluit: toevoegen "
        "aan een allowlist, of de deny bevestigen en de call-site aanpassen. Zie "
        "SP-GOV-ENTRYPOINT-AUDIT."
    )


@pytest.mark.unit
@pytest.mark.parametrize("action_name", sorted(CLASSIFIED_ACTIONS))
@pytest.mark.asyncio
async def test_classified_action_passes_policy_engine(action_name: str) -> None:
    """Elke geclassificeerde actie moet de PolicyEngine daadwerkelijk passeren."""
    engine = PolicyEngine()
    result = await engine.validate_action(
        ActionContext(
            action_name=action_name,
            parameters={},
            risk_level=PolicyRiskLevel.LOW,
            tenant_id="1",
        )
    )
    assert result.allowed, (
        f"Actie '{action_name}' ({CLASSIFIED_ACTIONS[action_name]}) wordt geweigerd: "
        f"{result.reason}"
    )


@pytest.mark.unit
def test_stream_call_site_uses_the_classified_name() -> None:
    """De call-site moet `stream_execution` gebruiken, niet de mismatch `stream`."""
    websocket_module = SRC_ROOT / "core" / "api" / "v1" / "agentic" / "websocket.py"
    text = websocket_module.read_text(encoding="utf-8")
    assert 'task_action="stream_execution"' in text, (
        'src/core/api/v1/agentic/websocket.py moet task_action="stream_execution" '
        "gebruiken; de losse naam `stream` stond in geen enkele allowlist en werd stil "
        "geweigerd."
    )
    assert 'task_action="stream"' not in text, (
        'De oude mismatch task_action="stream" staat er nog -- die wordt deny-by-default geweigerd.'
    )


@pytest.mark.unit
def test_autonomous_breakthrough_deeper_gates_remain_intact() -> None:
    """Restrisico-guard: de diepere poorten mogen niet meeverruimd zijn.

    autonomous_breakthrough mag het pad STARTEN (besluit Rakesh 2026-07-31), maar de
    destructieve eindoperaties moeten human approval blijven vereisen. Als iemand later
    een van deze namen uit BREAKTHROUGH_ACTIONS haalt, faalt deze test.
    """
    required_breakthrough_gates = {
        "code_generation",
        "file_creation",
        "database_migration",
        "deployment",
        "config_change",
        "permission_change",
    }
    missing = required_breakthrough_gates - set(OversightGate.BREAKTHROUGH_ACTIONS)
    assert not missing, (
        f"BREAKTHROUGH_ACTIONS mist {sorted(missing)}. Die poort is de enige die "
        "destructieve eindoperaties achter human approval houdt nu "
        "autonomous_breakthrough het startpad mag passeren."
    )
