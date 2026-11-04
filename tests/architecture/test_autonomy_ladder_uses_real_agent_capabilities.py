"""TODO(SP-GOV-ARCH-6): GOV-002/003/005 wired ai_act_classifier.classify_agent() into
EnhancedBaseAgent.__init__() (Sprint Dag 1 Groep 3, AUDIT-ARCH-2026-07-02), but the
~120 agent classes that make up most of this codebase's agent population never get
real classification input:

- The 40 src/core/als/agents/departments/** agents (DepartmentAgent subclasses) set
  self.department_capabilities AFTER super().__init__() returns -- invisible to the
  classifier at construction time.
- The 80 src/core/agents/generated/*.py agents pass neither department, function, nor
  capabilities to their constructor at all.

TalentAcquisitionAgent (src/core/als/agents/departments/hr_culture/talent_acquisition_agent.py)
is a real Annex III.4 (HR/recruitment) system: its department_capabilities list includes
"resume_screening", which is a DIRECT HIGH_RISK_KEYWORDS match in ai_act_classifier.py.
It SHOULD classify as HIGH_RISK / HUMAN_IN_LOOP, but currently does not, because those
capabilities never reach classify_agent().

This test intentionally FAILS until department/generated agents thread their real
capability data into the classifier (either by passing capabilities= through **kwargs
before calling super().__init__(), or by re-classifying once department_capabilities
is known).
"""

from unittest.mock import patch

from src.core.governance.governance_contract import AutonomyLevel
from src.core.shared.ai_act_types import AIActRiskLevel


def _make_talent_acquisition_agent():
    from src.core.als.agents.departments.hr_culture.talent_acquisition_agent import (
        TalentAcquisitionAgent,
    )

    with (
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.agents.base_agent.PromptGuard"),
        patch("src.core.agents.base_agent.OutputValidator"),
        patch("src.core.agents.base_agent.LearningMixin.__init_learning__", return_value=None),
    ):
        return TalentAcquisitionAgent(agent_id="talent-acq-1", tenant_id=1)


def test_talent_acquisition_agent_classifies_as_high_risk() -> None:
    """TODO(SP-GOV-ARCH-6): a real Annex III HR/recruitment agent must classify
    HIGH_RISK/HUMAN_IN_LOOP -- fails while department_capabilities isn't visible to
    ai_act_classifier.classify_agent() at construction time."""
    agent = _make_talent_acquisition_agent()

    assert agent._governance_contract is not None
    assert agent._governance_contract.risk_category == AIActRiskLevel.HIGH_RISK, (
        "SP-GOV-ARCH-6 backlog not yet resolved -- TalentAcquisitionAgent's "
        "department_capabilities (includes 'resume_screening', a direct Annex III "
        "high-risk keyword) never reaches classify_agent()."
    )
    assert agent._governance_contract.autonomy_level == AutonomyLevel.HUMAN_IN_LOOP


def test_hitl_approval_has_a_production_caller() -> None:
    """TODO(SP-GOV-ARCH-7): GovernanceContract.record_hitl_approval() is the ONLY way
    to unblock a HUMAN_IN_LOOP contract (is_action_permitted() checks
    evidence['approved_actions'], populated exclusively by this method), but it has
    ZERO production callers in src/. Once SP-GOV-ARCH-6 lets a real agent classify
    HIGH_RISK/HUMAN_IN_LOOP, that agent's process_task()/delegate_task() will be
    permanently blocked with no operational path to approve it -- confirmed by both
    the code-reviewer and security-reviewer of Sprint Dag 1 Groep 3
    (AUDIT-ARCH-2026-07-02). This test fails until a real approval flow (e.g. a
    gatekeeper/HITL API endpoint) calls record_hitl_approval()."""
    import ast
    from pathlib import Path

    src_root = Path("src")
    callers = []
    for py_file in src_root.rglob("*.py"):
        if py_file == Path("src/core/governance/governance_contract.py"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "record_hitl_approval":
                callers.append(str(py_file))
                break

    assert callers, (
        "SP-GOV-ARCH-7 backlog not yet resolved -- record_hitl_approval() has no "
        "production caller. A HIGH_RISK/HUMAN_IN_LOOP agent has no way to ever be "
        "approved once SP-GOV-ARCH-6 makes real HIGH_RISK classification reachable."
    )
