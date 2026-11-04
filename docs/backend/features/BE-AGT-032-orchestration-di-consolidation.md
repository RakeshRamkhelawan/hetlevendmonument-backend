# BE-AGT-032: Orchestration DI Consolidation naar dependencies.py

**ID:** BE-AGT-032
**Sprint:** SP-AGT-002 Dag 1
**ADR:** ADR-033 (3-laags router boundary) + ADR-034 (agent_runtime service boundary)
**Status:** IMPLEMENTED
**Datum:** 2026-06-09

---

## Doel

Na SP-AGT-001 hadden 4 orchestration sub-router bestanden directe `src.core.agents.*` imports
en lokale DI-factory functies. Dit brak ADR-033 Contract 1 (routers mogen geen domeinlogica
direct importeren) en creeerde duplicatie: `get_critic_agent` was gedefinieerd in zowel
`workflow_router.py` als `critic_router.py`, en `stats_router.py` importeerde uit beide sibling
sub-routers (circulaire koppeling).

Dag 1 consolideert alle orchestration DI in de ADR-033 facade laag: `dependencies.py`.

---

## Gecreeerde/gewijzigde bestanden

| Bestand | Type | Omschrijving |
|---------|------|--------------|
| `src/core/api/v1/orchestration/dependencies.py` | Herschreven | 4 agent DI factories + 4 caches + re-exports |
| `src/core/api/v1/orchestration/__init__.py` | Nieuw | Leeg -- maakt orchestration een proper Python package (grimp-vereiste) |
| `src/core/api/v1/orchestration/workflow_router.py` | Gewijzigd | Directe agents.* imports verwijderd; importeert nu via dependencies |
| `src/core/api/v1/orchestration/critic_router.py` | Gewijzigd | Directe CriticAgent import + lokale DI verwijderd |
| `src/core/api/v1/orchestration/health_router.py` | Gewijzigd | Directe AgentHealthMonitorAgent import + lokale DI verwijderd |
| `src/core/api/v1/orchestration/stats_router.py` | Herschreven | Cross-sub-router imports en directe agent imports verwijderd |
| `tests/integration/test_orchestration_api.py` | Gewijzigd | Import van `_health_monitor_cache` bijgewerkt naar `dependencies` |
| `.importlinter` | Gewijzigd | Contract 1 uitgebreid: 4 source_modules + 4 sanctioned edges |
| `tests/architecture/test_adr034_orchestration_boundary.py` | Nieuw | 6 AST-tests voor boundary enforcement |
| `tests/unit/api/orchestration/__init__.py` | Nieuw | Leeg -- package init voor unit tests |
| `tests/unit/api/orchestration/test_orchestration_dependencies.py` | Nieuw | 9 unit tests voor DI factories (4 importable + 1 cache-hit + 3 cross-tenant isolatie + 1 FA-002 401-unhappy) |

---

## Opgeloste violations

| # | Violation | Type | Bestand |
|---|-----------|------|---------|
| 1 | `from src.core.agents.agent_router_agent import AgentRouterAgent` | Directe agent import | `workflow_router.py` |
| 2 | `from src.core.agents.critic_agent import CriticAgent` | Directe agent import | `workflow_router.py` |
| 3 | `from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent` | Directe agent import | `workflow_router.py` |
| 4 | `from src.core.agents.critic_agent import CriticAgent` | Directe agent import | `critic_router.py` |
| 5 | `from src.core.agents.agent_health_monitor_agent import AgentHealthMonitorAgent` | Directe agent import | `health_router.py` |
| 6 | `from src.core.agents.health_status import HealthStatus as AgentHealthStatus` | Directe agent import | `health_router.py` |
| 7 | `from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent` | Directe agent import | `stats_router.py` |
| 8 | `from src.core.api.v1.orchestration.workflow_router import _orchestrator_cache` | Cross-sub-router import | `stats_router.py` |

---

## Implementatie: dependencies.py

Vier agent DI factories met per-tenant caching:

```python
def get_critic_agent(tenant_id: int = Depends(safe_get_tenant_id)) -> CriticAgent:
    if tenant_id not in _critic_cache:
        _critic_cache[tenant_id] = CriticAgent(agent_id=f"critic_t{tenant_id}")
    return _critic_cache[tenant_id]

def get_master_orchestrator(
    tenant_id: int = Depends(safe_get_tenant_id),
    _critic: CriticAgent = Depends(get_critic_agent),  # noqa: ARG001 -- pre-wires CriticMixin cache
) -> MasterOrchestratorAgent:
    if tenant_id not in _orchestrator_cache:
        _orchestrator_cache[tenant_id] = MasterOrchestratorAgent(
            agent_id=f"master_orchestrator_t{tenant_id}"
        )
    return _orchestrator_cache[tenant_id]
```

Sleutelbeslissingen:
- `safe_get_tenant_id` (raises HTTP 401) i.p.v. onveilige fallback-naar-1 pattern
- `get_critic_agent` gedefinieerd VOOR `get_master_orchestrator` (Python default arg evaluatie)
- Agent classes worden opnieuw geexporteerd in `__all__` zodat router type-annotaties niet breken
- `ARG001 noqa` op `_critic` parameter: pre-wires CriticMixin cache in DI graph (ADR-034 pattern)

---

## Import-linter update

Contract 1 (`api-no-domain`) uitgebreid met:
- `source_modules`: 4 orchestration sub-router bestanden expliciet toegevoegd (matchen niet via `*.router` glob)
- `ignore_imports`: 4 sanctioned edges van `dependencies -> agents.*` gedocumenteerd

**Let op:** edges zijn toegevoegd aan Contract 1 (niet Contract 6) per reviewer ISSUE-9 -- Contract 6
bewaakt `agents.api` (facade) die geen circulaire dep naar `api.*` mag hebben; de sanctioned imports
van `dependencies -> agents.*` horen bij Contract 1's `ignore_imports`.

---

## Testresultaten

| Test | Resultaat |
|------|-----------|
| `tests/architecture/test_adr034_orchestration_boundary.py` (6 tests) | 6/6 PASS |
| `tests/unit/api/orchestration/test_orchestration_dependencies.py` (8 tests) | 8/8 PASS |
| `tests/unit/agents/test_runtime_adapter.py` (10 tests) | 10/10 PASS |
| Volledige unit suite (`-n 8`) | 12708 passed, 0 failed |
| Import-linter alle contracts | 4 kept, 0 broken |


## Trainingssamenvatting

- Actor: Een HTTP endpoint handler in een orchestration sub-router (`workflow_router.py`, `critic_router.py`, `health_router.py`, `stats_router.py`).
- Voorwaarde: Het request is geauthenticeerd en bevat een geldige tenant context; de orchestration package importeert agents uitsluitend via `dependencies.py`.
- Actie (request): De handler declareert een dependency, bijvoorbeeld `orchestrator: MasterOrchestratorAgent = Depends(get_master_orchestrator)` of `router: AgentRouterAgent = Depends(get_agent_router)`.
- Systeemverwerking: `safe_get_tenant_id` leest de tenant_id uit de request context. De factory kijkt in de per-tenant cache (`_critic_cache`, `_health_monitor_cache`) of vraagt de agent singleton aan (`get_orchestrator_singleton`, `get_router_singleton`). Voor `get_master_orchestrator` en `get_agent_router` wordt eerst `_get_redis_client_fail_graceful()` aangeroepen; bij Redis-uitval wordt `None` doorgegeven zonder het request te laten falen. De agent krijgt `async_session_factory=get_db_session` en eventueel `redis_client` mee.
- Succesrespons: De handler ontvangt het gevraagde agent-object en kan de business-actie uitvoeren.
- Foutrespons: `safe_get_tenant_id` genereert HTTP 401 bij ontbrekende tenant; fouten tijdens agent-instantiatie propageren als HTTP 500 tenzij ze intern worden afgevangen.
- Uitzonderingen: Redis is een optionele cache-tier; `clear_tenant_cache()` verwijdert cache-items voor een tenant maar is niet atomair over alle caches.
