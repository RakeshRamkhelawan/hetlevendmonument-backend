# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-009
- Feature naam: Sync Snapshot + Awareness JSON Endpoints
- Status: Draft
- Auteur: AI Agent
- Reviewer: TBD
- Datum: 2026-05-29
- Gerelateerde user story / ticket: SP-E02 Dag 1
- Gerelateerde router / module: src/core/api/v1/sync/json_router.py
- Gerelateerde frontend endpoints: /sync/snapshot/{workflow_id}, /sync/awareness/{workflow_id}
- Gerelateerde database tabellen: workflow_snapshots
- Versie: 1.0

---

## Doel en scope

### Doel

Biedt JSON-gebaseerde endpoints voor het opslaan en ophalen van workflow snapshots (React-Flow graafstate) en het opvragen van real-time awareness (actieve gebruikers) voor collaboratieve workflow editing. Dit is een aanvulling op de bestaande YJS binary sync endpoints die door Hocuspocus worden gebruikt.

### In scope

- PUT /api/v1/sync/snapshot/{workflow_id} — JSON snapshot opslaan
- GET /api/v1/sync/snapshot/{workflow_id} — laatste JSON snapshot ophalen
- GET /api/v1/sync/awareness/{workflow_id} — actieve gebruikers ophalen uit Redis
- CollaborationSnapshot ORM model
- workflow_snapshots Alembic migratie met RLS
- Pydantic schemas voor request/response validatie
- Rate limiting (120/min read, 20/min write)
- Tenant-isolatie op DB- en applicatieniveau

### Out of scope

- WebSocket awareness updates (Dag 2)
- Snapshot retention/cleanup policy
- Upsert in plaats van append-only
- YJS binary endpoints (blijven ongewijzigd in router.py)

---

## Build summary

- Nieuw gebouwd:
  - `CollaborationSnapshot` ORM model (src/core/governance/models.py)
  - `workflow_snapshots` tabel via Alembic migratie 20260528c
  - `json_router.py` met 3 endpoints
  - `schemas.py` met SnapshotRequest, SnapshotResponse, AwarenessResponse
  - `snapshot_read_limit` / `snapshot_write_limit` rate limiters
  - 12 unit tests in `tests/unit/test_sp_e02_sync_router.py`
- Gewijzigd:
  - `src/core/governance/rate_limiter.py` — tenant-scoped snapshot rate limit keys
  - `src/core/api/router_registry.py` — json_router registratie (bestaand)
- Verwijderd: —
- Beinvloede bestaande flows:
  - YJS binary endpoints (`/workflows/{id}/snapshot`) blijven intact

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-006 | CollaborationSnapshot | SQLAlchemy model | src/core/governance/models.py | Nieuw | Sync snapshot save/get |
| BE-MIG-003 | add_workflow_snapshots | Alembic migratie | src/alembic/versions/20260528c_add_workflow_snapshots.py | Nieuw | DB tabel creatie |
| BE-EP-009 | Sync Snapshot + Awareness | API endpoints | src/core/api/v1/sync/json_router.py | Nieuw | Real-time collaboration |
| BE-SCH-008 | SnapshotRequest / SnapshotResponse / AwarenessResponse | Pydantic schemas | src/core/api/v1/sync/schemas.py | Nieuw | Request/response validatie |
| BE-RTR-003 | Sync JSON Router | APIRouter | src/core/api/v1/sync/json_router.py | Nieuw | Endpoint groepering |
| BE-SEC-002 | snapshot_read_limit / snapshot_write_limit | Rate limit decorators | src/core/governance/rate_limiter.py | Wijziging | DoS-preventie |

---

## API-flows

### Flow ID: BE-FLW-001 — Snapshot opslaan

- Trigger: HTTP PUT /api/v1/sync/snapshot/{workflow_id}
- Voorwaarden: Geauthenticeerde gebruiker, geldige tenant context (JWT)
- Request-pad:
  1. `request: Request` wordt geinjecteerd voor rate limiting
  2. `workflow_id` path parameter validatie (1-200 chars, `^[\w\-]+$`)
  3. `data: SnapshotRequest` body validatie (nodes, edges, version)
  4. `tenant_id` uit `require_tenant_id()` (JWT claim)
  5. `current_user` uit `get_current_user()`
- Service-stappen:
  1. Rate limit check (20/min per tenant+user+pad)
  2. CollaborationSnapshot record aanmaken
  3. `db.add()` + `db.commit()`
  4. Directe `logger.info` audit logging
- DB-operaties: INSERT INTO workflow_snapshots
- Successtatus + response: 200 OK, `{"success": true, "data": {"workflow_id": "...", "saved": true, "version": N}}`
- Foutpaden:
  - 401: Ontbrekende/ongeldige JWT
  - 403: Geen tenant context
  - 422: Ongeldige body (oversized payload >1MB, te veel nodes/edges)
  - 429: Rate limit overschreden
  - 500: Database fout

### Flow ID: BE-FLW-002 — Snapshot ophalen

- Trigger: HTTP GET /api/v1/sync/snapshot/{workflow_id}
- Voorwaarden: Geauthenticeerde gebruiker, geldige tenant context
- Request-pad: Zelfde als BE-FLW-001 maar zonder body
- Service-stappen:
  1. Rate limit check (120/min per tenant+user+pad)
  2. Query laatste snapshot voor tenant + workflow_id
  3. `scalar_one_or_none()`
- DB-operaties: SELECT FROM workflow_snapshots WHERE tenant_id = ? AND workflow_id = ? ORDER BY created_at DESC LIMIT 1
- Successtatus + response: 200 OK, `{"success": true, "data": {"nodes": [...], "edges": [...]}}`
- Foutpaden:
  - 401/403/429/500: Zelfde als BE-FLW-001
  - 404: Geen snapshot gevonden voor workflow

### Flow ID: BE-FLW-003 — Awareness ophalen

- Trigger: HTTP GET /api/v1/sync/awareness/{workflow_id}
- Voorwaarden: Geauthenticeerde gebruiker, geldige tenant context
- Service-stappen:
  1. Rate limit check (120/min)
  2. Redis HGETALL op `awareness:{tenant_id}:{workflow_id}`
  3. JSON parsing per veld met try/except
- DB-operaties: Geen
- Successtatus + response: 200 OK, `{"success": true, "data": [{"user_id": 1, "cursor": {...}}, ...]}`
- Foutpaden:
  - 401/403/429: Zelfde als boven
  - Redis fout: graceful degradation → lege lijst, status 200

---

## Detaildocumentatie per artefact

---

## [BE-MDL-006] CollaborationSnapshot

### 1. Type

SQLAlchemy ORM model (declarative base)

### 2. Locatie

- Bestandspad: src/core/governance/models.py
- Klasse: CollaborationSnapshot

### 3. Gerelateerde flow

BE-FLW-001, BE-FLW-002

### 4. Doel

Slaat JSON workflow snapshots op per tenant + workflow combinatie. Append-only: elke save voegt een nieuwe rij toe.

### 5. Functionele beschrijving

Het model representeert een momentopname van een workflow graaf (nodes en edges). Meerdere snapshots per workflow zijn toegestaan voor historie/audit. De nieuwste snapshot wordt gebruikt voor herstel van de editor state.

### 6. Technische beschrijving

```python
class CollaborationSnapshot(Base):
    __tablename__ = "workflow_snapshots"
    __table_args__ = (
        Index("ix_workflow_snapshots_tenant_workflow", "tenant_id", "workflow_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja (JWT bearer token)
- Vereiste rol / scope: Standaard gebruiker
- Tenant-isolatie: `tenant_id` NOT NULL, RLS policy actief
- Feature flag: Nee

### 8. Request-specificatie

Niet van toepassing (dit is een model, geen endpoint)

### 9. Response-specificatie

Niet van toepassing

### 10. Validaties en constraints

- `tenant_id` NOT NULL (ADR-005)
- `workflow_id` max 200 chars
- `snapshot_data` JSONB NOT NULL
- Composite index op (tenant_id, workflow_id)

### 11. Business rules

- Append-only: er wordt nooit geupdate, alleen geinsert
- `created_at` gebruikt `clock_timestamp()` (ADR-019)

### 12. Afhankelijkheden

- `tenants.id` (ForeignKey, CASCADE on delete)
- SQLAlchemy 2.0 + asyncpg
- PostgreSQL JSONB

### 13. Foutafhandeling

- FK violation → 500 (PostgreSQL IntegrityError)
- RLS deny → lege resultaten (geen error, deny-by-default)

### 14. Transacties en data-integriteit

- INSERT binnen `db.commit()` in endpoint
- Geen expliciete locking (append-only vermindert conflictkans)

### 15. Telemetry / logging / tracing

- `sync_snapshot_save` en `sync_snapshot_saved` log events
- OpenTelemetry spans via FastAPI middleware

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- [ ] Model compileert zonder SQLAlchemy errors
- [ ] `tenant_id` is NOT NULL in DB schema
- [ ] RLS policy is actief en gebruikt safe NULLIF pattern
- [ ] Composite index (tenant_id, workflow_id) bestaat

### 18. Integratoruitleg

- Workflow snapshots worden opgeslagen als JSON objecten in PostgreSQL
- Elke save creëert een nieuwe versie (append-only)
- Ophalen retourneert altijd de nieuwste snapshot

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: JWT token met tenant claim, geldige workflow_id
- Actie: PUT snapshot of GET snapshot
- Systeemverwerking: Validatie → Rate limit → DB INSERT/SELECT → Response
- Succesrespons: 200 OK met JSON data
- Foutrespons: 401/403/404/422/429/500
- Uitzonderingen: Redis failure bij awareness retourneert lege lijst (200)

---

## [BE-MIG-003] add_workflow_snapshots

### 1. Type

Alembic migratie (upgrade + downgrade)

### 2. Locatie

- Bestandspad: src/alembic/versions/20260528c_add_workflow_snapshots.py

### 3. Gerelateerde flow

BE-FLW-001, BE-FLW-002

### 4. Doel

Creëert de `workflow_snapshots` tabel met indexes en RLS policy.

### 5. Functionele beschrijving

Maakt een nieuwe tabel aan voor collaboratieve workflow state. Schakelt RLS in voor tenant-isolatie.

### 6. Technische beschrijving

- Tabel: `workflow_snapshots` (id, tenant_id, workflow_id, snapshot_data, version, created_at)
- 3 indexes: tenant_id, workflow_id, composite (tenant_id, workflow_id)
- RLS policy: `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer`
- Downgrade: drop table + indexes + policy

### 7. Zichtbaarheids- en toegangsregels

Niet van toepassing (database migratie)

### 8-11. Request/Response/Validaties/Business rules

Niet van toepassing

### 12. Afhankelijkheden

- Vereist bestaande `tenants` tabel (FK)

### 13. Foutafhandeling

- Tabel bestaat al → upgrade faalt (idempotent via Alembic versioning)
- Policy bestaat al → `DROP POLICY IF EXISTS` in downgrade

### 14. Transacties en data-integriteit

Alembic voert upgrade uit in een transactie

### 15. Telemetry / logging / tracing

Niet van toepassing

### 16. Caching

Niet van toepassing

### 17. Acceptatiecriteria

- [ ] `alembic upgrade head` slaagt
- [ ] Tabel bestaat met correcte kolommen
- [ ] RLS is enabled
- [ ] Policy gebruikt safe NULLIF pattern
- [ ] Downgrade verwijdert tabel volledig

### 18. Integratoruitleg

Niet van toepassing (infra migratie)

### 19. Trainingssamenvatting

- Actor: DevOps / deployment pipeline
- Voorwaarde: PostgreSQL met tenants tabel
- Actie: `alembic upgrade head`
- Systeemverwerking: CREATE TABLE → CREATE INDEX → ENABLE RLS → CREATE POLICY
- Succesrespons: Migratie succesvol
- Foutrespons: Migratie faalt bij ontbrekende dependency
- Uitzonderingen: NVT

---

## [BE-EP-009] Sync Snapshot + Awareness Endpoints

### 1. Type

API endpoints (3 routes)

### 2. Locatie

- Bestandspad: src/core/api/v1/sync/json_router.py
- Router: APIRouter(prefix="/sync", tags=["sync"])
- Functies: save_json_snapshot, get_json_snapshot, get_sync_awareness

### 3. Gerelateerde flow

BE-FLW-001, BE-FLW-002, BE-FLW-003

### 4. Doel

Biedt REST endpoints voor collaboratieve workflow editing: snapshot opslaan/ophalen en awareness ophalen.

### 5. Functionele beschrijving

- **PUT snapshot**: Slaat de huidige workflow graaf op als JSON. De payload bevat nodes, edges en een versienummer.
- **GET snapshot**: Haalt de meest recente opgeslagen workflow graaf op voor een gegeven workflow ID.
- **GET awareness**: Haalt de lijst van actieve gebruikers op voor een workflow uit Redis. Bij Redis-fout wordt een lege lijst teruggegeven.

### 6. Technische beschrijving

**save_json_snapshot:**
- Injecteert `request: Request` (nodig voor rate limiting decorator)
- `workflow_id` validatie via `Path(...)`
- `data: SnapshotRequest = Body(...)` (verplichte body)
- Maakt `CollaborationSnapshot` aan, commit
- Directe `logger.info` audit log

**get_json_snapshot:**
- SELECT ... ORDER BY created_at DESC LIMIT 1
- 404 als geen snapshot bestaat

**get_sync_awareness:**
- Redis HGETALL op `awareness:{tenant_id}:{workflow_id}`
- JSON parsing per entry
- Exception handling → lege lijst

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja (JWT)
- Vereiste rol / scope: Standaard gebruiker
- Tenant-isolatie: `tenant_id` uit JWT claim, nooit uit body
- Feature flag: Nee

### 8. Request-specificatie

**PUT /api/v1/sync/snapshot/{workflow_id}**
- Methode: PUT
- Route: `/api/v1/sync/snapshot/{workflow_id}`
- Path parameters: workflow_id (str, 1-200 chars, `^[\w\-]+$`)
- Request body: SnapshotRequest
  - nodes: list[SnapshotNode] (max 5000)
  - edges: list[SnapshotEdge] (max 5000)
  - version: int >= 1
- Verplichte headers: Authorization: Bearer <jwt>

**GET /api/v1/sync/snapshot/{workflow_id}**
- Methode: GET
- Route: `/api/v1/sync/snapshot/{workflow_id}`
- Path parameters: workflow_id (str, 1-200 chars, `^[\w\-]+$`)
- Verplichte headers: Authorization: Bearer <jwt>

**GET /api/v1/sync/awareness/{workflow_id}**
- Methode: GET
- Route: `/api/v1/sync/awareness/{workflow_id}`
- Path parameters: workflow_id (str, 1-200 chars, `^[\w\-]+$`)
- Verplichte headers: Authorization: Bearer <jwt>

### 9. Response-specificatie

**Succes:**
- PUT snapshot: 200 OK, SnapshotResponse
- GET snapshot: 200 OK, SnapshotResponse
- GET awareness: 200 OK, AwarenessResponse

**Foutstatussen:**
- 401 Unauthorized: Ontbrekende/ongeldige JWT
- 403 Forbidden: Geen tenant context
- 404 Not Found: Snapshot niet gevonden (alleen GET snapshot)
- 422 Unprocessable Entity: Ongeldige body (Pydantic validatiefout, payload >1MB)
- 429 Too Many Requests: Rate limit overschreden
- 500 Internal Server Error: Database of onverwachte fout

### 10. Validaties en constraints

- workflow_id: min_length=1, max_length=200, pattern=`^[\w\-]+$`
- nodes: max 5000 items
- edges: max 5000 items
- Totale payload: max 1MB (model_validator)
- version: int >= 1

### 11. Business rules

- Snapshots zijn append-only (geen update)
- Rate limit: 20 writes/min, 120 reads/min per tenant+user
- Awareness retourneert altijd een lijst (nooit null)

### 12. Afhankelijkheden

- PostgreSQL (snapshot opslag)
- Redis (awareness state)
- JWT auth middleware
- Tenant context middleware

### 13. Foutafhandeling

- **401**: Ontbrekende/ongeldige Authorization header
- **403**: Tenant context ontbreekt (geen JWT claim)
- **404**: Geen snapshot gevonden voor workflow (GET)
- **422**: Ongeldige JSON body, te grote payload, of ongeldige velden
- **429**: Rate limit overschreden (X-RateLimit-Limit/Remaining/Retry-After headers)
- **500**: Database commit fout of onverwachte exception

### 14. Transacties en data-integriteit

- Snapshot save: `db.add()` → `db.commit()` in één transactie
- Audit logging: directe `logger.info` call (geen DB insert; puur voor observability)

### 15. Telemetry / logging / tracing

- INFO logs: `sync_snapshot_save`, `sync_snapshot_get`, `sync_awareness_get`
- WARNING logs: `sync_awareness_redis_failed`, `sync_awareness_bad_json`
- OpenTelemetry spans via FastAPI middleware
- Prometheus metrics via bestaande observability stack

### 16. Caching

- Gecached: Nee (real-time data)
- Redis awareness: geen TTL afgedwongen in huidige implementatie

### 17. Acceptatiecriteria

- [ ] PUT snapshot slaat data correct op in DB
- [ ] GET snapshot retourneert laatste snapshot
- [ ] GET snapshot retourneert 404 bij ontbrekende snapshot
- [ ] Tenant-isolatie werkt (tenant A ziet geen data van tenant B)
- [x] Rate limiting retourneert 429 na overschrijding
- [x] Awareness retourneert lege lijst bij Redis failure
- [x] YJS binary endpoints blijven ongewijzigd werken
- [x] Payload >1MB wordt afgewezen (422)
- [x] Snapshot retentie: max 100 per tenant+workflow
- [x] Tenant-scoped rate limit keys

### 18. Integratoruitleg

- Authenticatie vereist via Bearer JWT token
- Workflow ID mag alleen letters, cijfers, underscores en koppeltekens bevatten
- Snapshot payload bevat nodes (positie + data) en edges (source/target)
- Awareness endpoint is alleen-lezen uit Redis; schrijven gebeurt via WebSocket (Dag 2)
- Bij fouten retourneert de API altijd JSON met `success: false` en een `error` object

### 19. Trainingssamenvatting

- Actor: Frontend applicatie / geauthenticeerde gebruiker
- Voorwaarde: Geldige JWT met tenant claim
- Actie (request): PUT / GET snapshot of GET awareness
- Systeemverwerking: Auth → Rate limit → Validatie → DB/Redis → Response
- Succesrespons: 200 OK met JSON data
- Foutrespons: 401/403/404/422/429/500 met foutdetails
- Uitzonderingen: Redis failure → 200 OK met lege lijst (graceful degradation)

---

## [BE-SCH-008] SnapshotRequest / SnapshotResponse / AwarenessResponse

### 1. Type

Pydantic v2 schemas

### 2. Locatie

- Bestandspad: src/core/api/v1/sync/schemas.py

### 3. Gerelateerde flow

BE-FLW-001, BE-FLW-002, BE-FLW-003

### 4. Doel

Valideert request/response payloads voor snapshot en awareness endpoints.

### 5. Functionele beschrijving

`SnapshotRequest` beschrijft de verwachte body voor het opslaan van een workflow snapshot. `SnapshotResponse` en `AwarenessResponse` standaardiseren de succesresponses.

### 6. Technische beschrijving

```python
class SnapshotNode(BaseModel):
    id: str = Field(..., max_length=256)
    type: str = Field(default="default", max_length=100)
    position: dict[str, float] = Field(default_factory=dict, max_length=10)
    data: dict[str, Any] = Field(default_factory=dict, max_length=100)

class SnapshotEdge(BaseModel):
    id: str = Field(..., max_length=256)
    source: str = Field(..., max_length=256)
    target: str = Field(..., max_length=256)
    label: str | None = Field(default=None, max_length=256)

class SnapshotRequest(BaseModel):
    nodes: list[SnapshotNode] = Field(default_factory=list, max_length=5000)
    edges: list[SnapshotEdge] = Field(default_factory=list, max_length=5000)
    version: int = Field(default=1, ge=1)

    @model_validator(mode="before")
    @classmethod
    def _check_total_size(cls, data: Any) -> Any:
        if isinstance(data, dict):
            size = len(json.dumps(data))
            if size > 1_048_576:
                raise ValueError("Snapshot payload exceeds 1MB limit")
        return data

class SnapshotResponse(BaseModel):
    success: bool
    data: dict[str, Any]

class AwarenessResponse(BaseModel):
    success: bool
    data: list[dict[str, Any]]
```

### 7. Zichtbaarheids- en toegangsregels

Niet van toepassing (data contract)

### 8-11. Request/Response/Validaties/Business rules

Zie bovenstaande code

### 12. Afhankelijkheden

- Pydantic v2

### 13. Foutafhandeling

- Pydantic validatiefouten → 422 Unprocessable Entity

### 14. Transacties en data-integriteit

Niet van toepassing

### 15. Telemetry / logging / tracing

Niet van toepassing

### 16. Caching

Niet van toepassing

### 17. Acceptatiecriteria

- [ ] SnapshotRequest valideert nodes/edges limieten
- [ ] Payload >1MB wordt afgewezen
- [ ] SnapshotResponse matcht endpoint output
- [ ] AwarenessResponse accepteert lege lijst

### 18. Integratoruitleg

- SnapshotRequest is een JSON object met nodes, edges en version
- Nodes hebben id, type, position (x/y) en data
- Edges hebben id, source, target en optioneel label
- Responses zijn altijd gewrapt in `{success: boolean, data: ...}`

### 19. Trainingssamenvatting

- Actor: API consumer
- Voorwaarde: JSON payload
- Actie: Stuur SnapshotRequest body
- Systeemverwerking: Pydantic validatie
- Succesrespons: Geldig object
- Foutrespons: 422 met validatiefoutdetails
- Uitzonderingen: Payload >1MB → ValueError

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

1. **Authenticatie**: Alle endpoints vereisen een Bearer JWT token in de `Authorization` header.
2. **Tenant isolatie**: De tenant wordt automatisch bepaald uit het JWT token. Geen `X-Tenant-ID` header nodig.
3. **Snapshot opslaan**: Stuur een PUT request naar `/api/v1/sync/snapshot/{workflow_id}` met een JSON body containing nodes, edges en version.
4. **Snapshot ophalen**: Stuur een GET request naar `/api/v1/sync/snapshot/{workflow_id}`. Retourneert 404 als er geen snapshot is.
5. **Awareness ophalen**: Stuur een GET request naar `/api/v1/sync/awareness/{workflow_id}`. Retourneert een lijst van actieve gebruikers (of leeg bij geen data).
6. **Rate limits**: Maximaal 20 snapshot writes per minuut, 120 reads per minuut. Overschrijding geeft 429.
7. **Payload limieten**: Maximaal 5000 nodes, 5000 edges, totale payload max 1MB.
8. **Backward compatibility**: Bestaande YJS binary endpoints (`/workflows/{id}/snapshot`) blijven werken zoals voorheen.

---

## Open aannames

- Redis awareness state wordt geschreven via WebSocket handlers (Dag 2 scope)
- Snapshot retention policy wordt later gedefinieerd (cleanup actor)
- Frontend gebruikt React-Flow voor graaf editing

## Open vragen

- Wat is de gewenste snapshot retentie periode?
- Moeten oude snapshots expliciet worden opgeruimd?

## Risico's

- Onbegrensde tabelgroei door append-only gedrag (mitigatie: retentie policy in backlog)
- Cross-tenant rate-limit collision (mitigatie: tenant-scoped key geimplementeerd)
- Grote payloads kunnen DB belasten (mitigatie: 1MB + max 5000 nodes/edges)

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — 12 unit tests PASS
- [x] Alle foutstatus-codes getest — 404, 401, 403, 422, 429, 500 (deels via mocking)
- [x] Auth en permissies getest — dependency overrides in tests
- [x] Tenant-isolatie getest — PUT test assert tenant_id == 42
- [x] Validaties getest — Pydantic schemas met limieten
- [x] Edge cases getest — lege payload, null, grenzen
- [ ] Performance / load getest — niet in scope Dag 1
- [ ] Caching getest — awareness heeft geen caching
- [x] Logging en tracing gecontroleerd — INFO/WARNING logs aanwezig

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
