# Backend Feature Specification

## Metadata

- Feature ID: BE-ADR023-001
- Feature naam: AgentRouterAgent-instantiatie consolideren + agent-discovery wiring
- Status: APPROVED
- Auteur: Claude (Sonnet 5)
- Reviewer: code-reviewer subagent (APPROVED WITH MINOR NOTES) + quality-reviewer subagent (APPROVED)
- Datum: 2026-07-05
- Gerelateerde user story / ticket: SP-ADR023-002 Dag 1
- Gerelateerde router / module: `src/core/api/v1/orchestration/`, `src/core/agents/agent_router_agent.py`, `src/core/app_lifespan.py`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

ADR-023 claimt intelligente routing naar echte, geregistreerde agents. In productie klopte dit niet: agent-discovery degradeerde stil naar lege resultaten omdat `async_session_factory` de router die klantverzoeken bedient nooit bereikte (letterlijke `TODO(Rakesh)` in `agent_router_agent.py`).

Bij het verifieren tegen code bleek het probleem dieper te zitten dan een ontbrekende parameter: er bestonden TWEE volledig gescheiden instantiatiepaden voor `AgentRouterAgent` --
1. de singleton-factory `agent_router_agent.get_agent_router()` (module-level `_instances`-dict), gebruikt door `app_lifespan.py`'s health-monitor warmup en `MasterOrchestratorAgent`;
2. een aparte `get_agent_router()`-functie in `orchestration/dependencies.py` die zelf een kale `AgentRouterAgent` construeerde in een eigen `_router_cache`-dict -- dit is de functie die de echte HTTP-endpoints (`/orchestration/route`, `/orchestration/stats`) via FastAPI `Depends()` gebruiken.

Deze feature consolideert beide paden tot 1 canoniek pad en wiret `async_session_factory` erin, zodat agent-discovery in productie echt werkt.

**Naamsbotsing (geen functionele overlap, expliciet uitgesloten van scope)**: `src/core/als/router.py:854` bevat een TWEEDE, functioneel volledig ongerelateerde klasse die ook `AgentRouterAgent` heet -- een dunne `BaseAgent`-wrapper rond `RouterService` (ADR-017 Gatekeeper-integratie, ALS-domein). Deze feature raakt uitsluitend `src.core.agents.agent_router_agent.AgentRouterAgent` (het intent-based routing-systeem met de 5-tier fallback-chain). De twee klassen delen geen code, geen cache en geen call-sites. Toekomstige lezers: verifieer bij elke wijziging aan "AgentRouterAgent" altijd het volledige importpad, niet alleen de klassenaam.

### In scope

- `agent_router_agent.py`: nieuwe `clear_router_instance(tenant_id)`-helper (thread-safe eviction via de bestaande `_instances_lock`); TODO(Rakesh) verwijderd uit de docstring.
- `orchestration/dependencies.py`: `get_agent_router()` delegeert naar de singleton-factory i.p.v. een eigen cache te onderhouden; `clear_tenant_cache()` evict nu via `clear_router_instance()`.
- `app_lifespan.py`: health-monitor warmup geeft `async_session_factory` door.
- Beide call-sites gebruiken `src.core.database.session.get_db_session` (niet `db_manager.async_session_maker` direct) -- ADR-034 verbiedt een directe `src.core.database.database`-import in `orchestration/` (afgedwongen door `tests/architecture/test_adr034_orchestration_boundary.py::test_orchestration_routers_do_not_import_database`, die deze wijziging in eerste opzet ook daadwerkelijk ROOD liet zien voor de `get_db_session`-correctie werd toegepast).

**FA-NEW-001 (gevonden door de verplichte onafhankelijke review, ronde 1)**: `MasterOrchestratorAgent._get_router()` (`master_orchestrator_agent.py:520`) was een DERDE, niet-gewirede call-site van de geconsolideerde `AgentRouterAgent`-singleton -- gemist bij de initiele consolidatie omdat geen enkele individuele test hem dekte. Opgelost door `async_session_factory` als DI-parameter aan `MasterOrchestratorAgent.__init__` toe te voegen (ADR-034-conform: agents/ importeert nog steeds geen `src.core.database` zelf), en die parameter te wiren op de twee bekende live constructiepunten van `MasterOrchestratorAgent`:
- `orchestration/dependencies.py::get_master_orchestrator()` (bedient de echte `/orchestration/*`-endpoints).
- `src/core/api/main.py`'s `agent_runtime`-facade-bootstrap (tenant_id=1, systeem-registratie bij opstarten).

**Nieuw ontdekt tijdens het oplossen van FA-NEW-001 (ronde-3-BLOCKER)**: `MasterOrchestratorAgent` zelf had dezelfde architecturale dubbele-instantiatie-bug die `AgentRouterAgent` had vóór deze feature (twee gescheiden caches: `master_orchestrator_agent._instances` vs `orchestration/dependencies._orchestrator_cache`). Een eerste versie van deze fix legde dit vast als een opzettelijk rode architectuurtest en stelde consolidatie uit naar een volgende sprint-dag -- de derde onafhankelijke reviewronde wees dit af onder de aangescherpte Laag-6-regel van `final-approver.md` (2026-07-03: een rode architectuurtest alléén is niet langer voldoende, het issue moet daadwerkelijk opgelost zijn tenzij expliciet naar Rakesh geescaleerd). Daarom alsnog vandaag geconsolideerd: `orchestration/dependencies.get_master_orchestrator()` delegeert nu naar de singleton in `master_orchestrator_agent.py` (nieuwe `clear_orchestrator_instance()`-helper, exact analoog aan `clear_router_instance()`). De architectuurtest is nu een permanente GROENE regressiebewaker, hernoemd naar `tests/architecture/test_master_orchestrator_instantiation_consolidation.py`.

### Out of scope (volgende dagen van dezelfde sprint, SP-ADR023-002)

- Redis-cachelaag wiring (`redis_client`) op het live pad -- dag 2.
- Prometheus/OTel-metrics op de routing-laag -- dag 3.
- `clear_tenant_cache()`-atomiciteit (bestaand, gedocumenteerd, niet vandaag herontworpen).
- `workflow/worker.py`'s eigen aanroep van de singleton-factory (systeemtenant, ongewijzigd, geen `async_session_factory`-behoefte in worker-context).

---

## Build summary

- Nieuw: `tests/unit/agents/test_agent_router_discovery_wiring.py` (6 tests)
- Nieuw: `tests/unit/api/orchestration/test_dependencies_router_consolidation.py` (3 tests)
- Nieuw: `tests/architecture/test_master_orchestrator_instantiation_consolidation.py` (1 test, GROEN -- permanente regressiebewaker; was kortstondig `test_master_orchestrator_dual_cache_gap.py`, opzettelijk ROOD, hernoemd na de daadwerkelijke consolidatie)
- Herschreven: `tests/unit/api/orchestration/test_orchestration_dependencies.py::test_get_agent_router_different_tenants_return_different_instances` EN `test_get_master_orchestrator_different_tenants_return_different_instances` (patchen nu `__init__` op de klasse i.p.v. de verwijderde `dependencies._router_cache`/`_orchestrator_cache`)
- Gewijzigd: `src/core/agents/agent_router_agent.py` (`clear_router_instance()` toegevoegd, TODO verwijderd)
- Gewijzigd: `src/core/agents/master_orchestrator_agent.py` (`async_session_factory` DI-parameter + `_get_router()` + `clear_orchestrator_instance()` toegevoegd)
- Gewijzigd: `src/core/api/v1/orchestration/dependencies.py` (BEIDE `get_agent_router()` en `get_master_orchestrator()` delegeren nu naar hun respectievelijke singleton in `agents/`, geen lokale caches meer; `get_db_session` i.p.v. directe `db_manager`-import)
- Gewijzigd: `src/core/app_lifespan.py` (`get_db_session` doorgegeven aan `get_agent_router()`)
- Gewijzigd: `src/core/api/main.py` (agent_runtime-facade-bootstrap wired met `get_db_session`)

---

## Backend inventory

| Element | Locatie | Beschrijving |
| --- | --- | --- |
| `clear_router_instance(tenant_id)` | `src/core/agents/agent_router_agent.py` | Thread-safe eviction van de singleton-cache-entry voor 1 tenant |
| `clear_orchestrator_instance(tenant_id)` | `src/core/agents/master_orchestrator_agent.py` | Thread-safe eviction, analoog aan `clear_router_instance` |
| `get_agent_router(tenant_id)` | `src/core/api/v1/orchestration/dependencies.py` | Delegeert naar de `agent_router_agent`-singleton, wired met `get_db_session` |
| `get_master_orchestrator(tenant_id)` | `src/core/api/v1/orchestration/dependencies.py` | Delegeert naar de `master_orchestrator_agent`-singleton, wired met `get_db_session` |
| `_init_agent_health_write_bridge` | `src/core/app_lifespan.py` | Warmup-loop geeft nu `async_session_factory=get_db_session` door |
| `MasterOrchestratorAgent.__init__(async_session_factory=...)` | `src/core/agents/master_orchestrator_agent.py` | DI-parameter, doorgegeven aan `_get_router()` |

---

## Testdekking

- Happy path: `dependencies.get_agent_router()` retourneert hetzelfde object als de singleton-factory voor dezelfde tenant (regressietest tegen de architecturale inconsistentie).
- Happy path: de geretourneerde router heeft `_async_session_factory is get_db_session` (niet `None`).
- Happy path: `AgentRouterAgent.initialize()` geeft de constructor-factory door aan `AgentDiscoveryService` (bewijst dat de wiring de daadwerkelijke discovery-laag bereikt).
- Regressie: discovery zonder factory blijft fail-graceful (bestaand gedrag, niet gebroken).
- Regressie: `clear_tenant_cache()` evict de geconsolideerde singleton-instance nog steeds correct.
- Architectuur: `test_adr034_orchestration_boundary.py::test_orchestration_routers_do_not_import_database` blijft GROEN (was tijdens implementatie kortstondig ROOD door een eerste opzet met directe `db_manager`-import -- gecorrigeerd naar `get_db_session`).
- Happy path (FA-NEW-001): `MasterOrchestratorAgent._get_router()` geeft `self._async_session_factory` door aan de `AgentRouterAgent`-singleton.
- Regressie (FA-NEW-001): zonder geinjecteerde factory blijft `MasterOrchestratorAgent._async_session_factory` `None` (fail-graceful, geen regressie voor bestaande call-sites).
- `orchestration/dependencies.get_master_orchestrator()` wiret `get_db_session` in de `MasterOrchestratorAgent` die het construeert.
- Architectuur (regressiebewaker): `tests/architecture/test_sp_agt_004_dsm_final.py::test_dsm_db_agents_no_regression` bleef GROEN nadat de eerste FA-NEW-001-implementatiepoging (lokale `get_db_session`-import IN `master_orchestrator_agent.py` zelf) hem tijdelijk ROOD had gemaakt -- opgelost door DI (constructor-parameter) i.p.v. een lokale import, zodat `src/core/agents/` nul nieuwe database-imports krijgt.

Alle nieuwe/herschreven tests waren ROOD tegen de pre-fix code, GROEN na de fix. Volledige gerichte regressie (`tests/unit/agents/`, `tests/unit/api/orchestration/`, `tests/architecture/`): 848 passed, 1 failed:
1. Pre-existing `test_dsm006_ar_governance_fan_out.py` (ongewijzigd t.o.v. nulpunt, al geescaleerd naar Rakesh in een eerdere sprint).

De MasterOrchestratorAgent-consolidatie voegde 1 test toe (`test_master_orchestrator_instantiation_paths_are_consolidated`) en verwijderde de eerder opzettelijk rode variant -- netto GEEN extra failure meer in de eindregressie.

---

## Bekende beperkingen (bewust, volgende dagen)

- Redis-cache en Prometheus-metrics volgen op dag 2/3 van SP-ADR023-002.
- Eerste-aanmaak-wint-semantiek van de singleton-dict is een bestaand kenmerk, niet gewijzigd: als een aanroep zonder factory als eerste voor een tenant binnenkomt, "vergrendelt" die tenant zonder discovery totdat `clear_tenant_cache()` wordt aangeroepen. Dit was al zo vóór deze fix, en geldt nu identiek voor beide singletons (`AgentRouterAgent` en `MasterOrchestratorAgent`).

---

## Trainingssamenvatting

Deze feature introduceert geen nieuw endpoint of gebruikersgerichte actie -- het is een interne wiring-fix in de agent-orchestratielaag. De trainingssamenvatting hieronder beschrijft daarom het systeeminterne gedrag (de "actor" is de applicatie zelf, niet een eindgebruiker).

- **Actor:** de FastAPI-applicatie tijdens opstarten (lifespan-warmup) en elke request-handler die via `Depends(get_agent_router)` een `AgentRouterAgent` nodig heeft (bijv. `/api/v1/orchestration/route`, `/api/v1/orchestration/stats`).
- **Voorwaarde:** de applicatie is gestart en `initialize_database()` is voltooid (routers worden synchroon geregistreerd in `create_app()`, maar `get_db_session()` faalt pas hard op het moment dat hij daadwerkelijk wordt aangeroepen zonder geinitialiseerde database -- dat gebeurt in de praktijk niet, omdat requests pas na lifespan-startup binnenkomen).
- **Actie (request):** een tenant-scoped request bereikt een orchestration-endpoint, of de lifespan-warmup itereert over alle tenants bij opstarten.
- **Systeemverwerking:** `get_agent_router(tenant_id)` (in `orchestration/dependencies.py` of via de directe singleton-aanroep in `app_lifespan.py`) roept nu altijd `agent_router_agent.get_agent_router(tenant_id, async_session_factory=get_db_session)` aan. Bij de eerste aanroep per tenant wordt een `AgentRouterAgent` aangemaakt met een echte, werkende sessie-factory; latere aanroepen voor dezelfde tenant hergebruiken die singleton-instance (`_instances`-dict, thread-safe via `_instances_lock`). Bij een route-beslissing kan de router nu daadwerkelijk `AgentDiscoveryService` gebruiken om geregistreerde agents in de database op te zoeken (tier 2 van de 5-tier fallback-chain), in plaats van altijd terug te vallen op capability-match/LLM/fallback omdat discovery leeg bleef.
- **Succesrespons:** de router retourneert een routebeslissing die (waar van toepassing) gebaseerd is op echte, in de database geregistreerde agents, niet uitsluitend op in-memory capability-matching of een LLM-gok.
- **Foutrespons:** als de database niet bereikbaar is op het moment van een discovery-query, valt `AgentDiscoveryService` fail-graceful terug op een leeg resultaat (bestaand gedrag, niet gewijzigd) -- de request faalt niet hierdoor, de routing valt door naar de volgende tier in de fallback-chain.
- **Uitzonderingen:** `workflow/worker.py` roept de singleton-factory aan met de systeemtenant en zonder `async_session_factory` -- dit is een apart OS-proces (Dramatiq-worker) waarvoor DB-backed discovery vandaag bewust buiten scope is gelaten (geen regressie, bestaand gedrag).
