"""TODO(SP-GOV-ARCH-2): AutonomousAgent/ChiefOrchestrator governance contracts are
hardcoded to AutonomyLevel.HUMAN_ON_LOOP + the GovernanceContract default risk_category
(AIActRiskLevel.LIMITED). Per governance_contract.py:42-56, that combination always
falls through to `is_action_permitted() -> True` -- the call-site check added in
Sprint Dag 1 Groep 1 (AUDIT-ARCH-2026-07-02) wires the gate correctly but it cannot
yet actually deny anything for these two agent classes.

Groep 3 of the same sprint wires `ai_act_classifier.classify_agent()` into
base_agent.py (EnhancedBaseAgent) to differentiate risk per agent-type -- this
backlog item extends that same treatment to AutonomousAgent and ChiefOrchestrator,
which are separate classes not covered by that scope.

This test intentionally FAILS until both modules derive autonomy_level/risk_category
from ai_act_classifier.classify_agent() instead of a hardcoded default.
"""

import inspect

from src.core.agents import autonomous_agent as autonomous_agent_module
from src.core.als.agents import chief_orchestrator as chief_orchestrator_module


def test_autonomous_agent_derives_risk_category_from_ai_act_classifier() -> None:
    source = inspect.getsource(autonomous_agent_module)
    assert "ai_act_classifier" in source, (
        "AutonomousAgent's GovernanceContract is hardcoded to HUMAN_ON_LOOP/LIMITED, which "
        "always permits every action -- it must derive autonomy_level/risk_category from "
        "ai_act_classifier.classify_agent() (SP-GOV-ARCH-2 backlog)."
    )


def test_chief_orchestrator_derives_risk_category_from_ai_act_classifier() -> None:
    source = inspect.getsource(chief_orchestrator_module)
    assert "ai_act_classifier" in source, (
        "ChiefOrchestrator's GovernanceContract is hardcoded to HUMAN_ON_LOOP/LIMITED, which "
        "always permits every action -- it must derive autonomy_level/risk_category from "
        "ai_act_classifier.classify_agent() (SP-GOV-ARCH-2 backlog)."
    )
