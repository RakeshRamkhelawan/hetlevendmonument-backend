# BE-API-033: import-linter Contract 1 -- api-no-domain

**ID:** BE-API-033
**Sprint:** SP-API-009 Dag 2
**Status:** DONE
**Datum:** 2026-06-11

## Beschrijving

Fix van ADR-033 criterium 2: import-linter contract `api-no-domain` stond BROKEN door
8 directe imports van `src.core.agents.*` in 4 orchestration router bestanden. Na deze
fix tonen alle 4 contracts de status KEPT.

## Wat gewijzigd

- `src/core/api/v1/orchestration/dependencies.py`: `HealthStatus as AgentHealthMonitorStatus`
  toegevoegd als re-export van `agent_health_monitor_agent`. Geregistreerd in `__all__`.
- `src/core/api/v1/orchestration/critic_router.py`: `CriticAgent` nu via dependencies
  (was: directe import uit `src.core.agents.critic_agent`).
- `src/core/api/v1/orchestration/health_router.py`: `AgentHealthMonitorAgent` en
  `AgentHealthMonitorStatus as AgentHealthStatus` nu via dependencies
  (was: directe import uit `src.core.agents.agent_health_monitor_agent`).
- `src/core/api/v1/orchestration/stats_router.py`: 3 directe agent-klasse imports
  vervangen door imports uit dependencies. Cross-router factory imports
  (`get_health_monitor`, `get_agent_router`, `get_master_orchestrator`) blijven
  intact -- ze garanderen dat stats_router dezelfde agent-instanties ziet als
  workflow_router en health_router.
- `src/core/api/v1/orchestration/workflow_router.py`: 3 directe agent-klasse imports
  (`AgentRouterAgent`, `CriticAgent`, `MasterOrchestratorAgent`) samengevoegd met het
  bestaande dependencies-blok.
- `tests/architecture/test_adr033_orchestration_imports.py`: regressietest toegevoegd
  (4 tests, 1 per router bestand) die direct-agent-imports detecteert via AST-analyse.

## Waarom

ADR-033 criterium 2: `lint-imports --config .importlinter` moet "All contracts OK" tonen.
Router bestanden mogen nooit direct importeren uit domeinmodules (`agents`, `database`,
`governance`, `learning`, `workflow`, `llm`). De facade aggregatie-laag (`dependencies.py`)
is het enige sanctioned import-punt per ADR-033 paragraaf 2 en `allow_indirect_imports = true`
in de `.importlinter` configuratie.

## Testbewijs

```
lint-imports --config .importlinter
  Contracts: 4 kept, 0 broken.

pytest tests/architecture/test_adr033_orchestration_imports.py -v
  4 passed

pytest tests/architecture/ tests/unit/api/orchestration/ -q
  80 passed

python -m pyright: 0 errors, 55 warnings
ruff check src/: All checks passed
python -m mypy src/core/api/v1/orchestration/: 0 errors
```

## Bekende follow-up (niet in scope SP-API-009)

De 4 router bestanden bevatten elk een eigen module-level cache en eigen factory functies
naast de gelijke structuren in `dependencies.py`. Dit is pre-existing duplicatie -- de
caches zijn functioneel correct maar `clear_tenant_cache()` in `dependencies.py` raakt
de router-lokale caches niet.

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
