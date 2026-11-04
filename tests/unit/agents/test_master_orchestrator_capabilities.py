"""SP-AGT-005 Dag 3: MasterOrchestratorAgent.get_capabilities() must return real capabilities.

TDD -- tests are RED before the fix (returns []), GREEN after.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.shared.interfaces import AgentCapability


@pytest.fixture(autouse=True)
def suppress_registry_mutation():  # type: ignore[return]
    with patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
        yield


@pytest.mark.asyncio
async def test_get_capabilities_is_non_empty() -> None:
    """get_capabilities() must return at least one capability -- not an empty list."""
    agent = MasterOrchestratorAgent(agent_id="test_orch", tenant_id=1)
    caps = await agent.get_capabilities()
    assert len(caps) >= 1, (
        "MasterOrchestratorAgent.get_capabilities() still returns [] -- "
        "fill it with real AgentCapability objects (SP-AGT-005 Dag 3)."
    )


@pytest.mark.asyncio
async def test_get_capabilities_includes_workflow_orchestration() -> None:
    """get_capabilities() must include a 'workflow_orchestration' capability."""
    agent = MasterOrchestratorAgent(agent_id="test_orch", tenant_id=1)
    caps = await agent.get_capabilities()
    names = [c.name for c in caps]
    assert "workflow_orchestration" in names, (
        f"'workflow_orchestration' not found in capabilities: {names}"
    )


@pytest.mark.asyncio
async def test_get_capabilities_returns_agent_capability_instances() -> None:
    """All returned objects must be AgentCapability instances."""
    agent = MasterOrchestratorAgent(agent_id="test_orch", tenant_id=1)
    caps = await agent.get_capabilities()
    for cap in caps:
        assert isinstance(cap, AgentCapability), f"Expected AgentCapability, got {type(cap)}"
