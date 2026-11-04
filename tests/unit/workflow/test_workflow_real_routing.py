"""SP-AGT-003 Dag 1 -- RED tests voor AgentRouterAgent injectie in ProductionAgentRuntime.

Tests gaan van ROOD naar GROEN na de implementatie in providers.py + worker.py.
"""

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


REPO_ROOT = Path(__file__).parents[3]
PROVIDERS_PATH = REPO_ROOT / "src" / "core" / "workflow" / "providers.py"


# ---------------------------------------------------------------------------
# Test 1: ProductionAgentRuntime.__init__ accepteert agent_router parameter
# ---------------------------------------------------------------------------


def test_production_agent_runtime_accepts_agent_router_parameter() -> None:
    """ProductionAgentRuntime.__init__ moet een optionele agent_router parameter hebben."""
    from src.core.workflow.providers import ProductionAgentRuntime

    sig = inspect.signature(ProductionAgentRuntime.__init__)
    assert "agent_router" in sig.parameters, (
        "ProductionAgentRuntime.__init__ mist parameter 'agent_router'. "
        "Voeg toe: def __init__(self, agent_router=None)"
    )
    param = sig.parameters["agent_router"]
    assert param.default is None, "agent_router moet default=None hebben (optionele injectie)"


# ---------------------------------------------------------------------------
# Test 2: run_agent() delegeert naar agent_router wanneer ingejecteerd
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_delegates_to_agent_router_when_injected() -> None:
    """run_agent() moet naar agent_router.run_agent() delegeren als die ingejecteerd is."""
    from src.core.workflow.providers import ProductionAgentRuntime

    mock_router = AsyncMock()
    mock_router.run_agent.return_value = {
        "success": True,
        "result": "routed",
        "agent_id": "test_agent",
    }

    runtime = ProductionAgentRuntime(agent_router=mock_router)
    result = await runtime.run_agent(
        agent_id="analytics_agent",
        instruction="analyseer data",
        context={"tenant_id": 42},
    )

    mock_router.run_agent.assert_called_once_with(
        agent_id="analytics_agent",
        instruction="analyseer data",
        context={"tenant_id": 42},
    )
    assert result.get("success") is True


# ---------------------------------------------------------------------------
# Test 3: run_agent() valt terug op subagent_loader als geen agent_router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_falls_back_to_subagent_loader_without_agent_router() -> None:
    """run_agent() moet de subagent_loader gebruiken als agent_router=None (geen regressie)."""
    from src.core.workflow.providers import ProductionAgentRuntime

    runtime = ProductionAgentRuntime(agent_router=None)

    mock_loader = MagicMock()
    mock_loader.get_subagents_by_category.return_value = []
    mock_loader.get_all_subagents.return_value = []
    runtime.subagent_loader = mock_loader

    result = await runtime.run_agent(
        agent_id="unknown_agent",
        instruction="test",
        context={},
    )

    assert result.get("success") is False
    assert "not found" in (result.get("error") or "").lower()
    mock_loader.get_subagents_by_category.assert_called()


# ---------------------------------------------------------------------------
# Test 4: create_workflow_engine() injecteert AgentRouterAgent in de runtime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workflow_engine_injects_agent_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_workflow_engine() moet een ProductionAgentRuntime met agent_router aanmaken.

    De redis-client wordt gemockt: wat deze test meet is de INJECTIE van de router,
    niet de bereikbaarheid van een Redis-server. Een echte verbinding maakte deze test
    tijd- en machineafhankelijk (hij faalde met een connect-timeout van 0,2s zodra de
    machine onder load stond -- twee van vier suite-runs op 2026-08-16, en opnieuw
    gemeten op 2026-10-07), terwijl tests/fixtures/netwerkblokkade.py (ADR-036 OP-18)
    unittests juist geen echte verbinding laat maken. De import van get_redis_client
    gebeurt in de body van create_workflow_engine, dus het patch-doel is de BRONmodule,
    niet workflow_worker zelf.
    """
    from src.core.workflow.providers import ProductionAgentRuntime
    from src.workers.workflow_worker import create_workflow_engine

    monkeypatch.setattr(
        "src.core.database.redis.get_redis_client",
        AsyncMock(return_value=MagicMock(name="redis-client")),
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    engine = await create_workflow_engine(mock_session)

    runtime = engine.agent_runtime
    # De melding draagt de IDENTITEIT van beide klassen mee. Deze test faalde op 2026-08-16 in
    # twee van vier volledige suite-runs en slaagde los en in elke kleinere combinatie
    # (SP-COUNCIL-GATE-001, ADR-036 OP-146). Een `isinstance` kan om twee heel verschillende
    # redenen falen -- verkeerd type, of twee keer dezelfde klasse uit een herladen module --
    # en zonder deze gegevens levert een volgende keer weer geen bewijs op. De oorzaak is
    # NIET vastgesteld; dit maakt hem meetbaar.
    assert isinstance(runtime, ProductionAgentRuntime), (
        "create_workflow_engine() moet een ProductionAgentRuntime opleveren. "
        f"Gekregen: {type(runtime).__module__}.{type(runtime).__qualname__} "
        f"(id={id(type(runtime))}), verwacht {ProductionAgentRuntime.__module__}."
        f"{ProductionAgentRuntime.__qualname__} (id={id(ProductionAgentRuntime)}). "
        "Zijn de namen gelijk maar de id's niet, dan is de module herladen en gaat het om "
        "module-identiteit, niet om een verkeerd type."
    )
    assert hasattr(runtime, "_agent_router"), (
        "ProductionAgentRuntime in create_workflow_engine() moet een _agent_router attribuut hebben. "
        "Injecteer via: runtime = ProductionAgentRuntime(agent_router=get_agent_router(...))"
    )
    assert runtime._agent_router is not None, (
        "agent_router moet een echte instantie zijn, niet None. "
        "create_workflow_engine() moet get_agent_router() aanroepen en injecteren."
    )


# ---------------------------------------------------------------------------
# Test 5: providers.py importeert NOOIT src.core.database.database (ADR-034)
# ---------------------------------------------------------------------------


def test_providers_does_not_import_database_module() -> None:
    """providers.py mag src.core.database.database niet direct importeren (ADR-034)."""
    source = PROVIDERS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "src.core.database.database" in node.module:
                violations.append(f"L{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "src.core.database.database" in alias.name:
                    violations.append(f"L{node.lineno}: import {alias.name}")

    assert not violations, (
        "ADR-034 schending: providers.py importeert src.core.database.database direct:\n"
        + "\n".join(f"  {v}" for v in violations)
        + "\nGebruik session factory injectie of IAgentRepository protocol."
    )
