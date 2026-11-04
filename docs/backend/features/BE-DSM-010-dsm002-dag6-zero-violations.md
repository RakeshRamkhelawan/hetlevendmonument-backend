# BE-DSM-010 -- SP-DSM-002 Dag 6: Alle 35 resterende violations opgelost (0 totaal)

**Sprint:** SP-DSM-002 Dag 6
**Datum:** 2026-06-17
**Status:** APPROVED

## Doel

Alle 35 resterende ADR-033 API-layer violations oplossen zodat
`scripts/dsm_api_violation_finder.py` 0 violations rapporteert en
`API_VIOLATION_CEILING` verlaagd wordt naar 0. SP-DSM-002 wordt CLOSED.

## Scope

5 clusters van violations:

| Cluster | Bestanden | Violations |
|---------|-----------|------------|
| A | council_dependencies.py, cva_chat.py, registries/agents.py, registries/copilot.py, registries/realtime.py, setup/middleware_config.py, setup/router_registry.py | 9 |
| B | agentic/dependencies.py + 4 routers, als/dependencies.py + als/shared.py | 12 |
| C | cva/dependencies.py + legacy_router.py + public_router.py + state.py | 6 |
| D | focus_builder/dependencies.py + agents.py + ai_router.py + ws_chat_router.py | 7 |
| E | sync/ws_handler.py | 1 |
| **Totaal** | | **35 -> 0** |

## Aanpak per Cluster

### Cluster A -- dsm:exempt annotaties

Bestanden die legitiem buiten het standard 3-laags patroon vallen (Laag 3 registries,
bootstrap modules, circular-import facade) krijgen een `# dsm:exempt reason: ...` header
op regel 1. De scanner slaat deze bestanden over.

### Cluster B -- agentic + als

`agentic/dependencies.py` uitgebreid met 7 nieuwe re-exports (AgentRegistry,
AgentRegistryRepository, AgentCatalogLoader, AgentConfig, DomainPack,
DomainPackOrchestrator, ROICalculator, FinanceSupervisor, SupervisorID, TaskStatus).
`als/dependencies.py` uitgebreid met ChiefOrchestrator, get_redis_pool, Signal,
SignalBus, SignalTier. Alle 6 router-bestanden omgeleid naar `.dependencies`.

### Cluster C -- cva

`cva/dependencies.py` uitgebreid met AgentRegistry, AgentRegistryRepository,
ConversationMemory, UltimateCVAAgent, create_ultimate_cva_agent, get_redis_client.
3 router-bestanden en state.py omgeleid.

### Cluster D -- focus_builder

`focus_builder/dependencies.py` uitgebreid met FocusBuilderChatAgent,
FocusBuilderToolAgent, _get_internal_agents, require_council_approval,
FocusSuggestionService, SuggestionRequest, SuggestionResponse.
ws_chat_router.py: lazy inline imports vervangen door top-level imports + dead
`except ImportError` block verwijderd.
Test `test_focus_builder_ws_chat.py` patch-locatie bijgewerkt naar router-namespace.

### Cluster E -- sync

`sync/ws_handler.py` omgeleid van `src.core.database.redis` naar
`src.core.api.v1.sync.dependencies` (get_redis_client was al aanwezig).

## Resultaat

- `python scripts/dsm_api_violation_finder.py` -- 0 violations
- `tests/architecture/test_dsm_api_violations.py` -- GROEN (ceiling = 0)
- `tests/architecture/test_dsm002_dag6_zero_violations.py` -- GROEN
- Pyright: 0 errors (55 warnings, gelijk aan baseline)
- Ruff: 0 errors in gewijzigde packages
- 291 passed, 19 xfailed (architecture + api unit suite)

## Gewijzigde bestanden

### Productie (src/)
- `src/core/api/v1/als/council_dependencies.py` (dsm:exempt)
- `src/core/api/cva_chat.py` (dsm:exempt)
- `src/core/api/registries/agents.py` (dsm:exempt)
- `src/core/api/registries/copilot.py` (dsm:exempt)
- `src/core/api/registries/realtime.py` (dsm:exempt)
- `src/core/api/setup/middleware_config.py` (dsm:exempt)
- `src/core/api/setup/router_registry.py` (dsm:exempt)
- `src/core/api/v1/agentic/dependencies.py` (uitgebreid)
- `src/core/api/v1/agentic/agent_discovery.py` (omgeleid)
- `src/core/api/v1/agentic/agentic_domain_router.py` (omgeleid)
- `src/core/api/v1/agentic/agentic_roi_router.py` (omgeleid)
- `src/core/api/v1/agentic/agents.py` (omgeleid)
- `src/core/api/v1/agentic/supervisors.py` (omgeleid)
- `src/core/api/v1/als/dependencies.py` (uitgebreid)
- `src/core/api/v1/als/shared.py` (omgeleid)
- `src/core/api/v1/cva/dependencies.py` (uitgebreid)
- `src/core/api/v1/cva/legacy_router.py` (omgeleid)
- `src/core/api/v1/cva/public_router.py` (omgeleid)
- `src/core/api/v1/cva/state.py` (omgeleid)
- `src/core/api/v1/focus_builder/dependencies.py` (uitgebreid)
- `src/core/api/v1/focus_builder/agents.py` (omgeleid)
- `src/core/api/v1/focus_builder/ai_router.py` (omgeleid)
- `src/core/api/v1/focus_builder/ws_chat_router.py` (lazy -> top-level)
- `src/core/api/v1/sync/ws_handler.py` (omgeleid)

### Tests
- `tests/architecture/test_dsm002_dag6_zero_violations.py` (nieuw -- rood -> groen)
- `tests/architecture/test_dsm_api_violations.py` (ceiling 35 -> 0)
- `tests/unit/api/test_focus_builder_ws_chat.py` (patch-locatie bijgewerkt)

### Docs
- `SPRINT_PLANNING.md` (SP-DSM-002 OPEN -> CLOSED)
- `docs/SPRINT_TRACKER.md` (SP-DSM-002 status bijgewerkt)
- `docs/backend/features/ID-REGISTRY.md` (BE-DSM-010 toegevoegd)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-002 Dag 6: Cluster A-E -- 35->0 violations. dsm:exempt + agentic/als/cva/focus_builder/sync facades. SP-DSM-002 CLOSED. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-002 Dag 6: Cluster A-E -- 35->0 violations. dsm:exempt + agentic/als/cva/focus_builder/sync facades. SP-DSM-002 CLOSED..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
