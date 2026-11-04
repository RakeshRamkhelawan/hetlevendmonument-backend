# BE-WFL-001 -- ProductionAgentRuntime AgentRouter Injectie

**Sprint:** SP-AGT-003 Dag 1
**Datum:** 2026-06-10
**Status:** IMPLEMENTED

---

## Samenvatting

`ProductionAgentRuntime.run_agent()` delegeert nu naar `AgentRouterAgent` wanneer ingejecteerd
(SP-AGT-003 P0-4 fix). Zonder injectie valt het terug op de bestaande `subagent_loader` (geen regressie).

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/agent_router_agent.py` | `run_agent()` adapter toegevoegd over `route_and_execute()` |
| `src/core/workflow/providers.py` | `__init__` accepteert `agent_router`; `run_agent()` delegeert; `FakeAgentRuntime` compatibel |
| `src/core/workflow/worker.py` | `ProviderFactory.create_agent_runtime(agent_router=None)`; `create_workflow_engine()` injecteert `get_agent_router(1)` |
| `tests/unit/workflow/test_workflow_real_routing.py` | 5 unit tests (SP-AGT-003) |

---

## Technische details

### AgentRouterAgent.run_agent()

Adapts de `IAgentRuntime.run_agent(agent_id, instruction, context)` interface naar
`route_and_execute(TaskData)`. Bouwt een `TaskData` van de parameters en converteert
`ExecutionResult` terug naar `AgentResponse` (dict).

### ProductionAgentRuntime.__init__

```python
def __init__(self, agent_router: "AgentRouterAgent | None" = None) -> None:
    self._agent_router: Any = agent_router
    ...
```

Bestaande tests die via `__new__` constructen worden beschermd door `getattr(self, "_agent_router", None)`.

### ProviderFactory.create_agent_runtime

```python
@classmethod
def create_agent_runtime(cls, agent_router: Any = None) -> IAgentRuntime:
    return cls._agent_runtime_class(agent_router=agent_router)  # type: ignore[call-arg]
```

### create_workflow_engine injectie

Deferred import (ADR-034 boundary): `get_agent_router(tenant_id=1)` -- system-level default.
Tenant_id=1 is technische schuld totdat JWT context naar workers wordt gepropageerd (SP-AGT-005).

---

## ADR-034 status

`providers.py` importeert nog steeds geen `src.core.database.database` (test 5 GROEN).
De deferred import in `worker.py` van `src.core.agents.agent_router_agent` is gedocumenteerd
als tijdelijk met NOTE-commentaar. ADR-034 Contract 2+3 re-enable target: SP-AGT-004.

---

## Tests

| Test | Status |
|------|--------|
| `test_production_agent_runtime_accepts_agent_router_parameter` | GROEN |
| `test_run_agent_delegates_to_agent_router_when_injected` | GROEN |
| `test_run_agent_falls_back_to_subagent_loader_without_agent_router` | GROEN |
| `test_create_workflow_engine_injects_agent_router` | GROEN |
| `test_providers_does_not_import_database_module` | GROEN |
| Bestaande `TestProductionAgentRuntime` (134 tests baseline) | GROEN -- 0 regressies |

---

## Bekende technische schuld

| ID | Beschrijving | Target |
|----|-------------|--------|
| TD-001 | `tenant_id=1` in worker -- geen JWT context propagatie | SP-AGT-005 |
| TD-002 | `asyncio.Lock` in AgentRouterAgent singleton niet thread-safe over Dramatiq worker-threads | SP-AGT-005 |
| TD-003 | ADR-034 Contract 2+3 nog uitgecommentarieerd in `.importlinter` | SP-AGT-004 |

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
