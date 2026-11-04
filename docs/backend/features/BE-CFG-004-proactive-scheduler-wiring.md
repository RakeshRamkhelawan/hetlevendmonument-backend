# Backend Feature Specification

## Metadata

- Feature ID: BE-CFG-004
- Feature naam: ProactiveScheduler wiring in app_lifespan
- Status: APPROVED
- Auteur: Sprint Executor
- Reviewer: code-reviewer + quality-reviewer
- Datum: 2026-05-30
- Gerelateerde user story / ticket: B-026 (MASTER-AUDIT-COMPLEET.md)
- Gerelateerde router / module: src/core/app_lifespan.py
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

Bug B-026: `ProactiveScheduler` werd nooit geinstantieerd of gestart in `app_lifespan.py`. Gevolg: alle 10 proactive monitors (AgentHealth, WorkflowLatency, QueueDepth, TokenSpike, CircuitBreaker, ConsentExpiry, AuditAnomaly, DSARExport, PolicyChange, SensitiveWorkflow) draaiden niet. Deze feature fixt de wiring.

### In scope

- `_init_proactive_scheduler(app)` toevoegen aan startup sequence
- `_cleanup_proactive_scheduler(app)` toevoegen aan shutdown sequence
- Lazy imports, non-fatal fallback, per-monitor try/except
- Alleen interval-based monitors (interval_seconds > 0) in scheduler

### Out of scope

- Concrete protocol-implementaties voor monitor dependencies (PrometheusClient, ConsentRepo, etc.)
- `TenantRepo.list_active_ids()` concrete implementatie
- `CopilotService` en `NotificationDispatcher` op `app.state` zetten (wordt elders opgelost)

---

## Build summary

- Nieuw gebouwd:
  - `async def _init_proactive_scheduler(app: FastAPI)` in `src/core/app_lifespan.py`
  - `async def _cleanup_proactive_scheduler(app: FastAPI)` in `src/core/app_lifespan.py`
  - `tests/unit/test_sp_h07_proactive_scheduler.py`
- Gewijzigd:
  - `src/core/app_lifespan.py` — startup/shutdown sequences, `typing.Any` import
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: application lifespan startup/shutdown

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-CFG-004 | ProactiveScheduler wiring | Config / Wiring | `src/core/app_lifespan.py` | Wijziging | App lifespan startup/shutdown |

---

## API-flows

### Flow ID: BE-FLW-003

- Naam: ProactiveScheduler startup
- Trigger: FastAPI lifespan context manager startup phase
- Voorwaarden: App start op; `copilot_service`, `notification_dispatcher`, `tenant_repo`, `redis_client` beschikbaar op `app.state`
- Request-pad: n.v.t. (interne lifecycle)
- Service-stappen:
  1. `_init_proactive_scheduler(app)` wordt aangeroepen
  2. Core dependencies worden opgehaald via `getattr(app.state, ..., None)`
  3. Als core deps ontbreken: log warning, return (non-fatal)
  4. Per interval-based monitor: lazy import + instantiatie met try/except
  5. `AsyncIOScheduler()` + `ProactiveScheduler(...)` aangemaakt
  6. `scheduler.start()` aangeroepen
  7. Scheduler opgeslagen in `app.state.proactive_scheduler`
- DB-operaties: n.v.t.
- Successtatus + response: `[OK] ProactiveScheduler started with N monitors`
- Foutpaden: Ontbrekende dep -> warning + skip; Monitor crash -> warning + andere monitors gaan door
- Eindtoestand: APScheduler draait met N jobs, 1 per monitor per interval

### Flow ID: BE-FLW-004

- Naam: ProactiveScheduler shutdown
- Trigger: FastAPI lifespan context manager shutdown phase
- Voorwaarden: `app.state.proactive_scheduler` is gezet
- Request-pad: n.v.t.
- Service-stappen:
  1. `_cleanup_proactive_scheduler(app)` wordt aangeroepen
  2. Scheduler opgehaald uit `app.state`
  3. `scheduler.shutdown(wait=True)` aangeroepen
- Successtatus + response: `[OK] ProactiveScheduler shut down`
- Foutpaden: Scheduler niet gezet -> skip; Shutdown exception -> warning

---

## Detaildocumentatie per artefact

---

## [BE-CFG-004] ProactiveScheduler wiring

### 1. Type

Configuratie / Application lifecycle wiring

### 2. Locatie

- Bestandspad: `src/core/app_lifespan.py`
- Klasse / functie: `_init_proactive_scheduler(app: FastAPI)`, `_cleanup_proactive_scheduler(app: FastAPI)`

### 3. Gerelateerde flow

- BE-FLW-003 (ProactiveScheduler startup)
- BE-FLW-004 (ProactiveScheduler shutdown)

### 4. Doel

Zorgen dat `ProactiveScheduler` daadwerkelijk start bij app startup en graceful shutdown uitvoert bij app shutdown, zodat alle interval-based proactive monitors hun detectieloopjes draaien.

### 5. Functionele beschrijving

Bij startup van de FastAPI applicatie wordt de `ProactiveScheduler` geinstantieerd met alle beschikbare interval-based monitors. De scheduler gebruikt APScheduler om per monitor een recurring job te registreren die per tenant de `detect()` methode aanroept. Bij shutdown wordt de scheduler graceful gestopt zodat lopende detecties afmaken.

### 6. Technische beschrijving

- `_init_proactive_scheduler` doet lazy imports binnen de functie (consistent met rest van `app_lifespan.py`)
- Core deps (`copilot_service`, `dispatcher`, `tenant_repo`, `redis_client`) worden opgehaald met `getattr(app.state, ..., None)`
- 8 interval-based monitors worden één voor één geprobeerd; elke monitor heeft eigen `try/except`
- `AsyncIOScheduler()` wordt zonder `event_loop=` argument geinstantieerd (gebruikt huidige loop)
- `ProactiveScheduler.start()` roept `scheduler.start()` aan en registreert jobs
- `app.state.proactive_scheduler` slaat de scheduler op zodat cleanup hem kan vinden
- `_cleanup_proactive_scheduler` roept `scheduler.shutdown(wait=True)` aan

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. (interne lifecycle)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: Monitors krijgen `tenant_id` van `tenant_repo.list_active_ids()`, nooit uit request body
- Feature flag: n.v.t.

### 8. Request-specificatie

n.v.t. — interne lifecycle, geen HTTP endpoint

### 9. Response-specificatie

n.v.t. — interne lifecycle, geen HTTP endpoint

### 10. Validaties en constraints

- `interval_seconds > 0` vereist voor scheduler-registratie (event-driven monitors worden overgeslagen)
- `max_instances=1` en `coalesce=True` per APScheduler job

### 11. Business rules

- Non-fatal: ontbrekende dependencies blokkeren startup NIET
- Per-monitor isolatie: één crashende monitor killt de scheduler niet
- Event-driven monitors (`DSARExportMonitor`, `PolicyChangeMonitor`) blijven in `_init_compliance_monitors`

### 12. Afhankelijkheden

- `apscheduler` package (`AsyncIOScheduler`, `IntervalTrigger`)
- `src.core.copilot.proactive.scheduler.ProactiveScheduler`
- `src.core.copilot.proactive.monitors.*` (per monitor lazy import)
- `app.state.copilot_service` (indien beschikbaar)
- `app.state.notification_dispatcher` (indien beschikbaar)
- `app.state.tenant_repo` (indien beschikbaar)
- `app.state.redis_client` (indien beschikbaar)

### 13. Foutafhandeling

- Core deps ontbreken: `logger.info(...)` + return (non-fatal)
- Monitor instantiatie faalt: `logger.warning(...)` + andere monitors gaan door
- Scheduler start faalt: `logger.warning(...)` + return (non-fatal)
- Shutdown faalt: `logger.warning(...)` + verder met cleanup

### 14. Transacties en data-integriteit

n.v.t. — geen DB transacties in lifespan wiring

### 15. Telemetry / logging / tracing

- Startup: `[OK] ProactiveScheduler started with %d monitors`
- Shutdown: `[OK] ProactiveScheduler shut down`
- Missing deps: `ProactiveScheduler: X not available, skipping Y`
- Monitor skip: `ProactiveScheduler: Z skipped: <exception>`
- Alle logs via `loguru.logger` met `%s`-style formatting

### 16. Caching

n.v.t.

### 17. Acceptatiecriteria

- [ ] `_init_proactive_scheduler(app)` bestaat in `src/core/app_lifespan.py`
- [ ] `_cleanup_proactive_scheduler(app)` bestaat in `src/core/app_lifespan.py`
- [ ] Startup sequence roept `_init_proactive_scheduler(app)` aan
- [ ] Shutdown sequence roept `_cleanup_proactive_scheduler(app)` aan
- [ ] `ProactiveScheduler` wordt gestart met interval-based monitors
- [ ] Event-driven monitors worden niet dubbel geinstantieerd
- [ ] Ontbrekende dependencies resulteren in warning (non-fatal)
- [ ] Een gecrashte monitor instantiatie killt de scheduler niet
- [ ] `tests/unit/test_sp_h07_proactive_scheduler.py` slaagt (5/5)
- [ ] `tests/unit/copilot/proactive/` regressies slagen (144/144)

### 18. Integratoruitleg

- De ProactiveScheduler wordt automatisch gestart bij app startup.
- Interval-based monitors draaien op vaste tijden (bijv. elke 5 minuten).
- Event-driven monitors blijven via het event-systeem werken.
- Als een monitor-dependency ontbreekt, wordt die monitor overgeslagen; de rest draait.

### 19. Trainingssamenvatting

- Actor: FastAPI lifespan manager
- Voorwaarde: App start op, core dependencies mogelijk beschikbaar
- Actie (request): Roept `_init_proactive_scheduler(app)` aan
- Systeemverwerking: Instantieert interval-based monitors, maakt scheduler aan, start APScheduler
- Succesrespons: `[OK] ProactiveScheduler started with N monitors`
- Foutrespons: Warning + skip (non-fatal)
- Uitzonderingen: Ontbrekende dependency -> skip; Monitor crash -> skip alleen die monitor

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

n.v.t. — interne lifecycle wiring, geen externe API impact.

---

## Open aannames

- `CopilotService` en `NotificationDispatcher` worden op `app.state` gezet door een andere init-functie (buiten scope van SP-H07).
- Concrete `TenantRepo` met `list_active_ids()` wordt later geimplementeerd.
- Protocol-implementaties voor monitor dependencies (PrometheusClient, ConsentRepo, etc.) worden later gebouwd.

## Open vragen

- Wanneer wordt `CopilotService` op `app.state` gezet zodat de scheduler daadwerkelijk start?

## Risico's

| Risico | Impact | Mitigatie |
|--------|--------|-----------|
| Scheduler start nooit omdat deps ontbreken | Medium | Non-fatal logging; dependencies kunnen later worden toegevoegd |
| APScheduler maakt conflicten met andere schedulers | Low | Gebruikt standaard event loop, geen expliciete loop override |

---

## QA-checks

- [x] Interne flow functioneel getest (happy path via unit tests)
- [x] Foutafhandeling getest (tests checken non-fatal fallback)
- [x] Logging gecontroleerd (`%s`-style, ASCII-only)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle services en functies zijn geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review door reviewer-prompt: APPROVED
