"""Architecture-guard tests -- AGENT_ENTRYPOINT_ACTIONS (18-failures fix, Oorzaak 2).

Rode tests totdat PolicyEngine.AGENT_ENTRYPOINT_ACTIONS bestaat. Deze constante staat
los van DEFAULT_ALLOW_ACTIONS (dat "veilige read-only ops" betekent) en mag NOOIT
destructieve eindacties bevatten -- de echte gevaarlijke sub-acties lopen via
OversightGate.BREAKTHROUGH_ACTIONS en de EU AI Act risk-classificatie, niet via deze lijst.
"""

from __future__ import annotations

import pytest

from src.core.governance.oversight_gate import OversightGate
from src.core.governance.policy_engine import PolicyEngine

EXPECTED_AGENT_ENTRYPOINT_ACTIONS = {
    "process_task",
    "orchestrate_task",
    "breakthrough_session",
    "execute_workflow",
    "create_and_execute",
    "stream_execution",
    "delegate_sub_task",
    # SP-GOV-ENTRYPOINT-AUDIT, besluit Rakesh 2026-07-31 (OP-11 dag 2): zes namen
    # toegevoegd die stil deny-by-default werden geweigerd. Motivatie per naam staat
    # bij de constante in src/core/governance/policy_engine.py; de scan die garandeert
    # dat er geen ongeklassificeerde namen meer zijn staat in
    # tests/unit/test_policy_engine_entrypoint_classification.py.
    "route_task",
    "critique_output",
    "route_and_execute",
    "execute_specialist",
    "start_swarm",
    "autonomous_breakthrough",
}

DESTRUCTIVE_SUBSTRINGS = (
    "delete",
    "remove",
    "drop",
    "deploy",
    "migrate",
    "write",
    "payment",
)


@pytest.mark.unit
def test_agent_entrypoint_actions_are_dispatch_only() -> None:
    """AGENT_ENTRYPOINT_ACTIONS moet exact de 7 verwachte dispatch-verba bevatten --
    geen minder, geen meer, tenzij een PR de lijst expliciet uitbreidt en deze test
    meegroeit."""
    assert set(PolicyEngine.AGENT_ENTRYPOINT_ACTIONS) == EXPECTED_AGENT_ENTRYPOINT_ACTIONS


@pytest.mark.unit
def test_agent_entrypoint_actions_disjoint_from_breakthrough_actions() -> None:
    """AGENT_ENTRYPOINT_ACTIONS mag nooit een naam bevatten die ook in
    OversightGate.BREAKTHROUGH_ACTIONS staat -- dispatch-toestemming mag nooit
    impliciet een destructieve breakthrough-actie goedkeuren."""
    overlap = set(PolicyEngine.AGENT_ENTRYPOINT_ACTIONS) & OversightGate.BREAKTHROUGH_ACTIONS
    assert overlap == set(), (
        f"AGENT_ENTRYPOINT_ACTIONS overlapt met BREAKTHROUGH_ACTIONS: {overlap}"
    )


@pytest.mark.unit
def test_agent_entrypoint_actions_no_destructive_verbs() -> None:
    """Geen naam in AGENT_ENTRYPOINT_ACTIONS mag een destructief/schrijvend
    patroon bevatten -- dit is de vangrail tegen toekomstige scope-kruip van de lijst."""
    for action_name in PolicyEngine.AGENT_ENTRYPOINT_ACTIONS:
        lowered = action_name.lower()
        for pattern in DESTRUCTIVE_SUBSTRINGS:
            assert pattern not in lowered, (
                f"AGENT_ENTRYPOINT_ACTIONS bevat '{action_name}', dat het destructieve "
                f"patroon '{pattern}' matcht. Destructieve acties horen via "
                f"OversightGate.BREAKTHROUGH_ACTIONS te lopen, niet via deze dispatch-only lijst."
            )
