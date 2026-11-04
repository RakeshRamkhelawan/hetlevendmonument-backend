"""GOV-002/003/005 -- autonomy ladder gedifferentieerd per agent-type
(Sprint Dag 1 Groep 3, AUDIT-ARCH-2026-07-02).

EnhancedBaseAgent hardcodede autonomy_level=HUMAN_ON_LOOP en liet risk_category op
de dataclass-default (LIMITED) staan voor ELKE agent, ongeacht agent_type/department/
specialisation. Dit maakt de governance-contract-check (GOV-001/002) een no-op voor
elke agent behalve via handmatige post-hoc mutatie.
"""

from unittest.mock import patch

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.governance.governance_contract import AutonomyLevel
from src.core.shared.ai_act_types import AIActRiskLevel
from src.core.types import AgentType


def _make_agent(**kwargs) -> EnhancedBaseAgent:
    with (
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.agents.base_agent.PromptGuard"),
        patch("src.core.agents.base_agent.OutputValidator"),
        patch("src.core.agents.base_agent.LearningMixin.__init_learning__", return_value=None),
    ):
        return EnhancedBaseAgent(
            agent_id=kwargs.pop("agent_id", "test-agent"),
            agent_type=kwargs.pop("agent_type", AgentType.SPECIALIST),
            tenant_id=kwargs.pop("tenant_id", 42),
            **kwargs,
        )


def test_high_risk_agent_gets_different_autonomy_level_than_limited_risk_agent() -> None:
    """Two agents with different department/specialisation/capabilities must get a
    different risk_category AND a different autonomy_level -- fails while both always
    get HUMAN_ON_LOOP/LIMITED regardless of agent-type (the pre-fix behavior)."""
    hr_agent = _make_agent(
        agent_id="hr-recruiter",
        department="hr",
        function="recruitment",
        capabilities=["candidate_ranking"],
    )
    docs_agent = _make_agent(
        agent_id="docs-writer",
        department="engineering",
        function="documentation",
        capabilities=["summarization"],
    )

    assert hr_agent._governance_contract is not None
    assert docs_agent._governance_contract is not None

    assert (
        hr_agent._governance_contract.risk_category != docs_agent._governance_contract.risk_category
    )
    assert (
        hr_agent._governance_contract.autonomy_level
        != docs_agent._governance_contract.autonomy_level
    )
    assert hr_agent._governance_contract.risk_category == AIActRiskLevel.HIGH_RISK
    assert docs_agent._governance_contract.risk_category == AIActRiskLevel.LIMITED


def test_high_risk_agent_requires_explicit_approval() -> None:
    """AI Act Art. 14: HIGH_RISK agents get a stricter autonomy_level (human approval
    required per-action), not the permissive HUMAN_ON_LOOP default."""
    hr_agent = _make_agent(
        agent_id="hr-recruiter",
        department="hr",
        function="recruitment",
        capabilities=["candidate_ranking"],
    )

    assert hr_agent._governance_contract is not None
    assert hr_agent._governance_contract.autonomy_level == AutonomyLevel.HUMAN_IN_LOOP


def test_ai_act_classifier_invoked_during_agent_initialization() -> None:
    """classify_agent() must actually be called during __init__, not bypassed."""
    with patch(
        "src.core.governance.ai_act_classifier.classify_agent",
        return_value=AIActRiskLevel.MINIMAL,
    ) as mock_classify:
        _make_agent(department="engineering", function="documentation", capabilities=[])

    mock_classify.assert_called_once()
