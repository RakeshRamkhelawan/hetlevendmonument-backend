"""TDD tests voor GovernanceContract klasse -- SP-DLP-002 Dag 1 (ADR-031)."""

import pytest

from src.core.shared.ai_act_types import AIActRiskLevel


def test_governance_contract_class_exists():
    from src.core.governance.governance_contract import GovernanceContract

    assert GovernanceContract is not None


def test_governance_contract_autonomy_level_not_stub():
    from src.core.governance.governance_contract import GovernanceContract

    contract = GovernanceContract(agent_id="test-agent", tenant_id=1)
    level = contract.autonomy_level
    assert level != "stub_phase4", f"autonomy_level is still a stub: {level!r}"
    assert level in ("HUMAN_IN_LOOP", "HUMAN_ON_LOOP", "HUMAN_OUT_OF_LOOP", "ADVISORY"), (
        f"Unexpected autonomy level: {level!r}"
    )


def test_governance_contract_requires_agent_id():
    from src.core.governance.governance_contract import GovernanceContract

    with pytest.raises((TypeError, ValueError)):
        GovernanceContract(tenant_id=1)  # type: ignore[call-arg]


def test_governance_contract_has_risk_category():
    from src.core.governance.governance_contract import GovernanceContract

    contract = GovernanceContract(agent_id="test-agent", tenant_id=1)
    assert hasattr(contract, "risk_category")
    assert contract.risk_category in AIActRiskLevel


def test_governance_contract_advisory_never_permitted():
    from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract

    contract = GovernanceContract(
        agent_id="test-agent",
        tenant_id=1,
        autonomy_level=AutonomyLevel.ADVISORY,
    )
    assert not contract.is_action_permitted("send_email"), "ADVISORY mag nooit acties uitvoeren"


def test_governance_contract_unacceptable_never_permitted():
    from src.core.governance.governance_contract import GovernanceContract

    contract = GovernanceContract(
        agent_id="test-agent",
        tenant_id=1,
        risk_category=AIActRiskLevel.UNACCEPTABLE,
    )
    assert not contract.is_action_permitted("any_action")
