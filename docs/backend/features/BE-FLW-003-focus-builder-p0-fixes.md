# Backend Feature Specification

## Metadata

- Feature ID: BE-FLW-003
- Feature naam: FocusBuilder P0-fixes (SP-FB-001)
- Status: review pending
- Auteur: Kimi Code CLI
- Reviewer: (toegewezen door Rakesh)
- Datum: 2026-06-19
- Gerelateerde user story / ticket: SP-FB-001, docs/audits/FOCUSBUILDER_AUDIT_2026-06-18.md
- Gerelateerde router / module: src/core/api/v1/focus_builder/
- Gerelateerde frontend endpoints: /focus-builder/* (React Flow editor)
- Gerelateerde database tabellen: flows, focus_builder_pieces_cache
- Versie: 1.0

---

## Doel en scope

### Doel

FocusBuilder (`/api/v1/focus-builder/*`) weer functioneel maken door drie productieblokkerende regressies op te heffen:

1. Lazy instantiatie van `ActivePiecesClient` zodat read-endpoints werken zonder geconfigureerde AP-credentials.
2. Een Alembic-migratie die de canonieke `flows`- en `focus_builder_pieces_cache`-tabellen aanmaakt.
3. Verwijdering van het dubbele ORM-model `FocusBuilderPieceCache` dat dezelfde tabel claimde als `PiecesCacheMetadata`.

Daarnaast worden direct daaraan gekoppelde transactionele bugs gerepareerd zodat `create_flow` DB-eerst opslaat en het repository correct met sessie-transacties omgaat.

### In scope

- `src/domains/flows/service.py` — lazy AP-client, DB-eerst `create_flow`, publieke `sync_pieces_catalog`, graceful degradatie bij ontbrekende AP-credentials.
- `src/domains/flows/repository.py` — `flush()` ipv `commit()`, verwijderen van `expunge()`.
- `src/core/focus_builder/models.py` — verwijderen van `FocusBuilderPieceCache`.
- `src/core/focus_builder/repositories.py` — aanpassen import van piece-cache model naar `PiecesCacheMetadata`.
- `src/core/database/model_registry.py` — verwijderen van `FocusBuilderPieceCache` uit registry.
- `src/core/api/v1/focus_builder/flows_router.py` — try/except rond `list_flows`.
- `src/core/api/v1/focus_builder/pieces_router.py` — aanroep naar publieke `sync_pieces_catalog()`.
- `src/alembic/versions/20260618_add_focus_builder_tables.py` — migratie voor `flows` + `focus_builder_pieces_cache` met RLS.
- Nieuwe en bijgewerkte tests.

### Out of scope

- Volledige verwijdering van legacy `src/core/focus_builder/service.py` en `FocusBuilderFlow`.
- Asynchrone AP-sync achtergrondtaak.
- Extra `sync_status` kolom op `flows`.
- Herziening van alle legacy FocusBuilder-tests buiten `test_focus_builder_phase4.py`.

---

## Build summary

- Nieuw gebouwd:
  - `src/alembic/versions/20260618_add_focus_builder_tables.py`
  - `tests/unit/domains/flows/test_service.py`
  - `tests/unit/domains/flows/test_repository.py`
  - `tests/integration/test_focus_builder_smoke.py`
- Gewijzigd:
  - `src/domains/flows/service.py`
  - `src/domains/flows/repository.py`
  - `src/core/focus_builder/models.py`
  - `src/core/focus_builder/repositories.py`
  - `src/core/database/model_registry.py`
  - `src/core/api/v1/focus_builder/flows_router.py`
  - `src/core/api/v1/focus_builder/pieces_router.py`
  - `tests/integration/test_focus_builder_phase4.py`
- Verwijderd:
  - Legacy `FocusBuilderPieceCache` ORM-model.
- Beinvloede bestaande flows:
  - `GET /api/v1/focus-builder/flows`
  - `GET /api/v1/focus-builder/pieces`
  - `POST /api/v1/focus-builder/flows`
  - `POST /api/v1/focus-builder/pieces/sync`

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-FLW-003 | FocusBuilder P0-fixes | End-to-end flow | docs/backend/features/BE-FLW-003-focus-builder-p0-fixes.md | Nieuw | Alle FB-read/write flows |
| BE-SVC-033 | FocusBuilderService lazy AP + DB-eerst create | Service | src/domains/flows/service.py | Wijziging | create_flow, get_pieces_catalog |
| BE-MDL-011 | Flow ORM model | Model | src/domains/flows/models.py | Nieuw (bestond als code, nu gemigreerd) | CRUD flows |
| BE-MDL-012 | PiecesCacheMetadata ORM model | Model | src/domains/flows/models.py | Nieuw (bestond als code, nu gemigreerd) | pieces catalog |
| BE-MIG-011 | add focus builder flows and pieces cache tables | Migratie | src/alembic/versions/20260618_add_focus_builder_tables.py | Nieuw | schema-init |
| BE-SEC-008 | RLS tenant isolation op flows | Security | src/alembic/versions/20260618_add_focus_builder_tables.py | Nieuw | alle flow queries |
| BE-RTR-005 | FocusBuilder flows router foutafhandeling | Router | src/core/api/v1/focus_builder/flows_router.py | Wijziging | list_flows |
| BE-RTR-006 | FocusBuilder pieces router sync-aanroep | Router | src/core/api/v1/focus_builder/pieces_router.py | Wijziging | sync_pieces |
| BE-UTL-034 | FlowRepository transactie-fix | Utility/Repository | src/domains/flows/repository.py | Wijziging | alle DB-operaties |

---

## API-flows

### Flow ID: BE-FLW-003-a — List flows without AP credentials

- Naam: Lijst van automation flows ophalen
- Trigger: `GET /api/v1/focus-builder/flows`
- Voorwaarden: Geauthenticeerde gebruiker; tenant_id via JWT/ContextVar; `READ` permissie.
- Request-pad:
  1. TenantMiddleware valideert JWT en zet tenant context.
  2. `get_current_user_dependency` retourneert user.
  3. `get_focus_builder_service` injecteert `FocusBuilderService` met DB-sessie en tenant_id.
  4. `service.repository.list(skip, limit)` voert query uit.
- Service-stappen:
  - `FlowRepository.list` filtert op `tenant_id` en sorteert op `updated_at DESC`.
  - Er wordt geen `ActivePiecesClient` geinstantieerd.
- DB-operaties: `SELECT ... FROM flows WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?`
- Successtatus + response: `200 OK`, `list[FlowRead]`
- Foutpaden:
  - `401 Unauthorized` — ontbrekende/ongeldige token.
  - `500 Internal Server Error` — onverwachte DB-fout (gelogd).
- Eindtoestand: Response bevat alleen flows van de huidige tenant; geen side-effects.

### Flow ID: BE-FLW-003-b — List pieces catalog without AP credentials

- Naam: Beschikbare integratie-pieces ophalen
- Trigger: `GET /api/v1/focus-builder/pieces?search=&category=`
- Voorwaarden: Geauthenticeerde gebruiker; tenant_id via JWT/ContextVar.
- Request-pad:
  1. TenantMiddleware valideert JWT.
  2. `service.get_pieces_catalog(search, category)` queryt de cache.
- Service-stappen:
  - Als cache leeg is zonder zoekterm, wordt `sync_pieces_catalog()` aangeroepen.
  - Bij ontbrekende AP-credentials wordt de `ValueError` afgevangen en lege catalogus geretourneerd.
- DB-operaties: `SELECT * FROM focus_builder_pieces_cache` (+ optionele ILIKE filter)
- Successtatus + response: `200 OK`, `{"pieces": [...], "total": N}`
- Foutpaden:
  - `401 Unauthorized` — ontbrekende/ongeldige token.
  - `500 Internal Server Error` — onverwachte fout.
- Eindtoestand: Response bevat cached pieces of lege lijst; geen crash bij ontbrekende AP-config.

### Flow ID: BE-FLW-003-c — Create flow DB-first

- Naam: Nieuwe automation flow aanmaken
- Trigger: `POST /api/v1/focus-builder/flows`
- Voorwaarden: Geauthenticeerde gebruiker; `WRITE` permissie.
- Request body: `FlowCreate` (`name`, `description`, `react_flow_graph`)
- Request-pad:
  1. Pydantic-validatie van `FlowCreate`.
  2. `service.create_flow(name, graph, created_by)` compileert en slaat op.
- Service-stappen:
  1. Compileer ReactFlow graph naar AP JSON (geen side-effects).
  2. Sla flow op in DB met `activepieces_flow_id = NULL` via `repository.create()`.
  3. Probeer AP-flow aan te maken in try/except.
  4. Bij succes: update DB-record met `activepieces_flow_id`.
  5. Bij AP-fout: log warning en retourneer flow-record.
- DB-operaties: `INSERT INTO flows ...`, mogelijk `UPDATE flows SET activepieces_flow_id = ...`
- Successtatus + response: `201 Created`, `FlowRead`
- Foutpaden:
  - `400 Bad Request` — graph validatie fout of Pydantic-fout.
  - `401 Unauthorized` — ontbrekende/ongeldige token.
  - `403 Forbidden` — onvoldoende rechten.
  - `500 Internal Server Error` — onverwachte fout.
- Eindtoestand: Flow is altijd opgeslagen in DB; AP-koppeling kan ontbreken zonder dataverlies.

### Flow ID: BE-FLW-003-d — Sync pieces catalog on demand

- Naam: Pieces catalog synchroniseren vanuit ActivePieces
- Trigger: `POST /api/v1/focus-builder/pieces/sync`
- Voorwaarden: Geauthenticeerde gebruiker (admin intentie; huidige router heeft geen expliciete admin-guard).
- Request-pad:
  1. `service.sync_pieces_catalog()` instantieert `ActivePiecesClient` lazily.
  2. AP-client haalt pieces op.
  3. `repository.upsert_piece()` per piece.
- DB-operaties: `INSERT ... ON CONFLICT (piece_name) DO UPDATE` via `upsert_piece`
- Successtatus + response: `202 Accepted`, `{"status": "sync_started", ...}`
- Foutpaden:
  - `401 Unauthorized` — ontbrekende/ongeldige token.
  - `500 Internal Server Error` — AP-credentials ontbreken of AP onbereikbaar.
- Eindtoestand: Cache bevat actuele pieces of endpoint faalt met 500.

---

## Detaildocumentatie per artefact

---

## [BE-SVC-033] FocusBuilderService lazy AP-client + DB-eerst create

### 1. Type

Service-klasse

### 2. Locatie

- Bestandspad: `src/domains/flows/service.py`
- Klasse / functie: `FocusBuilderService`

### 3. Gerelateerde flow

BE-FLW-003-a, BE-FLW-003-b, BE-FLW-003-c, BE-FLW-003-d

### 4. Doel

Orchestratie tussen React Flow UI, database en ActivePieces execution engine met veilige fallback als AP niet geconfigureerd is.

### 5. Functionele beschrijving

- Maakt het mogelijk om flows te beheren zonder dat de AP-credentials direct bij elke service-instantiatie worden gevalideerd.
- Zorgt dat een flow altijd lokaal wordt opgeslagen voordat er een externe AP-call wordt gedaan.
- Synchroniseert de pieces-catalogus op verzoek of on-demand bij een lege cache.

### 6. Technische beschrijving

- `__init__` slaat `_ap_client: ActivePiecesClient | None = None` op; er wordt geen client aangemaakt.
- `@property ap_client` maakt de client pas bij eerste toegang.
- `create_flow` doet DB-insert met `activepieces_flow_id=None`, probeert daarna AP, en update alleen bij succes.
- `get_pieces_catalog` vangt `ValueError` af bij ontbrekende AP-credentials en retourneert lege lijst.
- `sync_pieces_catalog` is publiek gemaakt (was `_sync_pieces_catalog`).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: via router afhankelijkheden.
- Vereiste rol / scope: `Permission.WRITE` voor `create_flow`.
- Tenant-isolatie: `tenant_id` wordt via dependency injectie in repository doorgegeven.
- Feature flag: geen.

### 8. Request-specificatie

Niet van toepassing (service-laag).

### 9. Response-specificatie

Niet van toepassing (service-laag).

### 10. Validaties en constraints

- `create_flow` verwacht een gecompileerde graph; validatie gebeurt in router/Pydantic.
- `ap_client` property raise `ValueError` als `AP_SERVICE_EMAIL` of `AP_SERVICE_PASSWORD` ontbreekt.

### 11. Business rules

- Een flow wordt altijd lokaal opgeslagen, onafhankelijk van AP-beschikbaarheid.
- AP-sync is best-effort; falen mag geen dataverlies of 500 op read-endpoints veroorzaken.

### 12. Afhankelijkheden

- `src.core.activepieces.client.ActivePiecesClient`
- `src.core.activepieces.transformer.FlowTransformer`
- `src.domains.flows.repository.FlowRepository`

### 13. Foutafhandeling

- `ValueError` bij ontbrekende AP-credentials wordt gelogd en genegeerd op read-paden.
- Onverwachte exceptions in `create_flow` propageren naar router (500).

### 14. Transacties en dataïntegriteit

- `repository.create` gebruikt `flush()` zodat de buitenste `get_db()`-context uiteindelijk commit.
- DB-eerst patroon voorkomt orphan AP-flows bij DB-fouten.

### 15. Telemetry / logging / tracing

- Standaard logging via `logging.getLogger(__name__)`.
- Waarschuwingen bij AP-credential-miss en AP-fouten.

### 16. Caching

- Geen (pieces-cache is de database zelf; legacy Redis-caching in `src/core/focus_builder/repositories.py` blijft bestaan maar wordt niet actief gebruikt door nieuwe service).

### 17. Acceptatiecriteria

- `FocusBuilderService` instantieert geen `ActivePiecesClient` in `__init__`.
- `GET /focus-builder/flows` retourneert 200 zonder AP-credentials.
- `GET /focus-builder/pieces` retourneert 200 en lege lijst zonder AP-credentials.
- `create_flow` slaat flow op in DB zelfs als AP-call faalt.

### 18. Integratoruitleg

- De FocusBuilder-service werkt standalone; AP-credentials zijn pas nodig bij publiceren/synchroniseren.
- Read-endpoints blijven beschikbaar zonder geconfigureerde execution engine.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker.
- Voorwaarde: JWT bevat geldige tenant_id; DB-tabellen bestaan.
- Actie: Roep flow/pieces endpoints aan.
- Systeemverwerking: Service queryt DB; AP-client wordt pas bij schrijf/sync gemaakt.
- Succesrespons: 200/201 met flow- of piece-data.
- Foutrespons: 401/403/400/500 afhankelijk van auth/validatie/onverwachte fout.
- Uitzonderingen: AP-credentials ontbreken leidt tot graceful degradatie op read, 500 op expliciete sync.

---

## [BE-UTL-034] FlowRepository transactie-fix

### 1. Type

Repository

### 2. Locatie

- Bestandspad: `src/domains/flows/repository.py`
- Klasse / functie: `FlowRepository`

### 3. Gerelateerde flow

BE-FLW-003-a, BE-FLW-003-c

### 4. Doel

Tenant-geisoleerde CRUD voor `Flow` en tenant-agnostieke cache-operaties voor `PiecesCacheMetadata` zonder dubbele commits of premature expunge.

### 5. Functionele beschrijving

- `create`, `update`, `delete` en `upsert_piece` gebruiken `flush()` ipv `commit()`.
- `get` en `list` retourneren attached instances (geen `expunge()` meer).
- Alle writes filteren op `tenant_id` waar van toepassing.

### 6. Technische beschrijving

- `self.db.flush()` zet wijzigingen naar DB binnen de huidige transactie.
- `self.db.refresh(instance)` haalt defaults (id, created_at) op.
- `commit()` wordt overgelaten aan de sessie-context manager (`get_db`).

### 7. Zichtbaarheids- en toegangsregels

- Repository krijgt `tenant_id` bij constructie; `tenant_id` komt uit JWT ContextVar.
- `PiecesCacheMetadata` heeft geen tenant_id (globale cache).

### 8. Request-specificatie

Niet van toepassing.

### 9. Response-specificatie

Niet van toepassing.

### 10. Validaties en constraints

- `create` injecteert altijd `tenant_id` uit repository in data dict.
- `get` filtert op zowel `id` als `tenant_id`.

### 11. Business rules

- Een tenant kan alleen eigen flows muteren.
- De pieces-cache is system-wide; tenant-isolatie is hier niet van toepassing.

### 12. Afhankelijkheden

- `src.domains.flows.models.Flow`
- `src.domains.flows.models.PiecesCacheMetadata`
- SQLAlchemy `AsyncSession`

### 13. Foutafhandeling

- `get` retourneert `None` bij ontbrekende of verkeerde-tenant flow.
- `update` retourneert `None` als flow niet bestaat.

### 14. Transacties en dataïntegriteit

- Enkele transactie per request via `get_db()` context manager.
- `flush()` maakt meerdere repository-operaties binnen één transactie mogelijk.

### 15. Telemetry / logging / tracing

- Geen specifieke logging in repository.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- `create` roept `commit()` niet aan.
- `list` roept `expunge()` niet aan.
- Tenant A ziet geen flows van tenant B.

### 18. Integratoruitleg

- Repository garandeert tenant-isolatie op DB-niveau voor flows.

### 19. Trainingssamenvatting

- Actor: FocusBuilderService.
- Voorwaarde: Geldige DB-sessie en tenant_id.
- Actie: CRUD-operatie op flow of piece.
- Systeemverwerking: Query/flush binnen transactie; commit door context manager.
- Succesrespons: Gewijzigd/opgehaald object.
- Foutrespons: `None` of DB-error.
- Uitzonderingen: Tenant mismatch resulteert in "not found" gedrag.

---

## [BE-MDL-011] Flow ORM model

### 1. Type

SQLAlchemy model

### 2. Locatie

- Bestandspad: `src/domains/flows/models.py`
- Klasse / functie: `Flow`

### 3. Gerelateerde flow

BE-FLW-003-a, BE-FLW-003-c

### 4. Doel

Canonieke opslag van automation flows inclusief React Flow graph en mapping naar ActivePieces.

### 5. Functionele beschrijving

- Slaat de visuele flow (React Flow graph) op als source of truth.
- Houdt AP-flow-id, project-id en versie bij voor execution.
- Bijhoudt publicatie-status, uitvoerings-teller en audit-tijdstippen.

### 6. Technische beschrijving

- Tabel: `flows`
- Kolommen: id, tenant_id, name, description, react_flow_graph (JSONB), ui_version, activepieces_flow_id, activepieces_project_id, activepieces_version, activepieces_flow_json (JSONB), is_published, last_executed_at, execution_count, created_at, updated_at, created_by.
- Indexes: id (PK), tenant_id, name, activepieces_flow_id (unique), created_by, updated_at.
- FK: tenant_id -> tenants.id, created_by -> users.id.

### 7. Zichtbaarheids- en toegangsregels

- Tenant-isolatie via RLS-policy op `flows`.

### 8. t/m 19.

Zie migratie BE-MIG-011 en repository BE-UTL-034 voor details.

---

## [BE-MDL-012] PiecesCacheMetadata ORM model

### 1. Type

SQLAlchemy model

### 2. Locatie

- Bestandspad: `src/domains/flows/models.py`
- Klasse / functie: `PiecesCacheMetadata`

### 3. Gerelateerde flow

BE-FLW-003-b, BE-FLW-003-d

### 4. Doel

Lokale cache van beschikbare ActivePieces integratie-pieces met actions/triggers metadata.

### 5. Functionele beschrijving

- Slaat per piece naam, versie, display naam, beschrijving, logo, actions, triggers, auth config en laatste sync-tijdstip op.
- Wordt gevuld door `sync_pieces_catalog`.

### 6. Technische beschrijving

- Tabel: `focus_builder_pieces_cache`
- Kolommen: id, piece_name (unique), piece_version, display_name, description, logo_url, actions (JSONB), triggers (JSONB), auth_config (JSONB), last_synced_at.
- Geen tenant_id; globale cache.

### 7. Zichtbaarheids- en toegangsregels

- Leesbaar voor alle geauthenticeerde gebruikers; schrijven via sync endpoint.

---

## [BE-MIG-011] add focus builder flows and pieces cache tables

### 1. Type

Alembic migratie

### 2. Locatie

- Bestandspad: `src/alembic/versions/20260618_add_focus_builder_tables.py`
- Klasse / functie: `upgrade`, `downgrade`

### 3. Gerelateerde flow

Schema-initialisatie

### 4. Doel

Aanmaken van `flows` en `focus_builder_pieces_cache` tabellen in productie en bestaande (test)databases die deze tabellen nog missen.

### 5. Functionele beschrijving

- Maakt `flows` tabel aan met tenant_id FK, indexes en RLS.
- Maakt `focus_builder_pieces_cache` tabel aan met unique constraint op piece_name.
- Conditie: tabellen worden alleen aangemaakt als ze nog niet bestaan (idempotent).

### 6. Technische beschrijving

- Revision ID: `20260618_add_focus_builder_tables`
- Down revision: `20260605a`
- Gebruikt `sa.inspect(bind).get_table_names()` voor idempotentie.
- RLS-policy: `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer`.
- Downgrade gebruikt `DROP TABLE IF EXISTS`.

### 7. Zichtbaarheids- en toegangsregels

- `flows`: RLS enabled.
- `focus_builder_pieces_cache`: geen RLS (globale cache).

### 12. Afhankelijkheden

- `tenants` en `users` tabellen moeten bestaan (FK).

### 14. Transacties en dataïntegriteit

- DDL wordt in één migratie-transactie uitgevoerd.
- Conditional create voorkomt fouten bij re-runnen.

### 17. Acceptatiecriteria

- `alembic upgrade head` maakt beide tabellen aan zonder fout.
- `alembic downgrade -1` verwijdert beide tabellen.

---

## [BE-SEC-008] RLS tenant isolation op flows

### 1. Type

Security policy

### 2. Locatie

- Bestandspad: `src/alembic/versions/20260618_add_focus_builder_tables.py`
- Policy naam: `tenant_isolation_policy`

### 3. Gerelateerde flow

Alle flow queries

### 4. Doel

Afdwingen dat een DB-verbinding alleen flows van de huidige tenant ziet.

### 6. Technische beschrijving

- `ALTER TABLE flows ENABLE ROW LEVEL SECURITY;`
- `CREATE POLICY tenant_isolation_policy ON flows FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer);`

### 17. Acceptatiecriteria

- Query zonder `app.current_tenant` setting ziet geen tenant-rijen.
- Query met tenant setting ziet alleen rijen van die tenant.

---

## [BE-RTR-005] FocusBuilder flows router

### 1. Type

Router

### 2. Locatie

- Bestandspad: `src/core/api/v1/focus_builder/flows_router.py`
- Klasse / functie: `list_flows`

### 3. Gerelateerde flow

BE-FLW-003-a

### 4. Doel

HTTP-router voor flow endpoints met nettere foutafhandeling op list-operaties.

### 6. Technische beschrijving

- `list_flows` heeft nu try/except rond `service.repository.list()`.
- Onverwachte DB-fouten resulteren in 500 met gestructureerde error response.

### 13. Foutafhandeling

- `500 Internal Server Error` bij onverwachte DB-fout.

---

## [BE-RTR-006] FocusBuilder pieces router

### 1. Type

Router

### 2. Locatie

- Bestandspad: `src/core/api/v1/focus_builder/pieces_router.py`
- Klasse / functie: `sync_pieces`

### 3. Gerelateerde flow

BE-FLW-003-d

### 4. Doel

HTTP-router voor pieces catalog sync.

### 6. Technische beschrijving

- Aanroep `service._sync_pieces_catalog()` vervangen door `service.sync_pieces_catalog()`.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- `GET /api/v1/focus-builder/flows` — haalt de lijst met automation flows voor de huidige tenant op. Werkt zonder ActivePieces configuratie.
- `GET /api/v1/focus-builder/pieces` — haalt de catalogus met beschikbare integratie-pieces op. Retourneert een lege lijst als de cache leeg is en ActivePieces niet geconfigureerd is.
- `POST /api/v1/focus-builder/flows` — maakt een nieuwe flow aan. De flow wordt altijd opgeslagen in de database; synchronisatie naar ActivePieces gebeurt best-effort achteraf.
- `POST /api/v1/focus-builder/pieces/sync` — forceert een synchronisatie van de pieces-catalogus vanuit ActivePieces. Vereist wel geldige AP-credentials.

---

## Open aannames

- `app.current_tenant` wordt door `TenantMiddleware` correct gezet op DB-connecties die RLS gebruiken.
- Legacy `src/core/focus_builder/service.py` en `FocusBuilderFlow` blijven bestaan; ze worden niet gebruikt door de huidige ADR-033 router.
- AP-credentials zijn optioneel voor read-paden; write/sync vereist ze.

## Open vragen

- Moet `POST /api/v1/focus-builder/pieces/sync` een expliciete admin-permissie krijgen?
- Moet de pieces-cache per tenant worden gescheiden in een toekomstige versie?

## Risico's

- Bestaande (niet-productie) databases die `flows`/`focus_builder_pieces_cache` al handmatig hadden aangemaakt kunnen afwijken van het migratie-schema; de migratie is idempotent maar past bestaande kolommen niet aan.
- Legacy `PiecesRepository` in `src/core/focus_builder/repositories.py` is nu een alias naar `PiecesCacheMetadata`; eventuele code die rechtstreeks op oude kolommen vertrouwde kan afwijken.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — smoke tests
- [x] Alle foutstatus-codes getest — unit tests + smoke tests
- [x] Auth en permissies getest — via fixtures
- [x] Tenant-isolatie getest — `test_repository.py`
- [x] Validaties getest — Pydantic + unit tests
- [x] Edge cases getest — lege cache, ontbrekende AP-credentials
- [x] Dataïntegriteit en transacties getest — `test_repository.py`
- [ ] Performance / load getest — niet relevant voor deze fix
- [ ] Caching getest — niet van toepassing op nieuwe service
- [x] Logging en tracing gecontroleerd — ruff/pyright groen

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
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
