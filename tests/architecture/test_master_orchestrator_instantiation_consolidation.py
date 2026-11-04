"""SP-ADR023-002 Dag 1 -- MasterOrchestratorAgent instantiatiepaden geconsolideerd.

Gevonden tijdens de onafhankelijke review van SP-ADR023-002 Dag 1 (FA-NEW-001-vervolg,
ronde 3): MasterOrchestratorAgent had dezelfde dubbele-instantiatie-bug die AgentRouterAgent
had vóór commit f852dfbc (zie BE-ADR023-001) -- twee gescheiden caches voor dezelfde klasse:

1. `src.core.agents.master_orchestrator_agent.get_master_orchestrator()` -- eigen
   `_instances`-dict, gebruikt door `src/core/api/main.py` (agent_runtime-facade bootstrap).
2. `src.core.api.v1.orchestration.dependencies.get_master_orchestrator()` -- eigen
   `_orchestrator_cache`-dict, gebruikt door de echte `/orchestration/*` HTTP-endpoints.

Een eerdere versie van deze test legde dit gat vast als ROOD (backlog-tracker). Per de
aangescherpte Laag-6-regel in `docs/agent-briefs/final-approver.md` (2026-07-03) is een
falende architectuurtest ALLEEN geen voldoende afhandeling meer -- het pre-existing issue
moet daadwerkelijk opgelost zijn. `dependencies.get_master_orchestrator()` delegeert nu
naar de singleton in `master_orchestrator_agent.py` (commit-vervolg op a6032b9e), exact
zoals `dependencies.get_agent_router()` al delegeerde naar de `AgentRouterAgent`-singleton.

Deze test is nu een permanente regressiebewaker: GROEN, en moet GROEN blijven.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_master_orchestrator_instantiation_paths_are_consolidated() -> None:
    """dependencies.get_master_orchestrator() en de master_orchestrator_agent-singleton
    moeten voor dezelfde tenant hetzelfde object retourneren -- regressietest tegen het
    heropduiken van de dubbele-cache-architectuur.

    SP-ADR023-002 Dag 2: dependencies.get_master_orchestrator() is nu `async def`
    (haalt redis_client op) -- get_redis_client wordt gemockt zodat deze unit-test
    geen echte Redis-verbinding probeert te maken."""
    import src.core.agents.master_orchestrator_agent as moa_module
    import src.core.api.v1.orchestration.dependencies as dep_module

    tenant_id = 88806
    original = moa_module._instances.pop(tenant_id, None)
    try:
        with (
            patch.object(
                moa_module.MasterOrchestratorAgent, "_register_agent_profile", return_value=None
            ),
            patch("src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())),
        ):
            from_moa_singleton = moa_module.get_master_orchestrator(tenant_id=tenant_id)
            from_dependencies = await dep_module.get_master_orchestrator(tenant_id=tenant_id)

        assert from_moa_singleton is from_dependencies, (
            "REGRESSIE: dependencies.get_master_orchestrator() en de "
            "master_orchestrator_agent-singleton retourneren weer verschillende objecten -- "
            "de dubbele-instantiatiepad-bug (SP-ADR023-002 Dag 1, FA-NEW-001-vervolg) is "
            "teruggekeerd."
        )
    finally:
        moa_module._instances.pop(tenant_id, None)
        if original is not None:
            moa_module._instances[tenant_id] = original
