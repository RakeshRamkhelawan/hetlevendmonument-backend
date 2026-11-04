"""SP-GOV-ARCH-8: persisted GovernanceContract state must be read back, not write-only.

Discovered during code review of AUDIT-ARCH-2026-07-02 Dag 3 Groep E
(SP-GOV-ARCH-7): the gatekeeper HITL approval endpoint durably persists
GovernanceContract evidence via GovernanceContractRepository, but agent
construction (src/core/agents/base_agent.py, autonomous_agent.py,
src/core/als/agents/chief_orchestrator.py) never read it back -- a fresh
GovernanceContract was built purely in-memory via classify_agent() on every
agent instantiation, so a HUMAN_IN_LOOP agent approved via that endpoint
stayed permanently blocked on its next construction.

Fixed (AUDIT-ARCH-2026-07-02 Dag 3 vervolg, Item 2): each of the 3 files now
has an async _load_persisted_governance_contract() (or, in
autonomous_agent.py, the equivalent logic inlined into the now-async
_governance_contract_for()) that reads back persisted approved_actions/
hitl_approval evidence via GovernanceContractRepository before
is_action_permitted() is evaluated, wired into each class's existing async
initialize() entry point (or, for AutonomousAgent, its per-task contract
build). This test now guards against a regression removing that wiring from
any of the 3 files.
"""

import ast
from pathlib import Path

_AGENT_CONSTRUCTION_FILES = [
    Path("src/core/agents/base_agent.py"),
    Path("src/core/agents/autonomous_agent.py"),
    Path("src/core/als/agents/chief_orchestrator.py"),
]


def _references_governance_contract_repository(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "GovernanceContractRepository":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "GovernanceContractRepository":
            return True
        # importlib-based lazy loading, same pattern as ai_act_classifier (Groep A)
        if (
            isinstance(node, ast.Constant)
            and node.value == "src.core.governance.governance_contract_repository"
        ):
            return True
    return False


def test_agent_construction_consumes_persisted_governance_contract() -> None:
    """SP-GOV-ARCH-8: all 3 agent-construction paths must load persisted HITL approvals.

    Asserts ALL THREE files, not just any one -- a regression that removes
    the read-back from a single agent class (e.g. during a future refactor
    of chief_orchestrator.py) must still fail this test, even though the
    other two classes remain correct.
    """
    consumers = [
        f for f in _AGENT_CONSTRUCTION_FILES if _references_governance_contract_repository(f)
    ]
    missing = [str(f) for f in _AGENT_CONSTRUCTION_FILES if f not in consumers]
    assert not missing, (
        f"{missing} raadple(e)gt/raadplegen GovernanceContractRepository niet -- een via "
        "/hitl/approve goedgekeurde HIGH_RISK/HUMAN_IN_LOOP agent blijft voor deze klasse "
        "op de volgende constructie alsnog permanent geblokkeerd. "
        "SP-GOV-ARCH-8: wire een read-back pad (async-aware) in agent-constructie."
    )
