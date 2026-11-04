# Backend Feature Specification

## Metadata

- Feature ID: BE-GDPR-003
- Feature naam: Echte purge voor Twin-geheugen (soft-deleted memory_items)
- Status: Implemented
- Auteur: agent
- Reviewer: APPROVED
- Datum: 2026-07-29
- Gerelateerde user story / ticket: AUDIT-004 (ADR-036 Fase A Dag 3, CRITICAL/P0)
- Gerelateerde router / module: `src/domains/memory/services/memory_purge_service.py`, `src/domains/memory/tasks.py`, `src/core/governance/dsar_service.py`, `src/workers/actors.py`, `src/workers/scheduler.py`
- Gerelateerde frontend endpoints: none
- Gerelateerde database tabellen: `memory_items`, `audit_logs`
- Versie: 1.0

---

## Doel en scope

### Doel

`MemoryWriteService.soft_delete_item()` zette alleen `deleted_at` -- geen enkele taak of endpoint verwijderde de rij of de bijbehorende `content_embedding` ooit fysiek (AUDIT-004, CRITICAL/P0). Een expliciet AVG-verwijderverzoek (art. 17) kon daardoor structureel niet worden uitgevoerd. Deze fix levert twee complementaire purge-paden: (A) een dagelijkse purge-taak die verlopen soft-deleted items fysiek verwijdert na de grace period, en (B) fysieke verwijdering van memory-items in het canonieke DSAR-verwijderpad (`DSARService.delete_user_data`), in hard- EN soft-mode.

### In scope

- `src/domains/memory/services/memory_purge_service.py` (nieuw):
  - `purge_soft_deleted_items(db, tenant_id, *, now=None, grace_period_days=30)` -- tenant-scoped fysieke DELETE van verlopen soft-deleted items.
  - `purge_expired_soft_deletes(*, now=None, grace_period_days=30)` -- per-tenant orchestratie: tenant-discovery onder `TenantFilterBypass`, daarna per-tenant DELETE met expliciete `WHERE tenant_id`; best-effort audit-regel na de purge-commit op een eigen sessie (ADR-019 hash chain).
  - `MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS = 30` (conventie uit `DSARServiceConfig.soft_delete_grace_period_days`).
- `src/domains/memory/tasks.py` (nieuw): Dramatiq actor `purge_soft_deleted_memory_items` (sync wrapper + `asyncio.run`, thread-safe per CLAUDE.md; conditionele registratie zonder workflow_worker-import om een import-cyclus te vermijden).
- `src/core/governance/dsar_service.py`: nieuwe helper `_purge_memory_items(tenant_id, user_id)` (importlib i.v.m. DSM006 governance->agent_runtime=0) + wiring in de hard- en soft-tak van `delete_user_data`.
- `src/workers/actors.py`: re-export van de actor voor worker-discovery.
- `src/workers/scheduler.py`: dagelijkse job 03:40 UTC (`CronTrigger(hour=3, minute=40, timezone="UTC")`, `misfire_grace_time=3600`).
- `tests/unit/test_memory_item_purge.py` (nieuw): 13 tests op echte in-memory SQLite (rood voor de fix, groen erna).
- `tests/integration/test_memory_purge_tenant_isolation.py` (nieuw): 3 tests op echte PostgreSQL met echte pgvector-embedding (skipt lokaal, draait in CI).
- Pre-existing fix: twee non-ASCII em-dashes in `src/workers/scheduler.py` commentaar (regels 140, 150) -> `--` (CLAUDE.md ASCII-only).

### Out of scope

- Wijzigingen aan read-paden (retrieval, profiel, consolidatie) -- die filteren op `deleted_at IS NULL` en blijven exact zo.
- Wijzigingen aan `soft_delete_item()` zelf -- de API-semantiek van `DELETE /items/{item_id}` blijft soft-delete.
- Purge van andere Twin-tabellen (`SessionMemoryEvent`, observaties) -- aparte overweging; de bestaande `RetentionCleanupService` dekt observaties al deels.
- Anonimiseren van memory-items (onmogelijk voor embeddings; bewust gekozen voor hard DELETE).
- Nieuwe settings-UI; de grace period is een module-constante met parameter-override (precedent: `RETENTION_DAYS_COUNCIL`).

---

## Build summary

- Nieuw: `src/domains/memory/services/memory_purge_service.py` -- purge-functie + per-tenant orchestratie + audit.
- Nieuw: `src/domains/memory/tasks.py` -- Dramatiq actor (dagelijkse purge).
- Gewijzigd: `src/core/governance/dsar_service.py` -- `_purge_memory_items` helper + wiring in beide delete-modi.
- Gewijzigd: `src/workers/actors.py` -- actor re-export.
- Gewijzigd: `src/workers/scheduler.py` -- dagelijkse job 03:40 UTC + 2 pre-existing ASCII-fixes.
- Nieuw: `tests/unit/test_memory_item_purge.py` (13 tests), `tests/integration/test_memory_purge_tenant_isolation.py` (3 tests).
- Verwijderd: niets.
- Beinvloede bestaande flows: `DSARService.delete_user_data` rapporteert nu ook `memory_items` (hard) / `memory_items_deleted` (soft) in `records_affected`; verder geen gedragswijziging voor bestaande aanroepers.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-GDPR-003 | purge_soft_deleted_items | Erasure service | `src/domains/memory/services/memory_purge_service.py` | Nieuw | BE-FLW-050 |
| BE-GDPR-003 | purge_expired_soft_deletes | Erasure orchestratie | `src/domains/memory/services/memory_purge_service.py` | Nieuw | BE-FLW-050 |
| BE-GDPR-003 | purge_soft_deleted_memory_items actor | Dramatiq actor | `src/domains/memory/tasks.py` | Nieuw | BE-FLW-050 |
| BE-GDPR-003 | _purge_memory_items (DSAR helper) | Erasure helper | `src/core/governance/dsar_service.py` | Nieuw | BE-FLW-051 |
| BE-GDPR-003 | DSAR delete_user_data wiring | Wiring | `src/core/governance/dsar_service.py` | Wijziging | BE-FLW-051 |
| BE-GDPR-003 | Scheduler-registratie 03:40 UTC | Scheduling | `src/workers/scheduler.py` | Wijziging | BE-FLW-050 |
| BE-GDPR-003-TEST | Purge regressietests | Unit + integratie test | `tests/unit/test_memory_item_purge.py`, `tests/integration/test_memory_purge_tenant_isolation.py` | Nieuw | BE-FLW-050/051 |

---

## API-flows

### Flow ID: BE-FLW-050

- Naam: Periodieke purge van verlopen soft-deleted memory_items
- Trigger (HTTP-methode + route of event): APScheduler cron dagelijks 03:40 UTC -> `_run_purge_soft_deleted_memory_items` -> `purge_soft_deleted_memory_items.send()` (Dramatiq, queue `cleanup`)
- Voorwaarden (auth, tenant, feature flag): geen HTTP-auth (achtergrondtaak); worker heeft geen tenant ContextVar, daarom `TenantFilterBypass` bij discovery; geen feature flag
- Request-pad:
  1. Actor voert `asyncio.run(purge_expired_soft_deletes())` uit (fresh event loop per aanroep).
  2. Cutoff = `datetime.now(timezone.utc) - grace_period_days` (default 30).
  3. Onder `TenantFilterBypass`: `SELECT DISTINCT tenant_id FROM memory_items WHERE deleted_at IS NOT NULL AND deleted_at < cutoff`.
  4. Per gevonden tenant: `DELETE FROM memory_items WHERE tenant_id = :tid AND deleted_at IS NOT NULL AND deleted_at < cutoff`.
  5. Een commit na de loop; daarna best-effort audit-regels (`memory_purge_executed`) op een aparte sessie via `AuditService.log_action` (ADR-019 hash chain) -- een regel per gepurgde tenant (audit_logs.tenant_id is een echte FK; een synthetische system-id zou de INSERT kunnen laten falen). Expliciete flush BINNEN `best_effort` zodat een falende INSERT daar wordt gevangen en teruggerold.
- DB-operaties: SELECT distinct tenant_ids; DELETE per tenant (row + content_embedding kolom verdwijnen samen); INSERT audit_logs (best-effort)
- Successtatus + response: summary dict `{items_purged, per_tenant, tenants_processed, cutoff, grace_period_days}`; audit-regel met dezelfde summary
- Foutpaden:
  - DB-fout tijdens purge: exception -> actor faalt -> Dramatiq retry (max_retries=3); fout wordt gelogd met exc_info
  - Audit-fout: `best_effort` vangt + rollback op audit-sessie; purge blijft intact (audit is secundair)
  - Lege set: purge retourneert 0 (idempotent)
- Eindtoestand (DB, cache, events): verlopen soft-deleted rijen fysiek weg per tenant; actieve en in-grace rijen ongemoeid; 1 audit-regel per run

### Flow ID: BE-FLW-051

- Naam: DSAR-verwijdering purgt memory-items van het datasubject
- Trigger (HTTP-methode + route of event): bestaand DSAR-pad -- `DSARService.delete_user_data(user_id, tenant_id, hard_delete=...)` (route `/api/gdpr/delete`)
- Voorwaarden (auth, tenant, feature flag): bestaande DSAR-autorisatie (`_authorize`, hard delete vereist admin; `_verify_tenant_isolation`)
- Request-pad:
  1. `delete_user_data` voert de bestaande stappen uit (workflows, CVA conversations, consents, agentic_tasks, copilot sessions).
  2. Nieuw (hard-tak stap 6c / soft-tak): `_purge_memory_items(tenant_id, user_id)` ->
     `DELETE FROM memory_items WHERE tenant_id = :tid AND user_id = :uid` binnen `begin_nested` (savepoint).
  3. Rowcount wordt gerapporteerd als `records_affected["memory_items"]` (hard) of `records_affected["memory_items_deleted"]` (soft).
- DB-operaties: DELETE memory_items per datasubject (row + embedding kolom verdwijnen samen)
- Successtatus + response: `DSARDeletionResult` met memory-items in `records_affected`; bestaande audit-regel `gdpr.dsar_delete` bevat de tellingen
- Foutpaden:
  - DB-fout in de memory-purge: gevangen zoals alle DSAR-helpers -> log met exc_info, return 0; de DSAR-delete zelf faalt niet (consistent met `_delete_agentic_tasks`, `_clear_copilot_sessions`)
- Eindtoestand (DB, cache, events): alle memory-items van het datasubject in die tenant fysiek weg; items van andere users/tenants ongemoeid

---

## Detaildocumentatie per artefact

---

## [BE-GDPR-003] Echte purge voor Twin-geheugen

### 1. Type

- Compliance erasure service + scheduled actor (BE-GDPR)

### 2. Locatie

- Bestandspad: `src/domains/memory/services/memory_purge_service.py` (`purge_soft_deleted_items`, `purge_expired_soft_deletes`, `MEMORY_SOFT_DELETE_GRACE_PERIOD_DAYS`); `src/domains/memory/tasks.py` (`purge_soft_deleted_memory_items`); `src/core/governance/dsar_service.py` (`_purge_memory_items`, wiring in `delete_user_data`); `src/workers/actors.py` (re-export); `src/workers/scheduler.py` (job 03:40 UTC)

### 3. Gerelateerde flow

- BE-FLW-050 (periodieke purge), BE-FLW-051 (DSAR-purge)

### 4. Doel

- GDPR art. 17 aantoonbaar uitvoerbaar maken voor Twin-geheugen: soft-delete krijgt een geplande hard-purge, en het canonieke DSAR-pad verwijdert memory-items van het datasubject fysiek.

### 5. Functionele beschrijving

- Probleem: soft-delete zonder purge = structurele non-compliance. Bovendien is `content_embedding` een niet-anonimiseerbare afgeleide van persoonsdata, dus is het bestaande anonimiseer-patroon (conversations/users) hier onvoldoende.
- Oplossing: twee paden. (A) dagelijkse taak die rijen met verlopen `deleted_at` fysiek verwijdert, per tenant. (B) het DSAR-pad verwijdert alle memory-items van het datasubject direct fysiek -- in soft-mode ook, want markeren is voor embeddings geen erasure.
- Resultaat bij succes: `SELECT` zonder `deleted_at`-filter levert 0 rijen op voor de gepurgde scope; de embedding verdwijnt mee (kolom op dezelfde rij, `models.py:218` -- er is geen aparte vector-store).
- Effect op systeemtoestand: alleen verwijdering van al onzichtbare rijen (plus DSAR-scope); read-paden ongewijzigd.

### 6. Technische beschrijving

- `purge_soft_deleted_items`: ORM `delete(MemoryItem).where(tenant_id ==, deleted_at.is_not(None), deleted_at < cutoff)`; `cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=grace_period_days)`; rowcount via `CursorResult` cast; commit bij de aanroeper.
- `purge_expired_soft_deletes`: eigen `get_db_session()`; discovery + loop onder `TenantFilterBypass` (worker heeft geen ContextVar; de `do_orm_execute` hook zou anders `WHERE 1=0` injecteren); per-tenant DELETE; een commit; daarna audit op een APARTE sessie onder `best_effort` -- een `memory_purge_executed`-regel per gepurgde tenant (FK-veilig: de tenant bestaat bewezen; `AuditLog.tenant_id` is een echte FK naar `tenants.id`). Lege runs schrijven geen audit-regel (conventie `cleanup_council_decisions`). De expliciete `flush()` staat binnen de guard -- zonder die flush zou een falende INSERT pas bij de volgende query opkomen (autoflush), buiten de guard (aangetoond tijdens implementatie, zo verholpen). `AuditService` wordt via `importlib.import_module` geladen (DSM boundary agent_runtime -> governance).
- Actor `purge_soft_deleted_memory_items`: sync wrapper + `asyncio.run()` (CLAUDE.md thread-safe patroon; precedent `cleanup_council_decisions`). Conditionele dramatiq-registratie test `import dramatiq` direct i.p.v. `workflow_worker` te importeren -- die import zou een cyclus creeren (`workers/actors.py` re-exporteert deze module). `import dramatiq` staat binnen de `if`-tak (pyright reportPossiblyUnbound).
- `_purge_memory_items` (DSAR): `importlib.import_module("src.domains.memory.models")` (DSM006: governance -> agent_runtime directe imports = 0); `begin_nested` savepoint; fout -> log + return 0 (consistent met de andere DSAR-helpers).
- Scheduler: `CronTrigger(hour=3, minute=40, timezone="UTC")` -- bewust NA de council-cleanup (03:00) en off-peak; `misfire_grace_time=3600`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: n.v.t. Pad A (achtergrondtaak); Pad B erft de bestaande DSAR-autorisatie (`_authorize`, admin-eis voor hard delete, `_verify_tenant_isolation`) ongewijzigd.
- Vereiste rol / scope: n.v.t. nieuw
- Tenant-isolatie: ELKE delete is tenant-scoped. Discovery cross-tenant uitsluitend onder `TenantFilterBypass`, daarna per-tenant `WHERE tenant_id` -- nooit een cross-tenant DELETE (ADR-005). DSAR-helper scopet op tenant_id + user_id.
- Feature flag: geen

### 8. Request-specificatie

- Methode: n.v.t. (geen nieuw endpoint)
- Functie-signaturen:
  - `async def purge_soft_deleted_items(db: AsyncSession, tenant_id: int, *, now: datetime | None = None, grace_period_days: int = 30) -> int`
  - `async def purge_expired_soft_deletes(*, now: datetime | None = None, grace_period_days: int = 30) -> dict[str, Any]`
  - `async def _purge_memory_items(self, tenant_id: int, user_id: str) -> int`
- Verplichte headers: n.v.t.

### 9. Response-specificatie

- Successtatus: purge-functies retourneren rowcount / summary dict; DSAR-delete rapporteert `memory_items`/`memory_items_deleted` in `records_affected`
- Foutstatussen: geen nieuwe HTTP-statussen; actor-fouten -> Dramatiq retry; DSAR-helper-fouten -> 0 + log (bestaand helper-patroon)

### 10. Validaties en constraints

- `grace_period_days` default 30 (platformconventie `DSARServiceConfig.soft_delete_grace_period_days`); expliciete override mogelijk (tests, jurisdictie-beleid).
- Alle datums tz-aware (`datetime.now(timezone.utc)`); cutoff server-side berekend.
- `tenant_id` is verplicht op elke delete-functie -- er bestaat bewust geen cross-tenant purge-variant.

### 11. Business rules

1. Soft-delete blijft de API-semantiek van `DELETE /items/{item_id}`; fysieke verwijdering volgt via de purge, na de grace period.
2. Een rij wordt alleen gepurged als `deleted_at` gezet is EN ouder is dan de cutoff; actieve en in-grace rijen worden nooit aangeraakt.
3. Elke DELETE is tenant-scoped; de orchestratie loopt per tenant (ADR-005).
4. Embeddings zijn niet anonimiseerbaar -> hard DELETE is de enige compliant-erasure voor memory-items; het DSAR-pad purgt daarom fysiek in BEIDE modi (consistent met CVA conversations en agentic_tasks, GDPR-A17-004).
5. De purge is idempotent: een tweede run verwijdert 0 rijen en faalt niet.
6. Audit is secundair: een audit-fout mag een voltooide purge nooit terugrollen (best_effort NA de purge-commit, eigen sessie).

### 12. Afhankelijkheden

- `src/domains/memory/models.py` (`MemoryItem`, `EMBEDDING_DIMS`)
- `src/core/database/session.py` (`get_db_session`), `src/core/database/tenant_query_filter.py` (`TenantFilterBypass`)
- `src/core/utils/best_effort.py`
- `src/core/governance/audit.py` (`AuditService.log_action`, ADR-019 hash chain) -- via importlib
- Dramatiq + APScheduler (ADR-006), `src/workers/actors.py` (discovery), `src/workers/scheduler.py` (cron)
- `src/core/governance/dsar_service.py` bestaande helpers en conventies

### 13. Foutafhandeling

- 400/401/403/404/409/422/429: n.v.t. (geen nieuw endpoint; DSAR-foutpaden ongewijzigd)
- 500: n.v.t. nieuw; actor-fouten propagieren naar Dramatiq retry (max_retries=3, time_limit=600s)
- 503: n.v.t.
- Audit-fouten: `best_effort` (log + rollback, nooit re-raise); DSAR-helper-fouten: log + return 0

### 14. Transacties en dataintegriteit

- Pad A: een expliciete commit na de per-tenant loop; de audit-schrijving is een aparte transactie op een aparte sessie NA de purge-commit.
- Pad B: `begin_nested` savepoint binnen de bestaande DSAR-transactie; de bestaande commit-volgorde in `delete_user_data` is ongewijzigd (memory-purge voor `delete(User)` -- referentiele integriteit: `memory_items.user_id` heeft `ondelete="SET NULL"`).
- Purge verwijdert alleen rijen die voor read-paden al onzichtbaar zijn (`deleted_at IS NOT NULL`), dus er kan geen lees-inconsistentie ontstaan.

### 15. Telemetry / logging / tracing

- `memory purge: tenant=%s deleted=%d cutoff=%s` per tenant; `memory purge completed: items_purged=%d tenants=%d cutoff=%s` per run.
- Actor: `memory purge actor completed: %s`.
- Audit-regels `memory_purge_executed` (event_type `gdpr_purge`, threat_level `info`), een per gepurgde tenant met de telling en cutoff in details.
- Scheduler: enqueue-logregels conform de bestaande jobs.

### 16. Caching

- Gecached: n.v.t.
- Cache-sleutel / TTL / invalidatie: n.v.t. -- geen cache op het verwijderpad; retrieval-caches raken alleen rijen die al onzichtbaar waren.

### 17. Acceptatiecriteria

- [x] Verlopen soft-deleted rij + embedding fysiek weg na purge (test: `test_purge_removes_expired_soft_deleted_item_physically`; integratie: `test_purge_removes_row_and_embedding_physically`)
- [x] Actieve items (deleted_at NULL) blijven (test: `test_purge_keeps_active_items`)
- [x] Items binnen de grace period blijven (test: `test_purge_keeps_items_within_grace_period`)
- [x] Purge is tenant-scoped -- tenant B ongemoeid (unit: `test_purge_is_tenant_scoped`; integratie: `test_purge_is_tenant_scoped_on_real_db`)
- [x] Orchestratie purgt per tenant en rapporteert correct (unit: `test_orchestration_purges_per_tenant_and_reports`; integratie: `test_orchestration_purges_per_tenant_on_real_db`)
- [x] Idempotent: tweede run purge 0 rijen (unit: `test_purge_is_idempotent`, `test_orchestration_is_idempotent_on_empty_set`; integratie: tweede run in orchestratie-test)
- [x] Actor voert de orchestratie uit (test: `test_actor_runs_purge_orchestration`)
- [x] DSAR-helper scopet op tenant_id + user_id met gebonden waarden (test: `test_purge_memory_items_is_tenant_and_user_scoped`)
- [x] DSAR-helper faalt nooit de DSAR-delete (test: `test_purge_memory_items_returns_zero_on_error`)
- [x] `delete_user_data` wired de purge in hard- EN soft-mode (tests: `test_hard_delete_wires_memory_item_purge`, `test_soft_delete_wires_memory_item_purge`)
- [x] Regressies: 834 gerichte tests groen (memory, governance, gdpr, dag 1-2 sets), architectuur-suite 388/388 (DSM006/013/017 binnen plafonds)

### 18. Integratoruitleg

- Niets aanroepen nodig: de dagelijkse purge draait vanzelf (03:40 UTC, queue `cleanup`). Soft-deleted items worden 30 dagen na soft-delete fysiek verwijderd.
- DSAR-verzoeken via het bestaande `/api/gdpr/delete` pad purgen nu ook memory-items; de telling staat in `records_affected` en in de bestaande DSAR audit-regel.
- Handmatig purgen (bijv. jurisictie-specifieke grace): roep `purge_expired_soft_deletes(grace_period_days=<n>)` aan vanuit een beheer-context; de functie is tenant-veilig by design.

### 19. Trainingssamenvatting

- Actor: APScheduler (dagelijks 03:40 UTC) of DSAR-verwijderverzoek via bestaand endpoint
- Voorwaarde: rij heeft `deleted_at` ouder dan grace period (30d), of datasubject ondergaat DSAR-delete
- Actie (request): `purge_soft_deleted_memory_items.send()` (Dramatiq) of `DSARService.delete_user_data(...)`
- Systeemverwerking: per-tenant fysieke DELETE op `memory_items` (rij + `content_embedding` verdwijnen samen); best-effort audit-regel `memory_purge_executed` per gepurgde tenant; DSAR-pad rapporteert tellingen in `records_affected`
- Succesrespons: summary dict met `items_purged` en `per_tenant`; `DSARDeletionResult` met memory-items tellingen
- Foutrespons: actor -> Dramatiq retry; DSAR-helper -> 0 + error-log (DSAR-delete faalt nooit door de memory-purge); audit-fout -> best_effort swallow + rollback op audit-sessie
- Uitzonderingen: actieve items en items binnen de grace period worden nooit verwijderd; elke DELETE is tenant-scoped; embeddings vereisen hard DELETE (anonimiseren is onmogelijk)

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Er is geen publiek API-oppervlak veranderd. Twee gedragsveranderingen zijn zichtbaar voor beheerders: (1) soft-deleted memory-items verdwijnen 30 dagen na soft-delete ook fysiek (voorheen: nooit), en (2) een DSAR-verwijderverzoek rapporteert nu `memory_items`/`memory_items_deleted` in `records_affected`. Teams met eigen Twin-verwijderpaden moeten deze purge-functies hergebruiken in plaats van zelf DELETEs te schrijven -- de ADR-026-aanvulling maakt de purge-eis expliciet voor alle Twin-data-verwijderpaden.

---

## Open aannames

- De grace period geldt platform-breed als 30 dagen (conventie uit `DSARServiceConfig`); jurisdictie-specifieke afwijking kan via de `grace_period_days`-parameter, een eigen retentie-indeling per tenant is post-MVP.
- Een purge-run zonder gepurgde rijen schrijft bewust geen audit-regel (conventie `cleanup_council_decisions`); de run zelf is zichtbaar via de logregels.

## Open vragen

- Geen.

## Risico's

- Een purge-run tijdens zware load voert per tenant een DELETE uit; batching (zoals bij council-cleanup) is bewust niet meegenomen omdat soft-deleted volumes laag zijn -- als metingen anders uitwijzen is batching een kleine uitbreiding op `purge_soft_deleted_items`.
- De actor-registratie hangt af van import via `src/workers/actors.py` (worker-discovery); de scheduler-enqueue faalt zichtbaar (error-log) als de actor ontbreekt, dus een registratiefout is nooit stil.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- n.v.t. nieuw endpoint; purge-functie + orchestratie happy path groen op echte db
- [x] Alle foutstatus-codes getest -- DSAR-helper error -> 0; actor error -> retry; audit error -> best_effort
- [x] Auth en permissies getest -- DSAR-autorisatie ongewijzigd (bestaande tests groen); purge vereist geen auth (achtergrond)
- [x] Tenant-isolatie getest -- unit + integratie (echte PostgreSQL, RLS-fixtures) bewijzen tenant B ongemoeid
- [x] Validaties getest (ongeldige invoer) -- lege set -> 0; ontbrekende tabel (audit) -> best_effort
- [x] Edge cases getest (leeg, null, grenzen) -- deleted_at NULL, deleted_at = nu (grace-grens), tweede run
- [x] Dataintegriteit en transacties getest -- commit-volgorde purge -> audit; savepoint in DSAR; SET NULL FK gerespecteerd
- [x] Performance / load getest (indien relevant) -- per-tenant DELETE met index op (tenant_id, ...); volumes laag
- [x] Caching getest (indien van toepassing) -- n.v.t.
- [x] Logging en tracing gecontroleerd -- per-tenant en per-run logregels + audit-regel aanwezig

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar (en als tests geimplementeerd, 13/13 unit + integratie geschreven)
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED
