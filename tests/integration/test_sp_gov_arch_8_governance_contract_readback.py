"""SP-GOV-ARCH-8: agent construction reads back a persisted GovernanceContract.

Proves the actual behavior fixed by base_agent.py's
_load_persisted_governance_contract(): a HITL approval persisted via
GovernanceContractRepository.save() (the same mechanism the
/hitl/approve endpoint uses) must be picked up on the agent's NEXT
construction, not just live in the approving request's in-memory
contract. Before this fix, a HUMAN_IN_LOOP agent that got approved stayed
permanently blocked because agent construction only ever built a fresh
in-memory contract via classify_agent().
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.database.database import db_manager
from src.core.governance.governance_contract import AutonomyLevel
from src.core.governance.governance_contract_repository import GovernanceContractRepository
from src.core.types import AgentType

_AGENT_ID = "sp-gov-arch-8-readback-test-agent"
_ACTION = "score_credit_application"
_ISOLATION_AGENT_ID = "sp-gov-arch-8-isolation-test-agent"


def _make_agent(tenant_id: int, agent_id: str = _AGENT_ID) -> EnhancedBaseAgent:
    with (
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.agents.base_agent.PromptGuard"),
        patch("src.core.agents.base_agent.OutputValidator"),
        patch("src.core.agents.base_agent.LearningMixin.__init_learning__", return_value=None),
    ):
        return EnhancedBaseAgent(
            agent_id=agent_id,
            agent_type=AgentType.RESEARCH,
            tenant_id=tenant_id,
            # "credit_scoring" is a direct Annex III high-risk keyword match
            # (ai_act_classifier.HIGH_RISK_KEYWORDS) -- guarantees a
            # deterministic HIGH_RISK -> HUMAN_IN_LOOP classification.
            capabilities=["credit_scoring"],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hitl_approval_survives_agent_reconstruction(
    integration_app, test_tenant_id: int
) -> None:
    """A HITL-approved action stays permitted after the agent is reconstructed."""
    try:
        agent_before = _make_agent(test_tenant_id)
        assert agent_before._governance_contract is not None
        assert agent_before._governance_contract.autonomy_level == AutonomyLevel.HUMAN_IN_LOOP

        await agent_before.initialize()
        assert agent_before._governance_contract.is_action_permitted(_ACTION) is False

        # Approve directly via the repository -- same mechanism as
        # /hitl/approve. Uses db_manager.get_session() (NOT the
        # rolled-back-per-test db_session fixture) because the write must be
        # visible to the agent's own db_manager.get_session() read-back --
        # db_session's transaction never commits, so a separate connection
        # would never see it.
        async with db_manager.get_session() as db:
            repo = GovernanceContractRepository(db, test_tenant_id)
            contract = await repo.load_or_create(_AGENT_ID)
            contract.record_hitl_approval(approved_by="admin@example.com", action=_ACTION)
            await repo.save(contract)

        agent_after = _make_agent(test_tenant_id)
        await agent_after.initialize()

        assert agent_after._governance_contract is not None
        assert agent_after._governance_contract.is_action_permitted(_ACTION) is True
    finally:
        async with db_manager.get_session() as db:
            await db.execute(
                text(
                    "DELETE FROM agent_governance_contracts "
                    "WHERE agent_id = :agent_id AND tenant_id = :tenant_id"
                ),
                {"agent_id": _AGENT_ID, "tenant_id": test_tenant_id},
            )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readback_does_not_leak_approval_across_tenants(
    integration_app, test_tenant_id: int
) -> None:
    """A different tenant sharing the same agent_id must NOT see tenant A's approval.

    GovernanceContractRepository.load() filters on (tenant_id, agent_id), but
    this test proves that guarantee holds through the full agent-construction
    read-back path added by SP-GOV-ARCH-8, not just at the repository layer
    directly (matching this project's isolatietest convention for repository
    consumers).
    """
    other_tenant_id = 2  # seeded by reset_db_per_module ("Other Tenant")
    try:
        async with db_manager.get_session() as db:
            repo = GovernanceContractRepository(db, test_tenant_id)
            contract = await repo.load_or_create(_ISOLATION_AGENT_ID)
            contract.record_hitl_approval(approved_by="admin@example.com", action=_ACTION)
            await repo.save(contract)

        agent_other_tenant = _make_agent(other_tenant_id, agent_id=_ISOLATION_AGENT_ID)
        await agent_other_tenant.initialize()

        assert agent_other_tenant._governance_contract is not None
        assert agent_other_tenant._governance_contract.is_action_permitted(_ACTION) is False
    finally:
        async with db_manager.get_session() as db:
            await db.execute(
                text("DELETE FROM agent_governance_contracts WHERE agent_id = :agent_id"),
                {"agent_id": _ISOLATION_AGENT_ID},
            )
