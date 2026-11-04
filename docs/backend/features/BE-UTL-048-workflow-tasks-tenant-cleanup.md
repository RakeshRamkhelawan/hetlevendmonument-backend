# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-048
- Feature naam: Dramatiq Tenant Context Cleanup Fix
- Status: Implemented
- Auteur: agent
- Reviewer: APPROVED WITH MINOR GAPS
- Datum: 2026-07-28
- Gerelateerde user story / ticket: AUDIT-003
- Gerelateerde router / module: `src/core/tasks/workflow_tasks.py`, `src/core/tasks/cva_tasks.py`, `src/core/copilot/audit/report_jobs.py`
- Gerelateerde frontend endpoints: none
- Gerelateerde database tabellen: none
- Versie: 1.0

---

## Doel en scope

### Doel

Zorg dat alle Dramatiq-actors die de tenant ContextVar zetten (`execute_workflow_step`, `process_cva_message`, `generate_audit_report`) deze altijd opruimen via `set_tenant_id(None)`, ook wanneer een constructie- of verwerkingsstap faalt. Dit voorkomt dat een hergebruikte worker-thread de tenant_id van een eerdere taak blijft dragen (AUDIT-003).

### In scope

- `src/core/tasks/workflow_tasks.py`: verplaats `agent = AutonomousAgent()` naar binnen het `try`-blok zodat `finally: set_tenant_id(None)` altijd bereikt wordt.
- `src/core/tasks/cva_tasks.py`: wrap het werk na `set_tenant_id(int(tenant_id))` in een `try/finally` zodat de tenant ContextVar altijd wordt opgeruimd, ook bij exceptions tijdens CVA-verwerking.
- `src/core/copilot/audit/report_jobs.py`: wrap het werk na `set_tenant_id(tenant_id)` in een `try/finally` zodat de tenant ContextVar altijd wordt opgeruimd, ook bij exceptions tijdens rapportgeneratie.
- `tests/unit/test_workflow_tasks_tenant_cleanup.py`: regressietest voor cleanup bij constructor-fout in workflow actor.
- `tests/unit/test_cva_tasks_tenant_cleanup.py`: regressietest voor cleanup bij falende CVA-verwerking.
- `tests/unit/test_audit_report_jobs_tenant_cleanup.py`: regressietest voor cleanup bij falende rapportgeneratie.

### Out of scope

- Wijzigingen aan `AutonomousAgent` zelf.
- Wijzigingen aan tenant-validatie of Dramatiq-configuratie.
- Nieuwe endpoints, schema's of modellen.

---

## Build summary

- Gewijzigd: `src/core/tasks/workflow_tasks.py` -- `agent = AutonomousAgent()` nu binnen `try`, cleanup altijd gegarandeerd.
- Gewijzigd: `src/core/tasks/cva_tasks.py` -- werk na `set_tenant_id(int(tenant_id))` nu binnen `try/finally`, cleanup altijd gegarandeerd.
- Gewijzigd: `src/core/copilot/audit/report_jobs.py` -- werk na `set_tenant_id(tenant_id)` nu binnen `try/finally`, cleanup altijd gegarandeerd.
- Nieuw: `tests/unit/test_workflow_tasks_tenant_cleanup.py` -- regressietest voor cleanup bij constructor-fout.
- Nieuw: `tests/unit/test_cva_tasks_tenant_cleanup.py` -- regressietest voor cleanup bij falende CVA-verwerking.
- Nieuw: `tests/unit/test_audit_report_jobs_tenant_cleanup.py` -- regressietest voor cleanup bij falende rapportgeneratie.
- Verwijderd: niets.
- Beinvloede bestaande flows: Dramatiq-achtergrondtaken voor workflow-stappen, CVA-berichten, en audit-rapporten.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-048 | Workflow Tasks Tenant Context Cleanup Fix | Utility fix | `src/core/tasks/workflow_tasks.py` | Wijziging | Dramatiq workflow execution |
| BE-UTL-048 | CVA Tasks Tenant Context Cleanup Fix | Utility fix | `src/core/tasks/cva_tasks.py` | Wijziging | Dramatiq CVA message processing |
| BE-UTL-048 | Audit Report Jobs Tenant Context Cleanup Fix | Utility fix | `src/core/copilot/audit/report_jobs.py` | Wijziging | Dramatiq audit report generation |
| BE-UTL-048-TEST | Tenant cleanup regression tests | Unit test | `tests/unit/test_workflow_tasks_tenant_cleanup.py`<br>`tests/unit/test_cva_tasks_tenant_cleanup.py`<br>`tests/unit/test_audit_report_jobs_tenant_cleanup.py` | Nieuw | Dramatiq tenant cleanup |

---

## API-flows

### Flow ID: BE-FLW-048

- Naam: Dramatiq tenant context cleanup (multi-actor)
- Trigger: Dramatiq message handled by `execute_workflow_step`, `process_cva_message`, or `generate_audit_report`
- Voorwaarden (auth, tenant, feature flag): `tenant_id` moet aanwezig en valide zijn in payload; geen feature flag
- Request-pad: Dramatiq broker -> worker thread -> actor
- Service-stappen (per actor):
  1. Valideer `tenant_id` in payload.
  2. Zet tenant ContextVar via `set_tenant_id(tenant_id)`.
  3. Binnen `try`: voer actor-specifiek werk uit (agent instantiëren, CVA-bericht verwerken, rapport genereren).
  4. In `finally`: roep `set_tenant_id(None)` aan.
- DB-operaties: afhankelijk van actor; tenant context is thread-local en heeft geen directe DB-impact
- Successtatus + response: actor-specifiek; fouten propageren naar Dramatiq retry-logica
- Foutpaden:
  - Ongeldige/missende `tenant_id` -> `ValueError`/`TypeError` voor cleanup wordt niet bereikt (fail-fast vóór set).
  - Actor-specifieke constructie/verwerkingsfout -> exception propageert, cleanup draait wel door fix.
- Eindtoestand (DB, cache, events): ContextVar is gecleared; worker thread heeft geen resterende tenant context.

#### Actor: `execute_workflow_step` (`src/core/tasks/workflow_tasks.py`)

- `set_tenant_id(tenant_id)` voor `try`.
- `agent = AutonomousAgent()` binnen `try`.
- `finally: set_tenant_id(None)`.

#### Actor: `process_cva_message` (`src/core/tasks/cva_tasks.py`)

- Na validatie van `tenant_id`, `channel`, `text`: `set_tenant_id(int(tenant_id))` binnen `try`.
- Volledige CVA-verwerkingslogica (DB, service, gateway) binnen `try`.
- `finally: set_tenant_id(None)`.

#### Actor: `generate_audit_report` (`src/core/copilot/audit/report_jobs.py`)

- Binnen `async with db_manager.get_session()`: `set_tenant_id(tenant_id)` binnen `try`.
- Rapportgeneratie binnen `try`.
- `finally: set_tenant_id(None)` (binnen de sessie-context manager, zodat cleanup altijd draait voordat de sessie sluit).

---

## Detaildocumentatie per artefact

---

## [BE-UTL-048] Workflow Tasks Tenant Context Cleanup Fix

### 1. Type

Utility fix in Dramatiq actor.

### 2. Locatie

- Bestandspad: `src/core/tasks/workflow_tasks.py`
- Klasse / functie: `execute_workflow_step`

### 3. Gerelateerde flow

- BE-FLW-048 (Dramatiq tenant context cleanup)

### 4. Doel

Voorkomen van tenant-context-lekkage tussen taken op een hergebruikte Dramatiq worker-thread wanneer agent-instantiatie faalt.

### 5. Functionele beschrijving

De actor zet bij ontvangst van een taak de tenant ContextVar. Daarna probeert hij een `AutonomousAgent` te maken en de taak uit te voeren. Ongeacht of het maken van de agent of het uitvoeren van de taak faalt, moet de tenant ContextVar worden opgeruimd voordat de functie retourneert. Voor de fix stond het aanmaken van de agent vóór het `try`-blok; bij een constructiefout werd de cleanup overgeslagen.

### 6. Technische beschrijving

- De actor is een synchrone Dramatiq actor die intern `asyncio.run()` gebruikt.
- `set_tenant_id(tenant_id)` wordt aangeroepen vóór het `try`-blok omdat de tenant-validatie fail-fast moet blijven.
- `agent = AutonomousAgent()` is nu de eerste actie binnen het `try`-blok.
- `finally: set_tenant_id(None)` wordt altijd bereikt, inclusief bij exceptions in `AutonomousAgent.__init__`.
- Geen wijziging in signatuur, payload, of normaal succesgedrag.

---

## [BE-UTL-048] CVA Tasks Tenant Context Cleanup Fix

### 1. Type

Utility fix in Dramatiq actor.

### 2. Locatie

- Bestandspad: `src/core/tasks/cva_tasks.py`
- Klasse / functie: `_process_cva_message_async` (aangeroepen door `process_cva_message`)

### 3. Gerelateerde flow

- BE-FLW-048 (Dramatiq tenant context cleanup)

### 4. Doel

Voorkomen van tenant-context-lekkage tussen CVA-berichten op een hergebruikte Dramatiq worker-thread wanneer verwerking faalt.

### 5. Functionele beschrijving

Na validatie van verplichte velden (`tenant_id`, `channel`, `text`) zet de actor de tenant ContextVar. Alle vervolgstappen (user_id resolutie, DB-initialisatie, integratie ophalen, CVA-service aanroepen, gateway-verzending) worden binnen een `try/finally` uitgevoerd, zodat `set_tenant_id(None)` altijd draait.

### 6. Technische beschrijving

- `set_tenant_id(int(tenant_id))` staat nu binnen een `try`-blok.
- Alle verwerkingslogica, inclusief alle vroege `return` statements, valt binnen hetzelfde `try`-blok.
- `finally: set_tenant_id(None)` draait altijd, inclusief bij exceptions en vroege returns.
- Geen wijziging in signatuur, payload, of normaal succesgedrag.

---

## [BE-UTL-048] Audit Report Jobs Tenant Context Cleanup Fix

### 1. Type

Utility fix in Dramatiq actor.

### 2. Locatie

- Bestandspad: `src/core/copilot/audit/report_jobs.py`
- Klasse / functie: `_generate_audit_report_async` (aangeroepen door `generate_audit_report`)

### 3. Gerelateerde flow

- BE-FLW-048 (Dramatiq tenant context cleanup)

### 4. Doel

Voorkomen van tenant-context-lekkage tussen audit-rapporttaken op een hergebruikte Dramatiq worker-thread wanneer rapportgeneratie faalt.

### 5. Functionele beschrijving

Binnen de database-sessie zet de actor de tenant ContextVar via `set_tenant_id(tenant_id)` en configureert `app.current_tenant` voor de sessie. De rapportgeneratie en statusupdates vinden binnen een `try/finally` plaats, zodat `set_tenant_id(None)` altijd draait voordat de sessie wordt vrijgegeven.

### 6. Technische beschrijving

- `set_tenant_id(tenant_id)` staat nu binnen een `try`-blok, direct na `set_config('app.current_tenant', ...)`.
- De bestaande `AuditReportGenerator` try/except blijft behouden binnen het nieuwe try/finally.
- `finally: set_tenant_id(None)` draait altijd, inclusief bij exceptions in `AuditReportGenerator.__init__` of rapportgeneratie.
- Geen wijziging in signatuur, payload, of normaal succesgedrag.

---

## Gedeelde eigenschappen per actor

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: geen (Dramatiq worker, payload bevat tenant_id)
- Vereiste rol / scope: geen
- Tenant-isolatie: ContextVar wordt gezet en opgeruimd; tenant_id komt uit taak-payload, niet uit request body
- Feature flag: geen

### 8. Request-specificatie

- Methode: Dramatiq actor call (`.send` of directe aanroep)
- Route: n.v.t.
- Path parameters: n.v.t.
- Query parameters: n.v.t.
- Request body (schema): actor-specifieke payload met minimaal `tenant_id` (int of str)
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: actor-specifieke retourwaarde
- Response schema: actor-specifiek
- Foutstatussen: propagerende exception (`ValueError`, `TypeError`, `RuntimeError`) afhankelijk van faal-locatie

### 10. Validaties en constraints

- `tenant_id` moet aanwezig zijn en numeriek zijn (bestaande validatie in `set_tenant_id`).
- Actor-specifieke payloadvelden worden gevalideerd vóór het zetten van de ContextVar.

### 11. Business rules

- Tenant context moet altijd worden opgeruimd na taakverwerking (ADR-003/004/005).
- Faalpaden mogen de cleanup niet omzeilen.

### 12. Afhankelijkheden

- `src.core.middleware.tenant_context.set_tenant_id`
- `src.core.agents.autonomous_agent.AutonomousAgent` (workflow actor)
- `src.core.services.cva_service.CVAService` (CVA actor)
- `src.core.copilot.audit.report_generator.AuditReportGenerator` (audit report actor)

### 13. Foutafhandeling

- 400: n.v.t. (geen HTTP endpoint)
- 401: n.v.t.
- 403: n.v.t.
- 404: n.v.t.
- 409: n.v.t.
- 422: n.v.t.
- 429: n.v.t.
- 500: interne exception propageert naar Dramatiq retry-logica; tenant context is ondertussen opgeruimd
- 503: n.v.t.

### 14. Transacties en dataïntegriteit

- Actor-specifieke transacties blijven behouden.
- ContextVar-cleanup is een thread-local veilige operatie.

### 15. Telemetry / logging / tracing

- Bestaande logging op INFO-niveau bij start van actor blijft behouden.
- Bestaande ERROR-logging bij exception blijft behouden.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [x] Regressietest `test_cleanup_runs_when_agent_init_fails` is ROOD op de oude code.
- [x] Regressietest `test_cleanup_runs_when_agent_init_fails` is GROEN op de nieuwe code.
- [x] Regressietest `test_cleanup_runs_when_cva_processing_fails` is ROOD op de oude code.
- [x] Regressietest `test_cleanup_runs_when_cva_processing_fails` is GROEN op de nieuwe code.
- [x] Regressietest `test_cleanup_runs_when_report_generation_fails` is ROOD op de oude code.
- [x] Regressietest `test_cleanup_runs_when_report_generation_fails` is GROEN op de nieuwe code.
- [x] `set_tenant_id(None)` wordt altijd aangeroepen na `set_tenant_id(tenant_id)`, ook bij constructie/verwerkings-exceptions.
- [x] Geen regressies in bestaande `workflow_tasks`, `cva_tasks`, of `report_jobs` tests.
- [x] `ruff check` en `mypy` slagen voor gewijzigde bestanden.

### 18. Integratoruitleg

- Dit is een interne bugfix in meerdere Dramatiq-achtergrondtaken.
- Geen impact op externe API-consumenten.
- Verkleint het risico op cross-tenant data-lekkage in worker-pools.

### 19. Trainingssamenvatting

- Actor: Dramatiq worker thread
- Voorwaarde: een achtergrondtaak wordt opgepakt met `tenant_id` in payload
- Actie (request): actor-specifieke Dramatiq-aanroep
- Systeemverwerking: tenant ContextVar wordt gezet, actor-specifiek werk wordt uitgevoerd, en in `finally` wordt ContextVar opgeruimd
- Succesrespons: actor-specifiek resultaat
- Foutrespons: exception propageert, maar tenant ContextVar is opgeruimd
- Uitzonderingen: Ongeldige `tenant_id` faalt vóór het zetten van de ContextVar; constructie- en verwerkingsfouten falen binnen het `try`-blok

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Geen externe wijzigingen. Interne Dramatiq-actors zijn robuuster tegen tenant-context-lekkage.

---

## Open aannames

- `AutonomousAgent.__init__` kan in theorie exceptions gooien; de fix behandelt dit expliciet.
- `CVAService` en `ResponseGateway` operaties kunnen exceptions gooien; deze worden door het try/finally-afgedekt.
- `AuditReportGenerator.__init__` en generatiefuncties kunnen exceptions gooien; deze worden door het try/finally-afgedekt.
- Dramatiq worker threads worden hergebruikt (gedocumenteerd in ADR-011).

## Open vragen

- Geen.

## Risico's

- Minimaal: de verplaatsing van code naar `try/finally` verandert geen extern gedrag.
- Indirect risico indien andere actors hetzelfde patroon gebruiken; deze werden tijdens final review opgespoord en meegenomen (FA-001, FA-002).

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- n.v.t. (geen endpoint), actor-flows getest via unit tests
- [x] Alle foutstatus-codes getest -- n.v.t., exception-paden getest
- [x] Auth en permissies getest -- n.v.t.
- [x] Tenant-isolatie getest -- regressietests controleren cleanup voor drie actors
- [x] Validaties getest (ongeldige invoer) -- bestaande validatie blijft
- [x] Edge cases getest (leeg, null, grenzen) -- constructie- en verwerkingsfout edge cases
- [ ] Dataïntegriteit en transacties getest -- n.v.t.
- [ ] Performance / load getest -- n.v.t.
- [ ] Caching getest -- n.v.t.
- [x] Logging en tracing gecontroleerd -- geen wijziging

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
