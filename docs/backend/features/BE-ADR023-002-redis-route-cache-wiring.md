# Backend Feature Specification

## Metadata

- Feature ID: BE-ADR023-002
- Feature naam: Redis-cache cross-worker wiring op AgentRouterAgent/MasterOrchestratorAgent
- Status: APPROVED
- Auteur: Claude (Sonnet 5)
- Reviewer: code-reviewer subagent (APPROVED WITH MINOR NOTES) + quality-reviewer subagent (CHANGES_REQUESTED -> opgelost)
- Datum: 2026-07-06
- Gerelateerde user story / ticket: SP-ADR023-002 Dag 2
- Gerelateerde router / module: `src/core/api/v1/orchestration/`, `src/core/agents/agent_router_agent.py`, `src/core/agents/master_orchestrator_agent.py`, `src/core/app_lifespan.py`, `src/core/api/main.py`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

ADR-023 sectie 4 claimt een cross-worker routing-cache via Redis. In productie was dit nooit actief: de singleton-factory `agent_router_agent.get_agent_router(tenant_id, redis_client=None, ...)` accepteerde `redis_client` al, maar geen enkele caller gaf hem daadwerkelijk door.

### Kritieke bevinding die de scope bepaalde (afwijking van de oorspronkelijke sprint-dag-brief)

De singleton heeft **eerste-aanmaak-wint-semantiek** (`agent_router_agent.py:719-729`): `redis_client` wordt alleen toegepast bij de allereerste aanmaak van een tenant-instance in `_instances`. `app_lifespan.py`'s warmup-loop (`_init_agent_health_write_bridge`) itereert bij elke opstart over ALLE bestaande tenants en wint daardoor vrijwel altijd die race. Als vandaag alleen `orchestration/dependencies.py` gewired zou worden (de oorspronkelijke, smallere scope), zou in de praktijk **geen enkele bestaande tenant** ooit een Redis-cache-tier krijgen -- exact het patroon dat Dag 1 drie reviewrondes kostte. Daarom is vandaag in één keer gewired op alle 4 bekende live call-sites, in plaats van de ontbrekende call-sites aan een volgende reviewronde over te laten.

### In scope

**4 call-sites gewired, allemaal met `redis_client` naast de bestaande `async_session_factory`-wiring uit Dag 1:**

| Call-site | Bestand:regel | Reden |
| --- | --- | --- |
| `dependencies.get_agent_router()` | `orchestration/dependencies.py` | Bedient de echte `/orchestration/*` HTTP-requests |
| `_init_agent_health_write_bridge` | `app_lifespan.py` | Kritiek: wint de eerste-aanmaak-race voor ALLE bestaande tenants bij opstart |
| `MasterOrchestratorAgent._get_router()` | `master_orchestrator_agent.py` | Workflow-sub-task-delegatie (dezelfde route als de FA-NEW-001-fix van gisteren) |
| agent_runtime-facade-bootstrap | `api/main.py` | Systeem-tenant (1) registratie bij opstarten |

**Bewust NIET gewijzigd**: `src/core/workflow/worker.py:293` (`get_agent_router(tenant_id=_SYSTEM_TENANT_ID)`) -- apart Dramatiq-OS-proces, systeemtenant, zelfde reeds gedocumenteerde uitzondering als bij `async_session_factory` gisteren. Ook test-only aanroepen in `tests/integration/test_workflow_real_routing.py` en `tests/unit/workflow/test_workflow_real_routing.py` zijn bewust ongewijzigd (geen productiepad).

**Naamsbotsing (zelfde als gisteren, herbevestigd)**: `src/core/agents/agent_router.py:657` definieert een ANDERE, gelijknamige `async def get_agent_router() -> AgentRouter` -- ander type (`AgentRouter`, niet `AgentRouterAgent`), ander bestand, geen call-site-overlap.

**Fail-graceful Redis-onbeschikbaarheid (code-reviewer-aanbeveling, overgenomen)**: `orchestration/dependencies.py` wrapt `await get_redis_client()` in een try/except (`_get_redis_client_fail_graceful()`), naar het precedent in `src/core/api/v1/agentic/dependencies.py::get_adaptation_service()`. Zonder deze wrapper zou een tijdelijke Redis-outage alle `/orchestration/*`-requests met een 500 laten falen voor wat een puur optionele cache-optimalisatie is. `app_lifespan.py` en `api/main.py` hebben al een brede `try/except Exception` rond de volledige init-stap en hoeven geen aparte wrapper.

**Dependency-injectie op `MasterOrchestratorAgent`**: nieuwe `redis_client: Any | None = None`-parameter op `__init__` (naast de bestaande `async_session_factory` van Dag 1), opgeslagen als `self._redis_client`, doorgegeven door `_get_router()`. Consistent met ADR-034: `agents/` importeert nog steeds geen `src.core.database`/`src.core.database.redis` direct.

### FA-001 (gevonden door de verplichte onafhankelijke review): `route()` gebruikte de Redis-tier nooit

De initiele implementatie van vandaag wirede `redis_client` correct van de applicatielaag naar `AgentRouterAgent._redis_cache_tier` op alle 4 call-sites, maar `AgentRouterAgent.route()` -- de enige methode die daadwerkelijk routeringsbeslissingen neemt -- raadpleegde `_redis_cache_tier` nergens. De tier werd geconstrueerd en correct tegen Redis getest in isolatie (`RedisRouteCacheTier.get()`/`set()` rechtstreeks aangeroepen in de integratietest), maar dat bewees niet dat `route()` hem gebruikt. Gevolg: twee Gunicorn-workers deelden in de praktijk nog steeds GEEN routeringsbeslissingen -- exact het probleem dat ADR-023 sectie 4 claimt op te lossen.

**Fix**: `route()` raadpleegt nu een nieuwe tier 1.5 tussen de in-memory cache-check (tier 1) en DB-discovery (tier 2): bij een in-memory-miss wordt `_redis_cache_tier.get()` geraadpleegd; bij een hit wordt de in-memory cache ook gevuld (zodat dezelfde worker geen tweede Redis-round-trip nodig heeft) en de agent_id geretourneerd. Een nieuwe `_remember_route()`-helper schrijft elke succesvolle routeringsbeslissing (discovery/capability/LLM) naar zowel de in-memory cache als (indien geconfigureerd) de Redis-tier, met dezelfde SHA-256-cache-key als de in-memory `RouteCache` (`self._cache._key(...)`) zodat beide tiers consistent keyen.

De integratietest is herschreven zodat hij door `router.route()` zelf gaat (niet meer rechtstreeks `_redis_cache_tier.get()`/`set()`): "worker 2" heeft bewust GEEN geregistreerd manifest, GEEN discovery-service en GEEN LLM-client, zodat de enige manier waarop `route()` het juiste antwoord kan geven de gedeelde Redis-tier is.

### Out of scope (volgende dagen van dezelfde sprint)

- Prometheus/OTel-metrics op de routing-laag -- dag 3.
- `clear_tenant_cache()`-atomiciteit (bestaand, gedocumenteerd, niet vandaag herontworpen).
- Consolidatie van `MasterOrchestratorAgent`'s eigen dubbele-cache-architectuur is al gebeurd (Dag 1) -- niet opnieuw geraakt vandaag.

---

## Build summary

- Gewijzigd: `src/core/agents/master_orchestrator_agent.py` (`redis_client`-DI-parameter + `_get_router()` + module-level `get_master_orchestrator()`-singleton)
- Gewijzigd: `src/core/api/v1/orchestration/dependencies.py` (`get_agent_router()` + `get_master_orchestrator()` nu `async def`, nieuwe `_get_redis_client_fail_graceful()`-helper)
- Gewijzigd: `src/core/app_lifespan.py` (`_init_agent_health_write_bridge` wiret `redis_client`)
- Gewijzigd: `src/core/api/main.py` (agent_runtime-facade-bootstrap wiret `redis_client`)
- Nieuw: `tests/unit/api/orchestration/test_dependencies_redis_cache_wiring.py` (3 tests)
- Uitgebreid: `tests/unit/agents/test_agent_router_discovery_wiring.py` (+4 tests: `MasterOrchestratorAgent`-redis-wiring, `app_lifespan`-warmup-assertie uitgebreid, `get_master_orchestrator`-aanroep nu async)
- Herschreven (cascading van `async def`-conversie): `tests/unit/api/orchestration/test_dependencies_router_consolidation.py`, `tests/unit/api/orchestration/test_orchestration_dependencies.py`, `tests/architecture/test_master_orchestrator_instantiation_consolidation.py` -- alle synchrone directe aanroepen van `get_agent_router()`/`get_master_orchestrator()` zijn nu `async`/`await` + mocken `get_redis_client`.
- Nieuw: `tests/integration/test_agent_router_redis_cross_worker_cache.py` (2 tests, echte Redis op poort 6380, geen mock -- herschreven na FA-001 om door `route()` te gaan i.p.v. de tier direct aan te spreken)
- Gewijzigd (FA-001-fix): `src/core/agents/agent_router_agent.py` (`route()` tier 1.5 Redis-lookup + nieuwe `_remember_route()`-helper die naar in-memory EN Redis schrijft)
- Uitgebreid (FA-001-fix): `tests/unit/test_agent_router_agent.py` (+4 tests: Redis-tier-hit vóór discovery, in-memory-populatie na Redis-hit, Redis-write na discovery-hit, fail-graceful zonder tier) + `router`-fixture kreeg `_redis_cache_tier = None`

---

## Backend inventory

| Element | Locatie | Beschrijving |
| --- | --- | --- |
| `_get_redis_client_fail_graceful()` | `src/core/api/v1/orchestration/dependencies.py` | Haalt Redis-client op, degradeert naar `None` bij een fout (geen 500 op cache-falen) |
| `MasterOrchestratorAgent.__init__(redis_client=...)` | `src/core/agents/master_orchestrator_agent.py` | DI-parameter, doorgegeven aan `_get_router()` |
| `get_master_orchestrator(tenant_id, async_session_factory=None, redis_client=None)` | `src/core/agents/master_orchestrator_agent.py` | Derde parameter toegevoegd |

---

## Testdekking

- Happy path: `dependencies.get_agent_router()`/`get_master_orchestrator()` geven een niet-`None` `_redis_cache_tier`/`_redis_client` terug wiens onderliggende client de (gemockte) `get_redis_client()`-return-value is.
- Regressie: `async_session_factory`-wiring uit Dag 1 blijft intact op beide functies na de Redis-wiring.
- Happy path: `MasterOrchestratorAgent(redis_client=X)._get_router()` geeft de router een `_redis_cache_tier` wiens `_redis` `X` is.
- Regressie: zonder geinjecteerde `redis_client` blijft `_redis_client`/`_redis_cache_tier` `None` (fail-graceful, geen regressie voor call-sites die dit bewust weglaten -- bv. `workflow/worker.py`).
- **Integratie, echte Redis (poort 6380, geen mock)**: cross-worker cache-hit via `route()` zelf -- "worker 2" (geen manifest, geen discovery, geen LLM) kan de taak ALLEEN oplossen via de Redis-tier die "worker 1" vulde. Plus een tenant-isolatietest tegen dezelfde cache-key voor 2 tenants.
- **FA-001-fix, unit-niveau**: `route()` raadpleegt de Redis-tier bij een in-memory-miss (tier 1.5) vóór DB-discovery; een Redis-hit vult ook de in-memory cache; elke succesvolle discovery/capability/LLM-beslissing wordt naar de Redis-tier geschreven; zonder tier blijft het gedrag exact zoals vóór deze feature (fail-graceful).
- 3 bestaande testbestanden zijn mee-geconverteerd naar async om de `async def`-conversie van `dependencies.get_agent_router()`/`get_master_orchestrator()` niet te laten regresseren (gevonden door zowel de quality- als code-reviewer, vóór implementatie).

Volledige gerichte regressie (`tests/unit/agents/`, `tests/unit/api/orchestration/`, `tests/architecture/`, `tests/unit/test_agent_router_agent.py`): zie final-approver brief voor het exacte, met FA-001-fix geverifieerde aantal. Enige verwachte failure: pre-existing `test_dsm006_ar_governance_fan_out.py`, al geescaleerd naar Rakesh, ongewijzigd t.o.v. het nulpunt.

---

## Bekende beperkingen (bewust, volgende dagen)

- Prometheus/OTel-metrics volgen op dag 3 van SP-ADR023-002.
- Eerste-aanmaak-wint-semantiek geldt nu ook voor `redis_client`, net als voor `async_session_factory` sinds Dag 1: als een aanroep zonder `redis_client` als eerste voor een tenant binnenkomt, blijft die tenant zonder cache-tier totdat `clear_tenant_cache()` wordt aangeroepen. Vandaag juist proactief op alle 4 bekende call-sites gewired om dit scenario te minimaliseren.
