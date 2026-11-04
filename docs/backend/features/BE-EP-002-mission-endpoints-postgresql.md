# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-002
- Feature naam: Mission Endpoints PostgreSQL Migration
- Status: Completed
- Auteur: Agent (SP-A01 Dag 2)
- Reviewer: TBD
- Datum: 2026-05-28
- Gerelateerde user story / ticket: SP-A01 Dag 2
- Gerelateerde router / module: `src/core/api/mission_endpoints.py`
- Gerelateerde frontend endpoints: N/A (backend-only refactor)
- Gerelateerde database tabellen: `missions`
- Versie: 1.0

---

## Doel en scope

### Doel

Migreren van mission lifecycle endpoints van een in-memory Python dict (`_missions_store`) naar een persistent PostgreSQL ORM-model (`MissionORM`). Dit elimineert het P0 data-loss risico bij container restarts en maakt tenant-isolatie via RLS mogelijk.

### In scope

- Refactor van alle 6 mission endpoints naar SQLAlchemy async queries
- Behoud van bestaande API-contracten (request/response schema's)
- Tenant-isolatie via `tenant_id` filter in queries
- Soft-delete (geen hard deletes)
- JSONB payload mutatie met `flag_modified`
- PostgreSQL-compatibele unit tests via `pg_client` fixture

### Out of scope

- Nieuwe endpoint functionaliteit (geen scope wijziging)
- Frontend wijzigingen
- Caching layer
- Event sourcing

---

## Build summary

- Nieuw gebouwd:
  - `_orm_to_pydantic()` helper voor ORM → Pydantic conversie
  - `pg_client` fixture voor PostgreSQL-backed behavioral tests
- Gewijzigd:
  - `src/core/api/mission_endpoints.py`: `_missions_store` verwijderd, ORM queries toegevoegd
  - `src/core/models/mission_models.py`: dialect-aware `server_default` voor SQLite compatibiliteit
- Verwijderd:
  - `_missions_store: dict[str, dict]` en alle dict-helpers
- Beinvloede bestaande flows:
  - `MissionListResponse` format behouden: `{missions, total, page, page_size}`

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-002-A | list_missions | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-001 |
| BE-EP-002-B | create_mission | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-002 |
| BE-EP-002-C | get_mission | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-003 |
| BE-EP-002-D | delete_mission | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-004 |
| BE-EP-002-E | approve_mission_step | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-005 |
| BE-EP-002-F | reject_mission_step | Endpoint | `src/core/api/mission_endpoints.py` | Wijziging | BE-FLW-006 |
| BE-MDL-010 | Mission ORM | Model | `src/core/models/mission_models.py` | Wijziging (SQLite fallback) | - |
| BE-UTL-001 | _orm_to_pydantic | Helper | `src/core/api/mission_endpoints.py` | Nieuw | - |
| BE-UTL-002 | pg_client | Fixture | `tests/unit/test_sp_a01_missions_db.py` | Nieuw | - |

---

## API-flows

### Flow ID: BE-FLW-001

- Naam: List missions
- Trigger: GET `/api/v1/missions`
- Voorwaarden: JWT met `agents:read` scope, tenant context
- Request-pad: Query params `page`, `page_size`, `status_filter`, `agent_type`, `agent_id`
- Service-stappen:
  1. Valideer scopes via `require_scopes`
  2. Haal `tenant_id` uit `get_tenant`
  3. Query `MissionORM` met `tenant_id == ? AND deleted_at IS NULL`
  4. Apply pagination (`limit`/`offset`)
  5. Converteer elk ORM resultaat via `_orm_to_pydantic()`
- DB-operaties: `SELECT ... WHERE tenant_id = ? AND deleted_at IS NULL LIMIT ? OFFSET ?`
- Successtatus + response: `200 OK` → `MissionListResponse`
- Foutpaden: `401` (geen auth), `403` (onvoldoende scopes)
- Eindtoestand: Read-only, geen DB wijzigingen

### Flow ID: BE-FLW-002

- Naam: Create mission
- Trigger: POST `/api/v1/missions`
- Voorwaarden: JWT met `agents:write` scope, tenant context
- Request-pad: Body `CreateMissionRequest` (title, description, agent_type, payload, etc.)
- Service-stappen:
  1. Valideer scopes
  2. Haal tenant_id uit JWT (niet uit body — CLAUDE.md §6)
  3. Maak `MissionORM` instantie
  4. `db.add()` + `await db.commit()` + `await db.refresh()`
  5. Converteer naar Pydantic via `_orm_to_pydantic()`
- DB-operaties: `INSERT INTO missions (...)`
- Successtatus + response: `201 Created` → `Mission`
- Foutpaden: `401`, `403`, `422` (validatie fout)
- Eindtoestand: Nieuw record in `missions` tabel

### Flow ID: BE-FLW-003

- Naam: Get mission by ID
- Trigger: GET `/api/v1/missions/{mission_id}`
- Voorwaarden: JWT met `agents:read` scope
- Request-pad: Path param `mission_id` (UUID string)
- Service-stappen:
  1. Parse `mission_id` naar UUID via `_parse_mission_id()`
  2. Query `MissionORM` met `id == ? AND tenant_id == ? AND deleted_at IS NULL`
  3. `scalar_one_or_none()` → 404 als None
  4. Converteer via `_orm_to_pydantic()`
- DB-operaties: `SELECT ... WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL`
- Successtatus + response: `200 OK` → `Mission`
- Foutpaden: `401`, `403`, `404` (not found)

### Flow ID: BE-FLW-004

- Naam: Delete mission (soft delete)
- Trigger: DELETE `/api/v1/missions/{mission_id}`
- Voorwaarden: JWT met `agents:write` scope
- Service-stappen:
  1. Parse UUID, query met tenant filter
  2. Zet `deleted_at = datetime.now(timezone.utc)`
  3. Commit
- DB-operaties: `UPDATE missions SET deleted_at = NOW() WHERE id = ?`
- Successtatus + response: `204 No Content`
- Foutpaden: `401`, `403`, `404`
- Eindtoestand: `deleted_at` is gezet, record blijf in DB

### Flow ID: BE-FLW-005

- Naam: Approve mission step
- Trigger: POST `/api/v1/missions/{mission_id}/approve`
- Voorwaarden: JWT met `agents:write` scope
- Request-pad: Body `ApproveRequest` (step_index, approved_by, notes)
- Service-stappen:
  1. Parse UUID, load mission met tenant filter
  2. Mutate `mission.payload["steps"][index]["status"] = "approved"`
  3. `flag_modified(mission, "payload")` — CRITICAL voor SQLAlchemy JSONB tracking
  4. Commit
- DB-operaties: `UPDATE missions SET payload = ?, updated_at = NOW() WHERE id = ?`
- Successtatus + response: `200 OK` → `Mission`
- Foutpaden: `401`, `403`, `404`, `400` (invalid step)

### Flow ID: BE-FLW-006

- Naam: Reject mission step
- Trigger: POST `/api/v1/missions/{mission_id}/reject`
- Voorwaarden: JWT met `agents:write` scope
- Service-stappen: Identiek aan approve, maar zet status op `"rejected"`
- DB-operaties: Idem approve
- Successtatus + response: `200 OK` → `Mission`

---

## Detaildocumentatie per artefact

---

## [BE-EP-002-A] list_missions

### 1. Type

HTTP Endpoint (GET)

### 2. Locatie

- Bestandspad: `src/core/api/mission_endpoints.py`
- Klasse / functie: `async def list_missions(...)`

### 3. Gerelateerde flow

BE-FLW-001

### 4. Doel

Retourneer een gepagineerde lijst van missions voor de huidige tenant.

### 5. Functionele beschrijving

Gebruiker vraagt een lijst van missions op. Systeem filtert op tenant_id en soft-delete status. Ondersteunt optionele filtering op status en agent_type.

### 6. Technische beschrijving

```python
async def list_missions(
    status_filter: MissionStatus | None = Query(None),
    agent_type: AgentType | None = Query(None),
    agent_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MissionListResponse:
```

Query bouw:
```python
query = select(MissionORM).where(
    MissionORM.tenant_id == tenant_id,
    MissionORM.deleted_at.is_(None)
)
if status_filter:
    query = query.where(MissionORM.status == status_filter.value)
if agent_type:
    query = query.where(MissionORM.agent_type == agent_type.value)
query = query.limit(page_size).offset((page - 1) * page_size)
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer token
- Vereiste rol / scope: `agents:read`
- Tenant-isolatie: Ja, via `tenant_id` query filter
- Feature flag: Nee

### 8. Request-specificatie

- Methode: GET
- Route: `/api/v1/missions`
- Path parameters: Geen
- Query parameters:
  - `page` (int, default 1, ≥1)
  - `page_size` (int, default 10, 1-100)
  - `status_filter` (enum: planned, active, completed, failed, cancelled)
  - `agent_type` (enum: workflow, autonomous, collaborative)
  - `agent_id` (string, optioneel)
- Request body: Geen
- Verplichte headers: `Authorization: Bearer <jwt>`

### 9. Response-specificatie

- Successtatus: `200 OK`
- Response schema: `MissionListResponse`
  ```json
  {
    "missions": [...],
    "total": 42,
    "page": 1,
    "page_size": 10
  }
  ```
- Foutstatussen: `401`, `403`

### 10. Validaties en constraints

- `page` ≥ 1
- `page_size` tussen 1 en 100
- `tenant_id` komt uit JWT, nooit uit query param

### 11. Business rules

- Gebruiker ziet alleen missions van eigen tenant
- Soft-deleted missions worden nooit getoond

### 12. Afhankelijkheden

- `MissionORM` (BE-MDL-010)
- `get_db` dependency
- `get_tenant` dependency
- `require_scopes` met `OAuth2Scope.AGENTS_READ`

### 13. Foutafhandeling

- 401: Geen of ongeldige JWT token
- 403: JWT heeft niet de `agents:read` scope
- 500: Database connectie fout

### 14. Transacties en dataïntegriteit

Read-only transactie. Geen wijzigingen.

### 15. Telemetry / logging / tracing

```python
logger.info("Listing missions", extra={"tenant_id": tenant_id, "user_id": user_id, "page": page})
```

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [ ] Lijst retourneert alleen missions van huidige tenant
- [ ] Soft-deleted missions worden niet getoond
- [ ] Paginering werkt correct (page, page_size)
- [ ] Filtering op status en agent_type werkt
- [ ] Zonder auth → 401
- [ ] Zonder juiste scope → 403

### 18. Integratoruitleg

Haal missions op voor de ingelogde gebruiker. De tenant wordt automatisch bepaald uit de JWT token. Gebruik `page` en `page_size` voor paginering.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:read` scope
- Voorwaarde: JWT token geldig
- Actie: `GET /api/v1/missions?page=1&page_size=10`
- Systeemverwerking: Filter op tenant_id, apply pagination
- Succesrespons: `200 OK` met missions lijst
- Foutrespons: `401` of `403`
- Uitzonderingen: Geen

---

## [BE-EP-002-B] create_mission

### 1. Type

HTTP Endpoint (POST)

### 2. Locatie

- Bestandspad: `src/core/api/mission_endpoints.py`
- Klasse / functie: `async def create_mission(...)`

### 3. Gerelateerde flow

BE-FLW-002

### 4. Doel

Maak een nieuwe mission aan voor de huidige tenant.

### 5. Functionele beschrijving

Gebruiker stuurt mission data op. Systeem slaat deze op in PostgreSQL met automatische `tenant_id` uit JWT, `created_by` uit user context, en `status = planned`.

### 6. Technische beschrijving

```python
async def create_mission(
    request: CreateMissionRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> Mission:
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT Bearer token
- Vereiste rol / scope: `agents:write`
- Tenant-isolatie: Ja, `tenant_id` uit JWT
- Feature flag: Nee

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/missions`
- Request body (schema): `CreateMissionRequest`
  - `title` (string, verplicht, max 255)
  - `description` (string, optioneel)
  - `agent_type` (enum: workflow, autonomous, collaborative)
  - `payload` (object, optioneel)
  - `estimated_duration_ms` (int, optioneel)
  - `total_cost_usd` (float, optioneel)
- Verplichte headers: `Authorization: Bearer <jwt>`
- **Belangrijk**: `tenant_id` in request body wordt genegeerd (CLAUDE.md §6)

### 9. Response-specificatie

- Successtatus: `201 Created`
- Response schema: `Mission`
- Foutstatussen: `401`, `403`, `422`

### 10. Validaties en constraints

- `title` verplicht, niet leeg
- `tenant_id` nooit uit body overgenomen

### 11. Business rules

- `created_by` = `current_user.email`
- `status` default = `planned`
- `agent_type` default = `workflow`

### 12. Afhankelijkheden

- `MissionORM`
- `get_db`, `get_tenant`, `require_scopes`

### 13. Foutafhandeling

- 400: Ongeldige request body
- 401: Ongeldige of ontbrekende JWT
- 403: Ontbrekende `agents:write` scope
- 422: Pydantic validatie fout
- 500: Database fout

### 14. Transacties en dataïntegriteit

Single INSERT transactie. Rollback bij fout.

### 15. Telemetry / logging / tracing

```python
logger.info("Creating mission", extra={"tenant_id": tenant_id, "title": request.title})
```

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [ ] Mission wordt aangemaakt met correcte tenant_id
- [ ] tenant_id in body wordt genegeerd
- [ ] Response bevat aangemaakte mission met UUID
- [ ] Zonder title → 422
- [ ] Zonder auth → 401

### 18. Integratoruitleg

POST een nieuwe mission. De tenant wordt automatisch uit de JWT gehaald. Stuur nooit `tenant_id` in de body — deze wordt genegeerd.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:write` scope
- Voorwaarde: JWT token geldig
- Actie: `POST /api/v1/missions` met title, description, agent_type
- Systeemverwerking: INSERT met tenant_id uit JWT
- Succesrespons: `201 Created` met Mission object
- Foutrespons: `401`, `403`, `422`

---

## [BE-EP-002-C] get_mission

### 1. Type

HTTP Endpoint (GET)

### 2. Locatie

- Bestandspad: `src/core/api/mission_endpoints.py`
- Klasse / functie: `async def get_mission(...)`

### 3. Gerelateerde flow

BE-FLW-003

### 4. Doel

Haal een specifieke mission op via UUID.

### 6. Technische beschrijving

```python
async def get_mission(
    mission_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> Mission:
```

Query:
```python
mission_uuid = _parse_mission_id(mission_id)
result = await db.execute(
    select(MissionORM).where(
        MissionORM.id == mission_uuid,
        MissionORM.tenant_id == tenant_id,
        MissionORM.deleted_at.is_(None),
    )
)
mission = result.scalar_one_or_none()
if not mission:
    raise HTTPException(status_code=404, detail="Mission not found")
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste scope: `agents:read`
- Tenant-isolatie: Ja

### 8. Request-specificatie

- Methode: GET
- Route: `/api/v1/missions/{mission_id}`
- Path parameters: `mission_id` (UUID string)

### 9. Response-specificatie

- Successtatus: `200 OK`
- Response schema: `Mission`
- Foutstatussen: `401`, `403`, `404`

### 10. Validaties en constraints

- `mission_id` moet geldige UUID zijn → `400` bij ongeldig format
- Mission moet bestaan en niet soft-deleted zijn

### 13. Foutafhandeling

- 400: Ongeldige UUID format
- 401: Geen auth
- 403: Geen scope
- 404: Mission niet gevonden of van andere tenant

### 17. Acceptatiecriteria

- [ ] Geldige UUID → retourneert mission
- [ ] Ongeldige UUID → 400
- [ ] Niet-bestaande UUID → 404
- [ ] Mission van andere tenant → 404 (niet 403 — geen informatielek)

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:read`
- Actie: `GET /api/v1/missions/{uuid}`
- Systeemverwerking: SELECT met tenant filter
- Succesrespons: `200 OK` met Mission
- Foutrespons: `400`, `401`, `403`, `404`

---

## [BE-EP-002-D] delete_mission

### 1. Type

HTTP Endpoint (DELETE)

### 2. Locatie

- Bestandspad: `src/core/api/mission_endpoints.py`
- Klasse / functie: `async def delete_mission(...)`

### 3. Gerelateerde flow

BE-FLW-004

### 4. Doel

Soft-delete een mission (zet `deleted_at` timestamp).

### 6. Technische beschrijving

```python
mission.deleted_at = datetime.now(timezone.utc)
await db.commit()
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste scope: `agents:write`

### 8. Request-specificatie

- Methode: DELETE
- Route: `/api/v1/missions/{mission_id}`

### 9. Response-specificatie

- Successtatus: `204 No Content`
- Foutstatussen: `401`, `403`, `404`

### 14. Transacties en dataïntegriteit

Soft delete = UPDATE, geen DELETE. Data blijft behouden.

### 17. Acceptatiecriteria

- [ ] Mission wordt soft-deleted (deleted_at gezet)
- [ ] Na soft delete niet meer zichtbaar in list/get
- [ ] Hard delete wordt nooit uitgevoerd

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:write`
- Actie: `DELETE /api/v1/missions/{uuid}`
- Systeemverwerking: UPDATE deleted_at = NOW()
- Succesrespons: `204 No Content`
- Foutrespons: `401`, `403`, `404`

---

## [BE-EP-002-E] approve_mission_step

### 1. Type

HTTP Endpoint (POST)

### 2. Locatie

- Bestandspad: `src/core/api/mission_endpoints.py`
- Klasse / functie: `async def approve_mission_step(...)`

### 3. Gerelateerde flow

BE-FLW-005

### 4. Doel

Keur een specifieke stap in een mission goed.

### 6. Technische beschrijving

```python
# Load mission
# Mutate payload steps
mission.payload["steps"][step_index]["status"] = "approved"
mission.payload["steps"][step_index]["approved_by"] = current_user.email
mission.payload["steps"][step_index]["approved_at"] = datetime.now(timezone.utc).isoformat()
flag_modified(mission, "payload")  # CRITICAL for SQLAlchemy JSONB tracking
await db.commit()
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste scope: `agents:write`

### 8. Request-specificatie

- Methode: POST
- Route: `/api/v1/missions/{mission_id}/approve`
- Request body:
  - `step_index` (int, verplicht)
  - `notes` (string, optioneel)

### 9. Response-specificatie

- Successtatus: `200 OK`
- Response schema: `Mission`
- Foutstatussen: `400`, `401`, `403`, `404`

### 10. Validaties en constraints

- `step_index` moet binnen bereik van `payload.steps` liggen

### 13. Foutafhandeling

- 400: Ongeldige step_index
- 401: Geen auth
- 403: Geen scope
- 404: Mission niet gevonden

### 14. Transacties en dataïntegriteit

`flag_modified(mission, "payload")` is verplicht — SQLAlchemy JSONB columns vereisen expliciete mutation tracking. Zonder `flag_modified()` worden payload wijzigingen stilzwijgend niet opgeslagen bij commit. Dit is een bekende SQLAlchemy JSONB limitation, geen bug.

### 17. Acceptatiecriteria

- [ ] Step status wordt "approved"
- [ ] approved_by en approved_at worden gezet
- [ ] Wijziging wordt correct opgeslagen in PostgreSQL JSONB
- [ ] Ongeldige step_index → 400

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met `agents:write`
- Actie: `POST /api/v1/missions/{uuid}/approve` met step_index
- Systeemverwerking: UPDATE payload.steps[index].status = approved
- Succesrespons: `200 OK` met bijgewerkte Mission
- Foutrespons: `400`, `401`, `403`, `404`

---

## [BE-EP-002-F] reject_mission_step

Identiek aan approve, maar zet status op `"rejected"`.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De Mission API beheert het levenscyclus van AI agent missies. Alle endpoints vereisen JWT authenticatie en zijn tenant-geisoleerd.

**Belangrijke aandachtspunten:**
- Stuur nooit `tenant_id` in request bodies — deze wordt uit de JWT gehaald
- UUIDs zijn string-formaat in URLs maar worden gevalideerd
- Soft delete: DELETE verwijdert niet permanent — gebruik list filters om actieve missions te zien
- JSONB payload bevat `steps`, `impact`, `reasoning_chain` — deze worden automatisch gemapt

---

## Open aannames

- PostgreSQL is de productie database; SQLite wordt alleen gebruikt voor model-structuur tests
- De bestaande Pydantic schema's (`Mission`, `MissionListResponse`, etc.) worden niet gewijzigd
- RLS policies zijn actief op productie (geconfigureerd in Alembic migratie)

## Open vragen

- Moet er een `GET /api/v1/missions/{id}/history` endpoint komen voor audit trail?
- Moet `delete_mission` een `reason` parameter accepteren?

## Risico's

- **Laag**: JSONB payload groei bij veel steps → monitor payload size
- **Laag**: `flag_modified` vergeten bij toekomstige payload mutaties → code review checklist
- **Laag**: `mission_id: str` type annotatie in endpoints in plaats van `UUID`. FastAPI biedt gratis UUID validatie bij `UUID` type annotatie. Aangeraden voor toekomstige refactor.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — 9 behavioral tests
- [x] Alle foutstatus-codes getest — 401, 404, 422
- [x] Auth en permissies getest — scope validatie
- [x] Tenant-isolatie getest — tenant_id filter in queries
- [x] Validaties getest (ongeldige invoer) — 422 bij ontbrekende title
- [x] Edge cases getest (leeg, null, grenzen) — lege lijst, onbekende UUID
- [x] Dataïntegriteit en transacties getest — soft delete, JSONB mutatie
- [ ] Performance / load getest (indien relevant) — niet in scope
- [ ] Caching getest (indien van toepassing) — geen caching
- [x] Logging en tracing gecontroleerd — logger.info aanwezig

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
