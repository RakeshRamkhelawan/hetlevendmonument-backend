"""SP-AGT-003 Dag 2 -- Integration tests voor AgentRouterAgent wiring in ProductionAgentRuntime.

Verifieer dat de dag 1 unit-test guarantees ook gelden op integratieniveau:
1. create_workflow_engine() produceert een engine met een echte AgentRouterAgent (niet mock)
2. run_agent() met echte router crasht niet en retourneert een geldige AgentResponse dict

Geen echte PostgreSQL vereist voor de tests zelf -- db_session is gemockt.
Draait niet als integration conftest PostgreSQL niet detecteert (module-level skip in conftest.py).
Windows wordt geskipt vanwege ProactorEventLoop / pytest-asyncio deadlock.

ADR-034 statische regressietest (providers.py database-import) staat in:
  tests/architecture/test_adr034_orchestration_boundary.py::test_providers_py_has_no_database_import_after_dag1_wiring
"""

import sys
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Hangs on Windows ProactorEventLoop due to pytest-asyncio Runner deadlock",
)

# Isolated tenant ID voor integratietests -- geen seeded DB-data vereist
_TEST_TENANT_ID = 9990


@pytest.mark.asyncio
async def test_create_workflow_engine_produces_wired_runtime() -> None:
    """create_workflow_engine() moet een engine produceren met een echte AgentRouterAgent-instantie."""
    from src.core.agents.agent_router_agent import AgentRouterAgent
    from src.workers.workflow_worker import create_workflow_engine

    mock_session = AsyncMock()
    engine = await create_workflow_engine(mock_session)

    assert engine.agent_runtime._agent_router is not None, (
        "agent_router is None -- create_workflow_engine() injecteert get_agent_router() niet"
    )
    assert isinstance(engine.agent_runtime._agent_router, AgentRouterAgent), (
        f"agent_router is geen AgentRouterAgent maar {type(engine.agent_runtime._agent_router)}"
    )


@pytest.mark.asyncio
async def test_run_agent_with_real_router_returns_dict() -> None:
    """run_agent() met echte AgentRouterAgent (geen mocks) retourneert een dict met 'success' key."""
    from src.core.agents.agent_router_agent import get_agent_router
    from src.core.workflow.providers import ProductionAgentRuntime

    router = get_agent_router(tenant_id=_TEST_TENANT_ID)
    runtime = ProductionAgentRuntime(agent_router=router)

    result = await runtime.run_agent(
        agent_id="test_agent",
        instruction="test instructie voor integratie",
        context={},
    )

    assert isinstance(result, dict), f"run_agent() retourneert geen dict maar {type(result)}"
    assert "success" in result, (
        f"run_agent() retourneert dict zonder 'success' key: {result.keys()}"
    )
