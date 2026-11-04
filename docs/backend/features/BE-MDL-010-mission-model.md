# Backend Feature Specification — BE-MDL-010

## Metadata

- Feature ID: BE-MDL-010
- Feature naam: Mission ORM Model
- Status: APPROVED
- Auteur: Sprint Agent SP-A01
- Reviewer: code-reviewer + quality-reviewer subagents
- Datum: 2026-05-28
- Gerelateerde user story / ticket: SP-A01 — Missions store naar PostgreSQL
- Gerelateerde router / module: `src/core/api/mission_endpoints.py`
- Gerelateerde database tabellen: `missions`
- Versie: 1.0

---

## Doel en scope

### Doel

Vervang de module-level `_missions_store: dict` in `mission_endpoints.py` door een
persistent SQLAlchemy ORM model op PostgreSQL. Elimineert P0 data-loss bij
Gunicorn worker-herstart (ADR-010 multi-process deployment).

### In scope

- `Mission` SQLAlchemy ORM model
- Alembic migratie met RLS policy (ADR-005)
- Partial index voor soft-delete filtering
- Unit tests voor model constraints

### Out of scope

- Endpoint refactor (Dag 2 van SP-A01)
- Council integration met mission audit trail
- Mission search / fulltext indexing

---

## Build summary

- Nieuw gebouwd:
  - `src/core/models/mission_models.py` — `Mission` ORM model
  - `src/alembic/versions/5d4738dff74b_add_missions_table.py` — migratie + RLS
  - `tests/unit/test_sp_a01_missions_db.py` — model + migratie tests
- Gewijzigd:
  - `src/core/database/model_registry.py` — registratie van `mission_models`
  - `src/core/models/__init__.py` — export `Mission`
- Verwijderd: —
- Beinvloede bestaande flows: —

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-010 | Mission | Model | `src/core/models/mission_models.py` | Nieuw | Mission CRUD (Dag 2) |
| BE-MIG-001 | add_missions_table | Migratie | `src/alembic/versions/5d4738dff74b_add_missions_table.py` | Nieuw | — |

---

## Detaildocumentatie per artefact

---

## [BE-MDL-010] Mission

### 1. Type

SQLAlchemy 2.0 ORM Model (asyncpg-compatibel)

### 2. Locatie

- Bestandspad: `src/core/models/mission_models.py`
- Klasse: `Mission`
- Base: `src.core.database.database.Base`

### 3. Gerelateerde flow

- Mission CRUD endpoints (`src/core/api/mission_endpoints.py`) — Dag 2 refactor

### 4. Doel

Persistente opslag van missions met strict tenant-isolatie, soft-delete,
en JSONB payload voor flexibele step/impact/reasoning data.

### 5. Functionele beschrijving

Elke mission behoort tot exact een tenant. De `tenant_id` is NOT NULL
(ADR-005). Missions worden nooit hard-deleted; `deleted_at` timestamp
markeert verwijdering. Het `payload` JSONB-veld bevat de mission steps,
impact summary, en reasoning chain — data die niet frequent wordt gequery'd.

### 6. Technische beschrijving

```python
class Mission(Base):
    __tablename__ = "missions"

    id: UUID PK, server_default=gen_random_uuid()
    tenant_id: int, NOT NULL, FK(tenants.id, CASCADE), index
    user_id: int, nullable, FK(users.id, SET NULL)
    created_by: str(255), NOT NULL  # API-compatibel string identifier
    title: str(255), NOT NULL
    description: Text, nullable
    agent_type: str(50), NOT NULL, default='workflow'
    status: str(50), NOT NULL, default='planned'
    payload: JSONB, nullable  # steps, impact, reasoning_chain
    created_at: DateTime(tz), NOT NULL, server_default=clock_timestamp()
    updated_at: DateTime(tz), nullable
    deleted_at: DateTime(tz), nullable  # soft delete
```

Indexen:
- `ix_missions_tenant_id` — tenant filter queries
- `ix_missions_active` — partial index (tenant_id, created_at) WHERE deleted_at IS NULL

RLS:
- `tenant_isolation_policy` — FOR ALL USING tenant_id match met `app.current_tenant`

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT (endpoint-laag)
- Vereiste rol / scope: endpoint-afhankelijk
- Tenant-isolatie: RLS + NOT NULL tenant_id + query filters
- Feature flag: —

### 8. Request-specificatie

NVT — dit is een model, geen endpoint.

### 9. Response-specificatie

NVT — dit is een model, geen endpoint.

### 10. Validaties en constraints

- `tenant_id` NOT NULL (database constraint + RLS)
- `title` NOT NULL
- `status` default 'planned' (match bestaande API MissionStatus enum)
- `agent_type` default 'workflow'
- ForeignKey: `tenant_id -> tenants.id` ON DELETE CASCADE
- ForeignKey: `user_id -> users.id` ON DELETE SET NULL

### 11. Business rules

- Soft delete only: nooit `DELETE FROM missions` — altijd `UPDATE deleted_at`
- `created_by` bevat de string user identifier (niet alleen int FK) voor
  backward compatibility met bestaande API responses.

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- PostgreSQL 15+ (JSONB, UUID, RLS)
- `tenants` tabel bestaat
- `users` tabel bestaat

### 13. Foutafhandeling

- 500 bij database constraint violation (unhandled)
- 500 bij ontbrekende tenant_id in request context (ORM hook / RLS)

### 14. Transacties en data-integriteit

- `gen_random_uuid()` server-side — geen client-side UUID generation nodig
- `clock_timestamp()` voor created_at — werkelijke insert-tijd, niet transactie-start

### 15. Telemetry / logging / tracing

NVT op model-niveau — endpoints loggen tenant_id + user_id.

### 16. Caching

NVT.

### 17. Acceptatiecriteria

- [x] Model is importeerbaar vanuit `src.core.models.mission_models`
- [x] tenant_id is NOT NULL
- [x] UUID PK met gen_random_uuid() server_default
- [x] Soft delete kolom (deleted_at) aanwezig
- [x] clock_timestamp() voor created_at
- [x] Alembic migratie heeft werkende downgrade()
- [x] RLS policy in migratie
- [x] `alembic check` toont geen drift

### 18. Integratoruitleg

Voor downstream services: importeer `Mission` van `src.core.models.mission_models`.
Alle queries MOETEN filteren op `tenant_id` en `deleted_at IS NULL`.
Gebruik `payload` JSONB voor mission steps, impact, en reasoning chain.

### 19. Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend systeem / Endpoint handler |
| Voorwaarde | PostgreSQL bereikbaar, Alembic migratie uitgevoerd |
| Actie | ORM model aanspreken voor CRUD operaties |
| Systeemverwerking | SQLAlchemy query met automatische tenant_id filter (ORM hook ADR-004) + RLS check |
| Succesrespons | Correct model object geretourneerd |
| Foutrespons | SQLAlchemy exception bij constraint violation, 500 bij DB-fout |
| Uitzonderingen | Migratie niet uitgevoerd: tabel bestaat niet -> 500 bij startup |

---

## Open aannames

- `payload` structuur (steps, impact, reasoning_chain) wordt niet geverifieerd
  op database-niveau — validatie gebeurt in Pydantic schemas (endpoint-laag).
- `user_id` FK is nullable omdat systeem-gegenereerde missions mogelijk zijn
  zonder gekoppelde user record.

## Open vragen

- Moet `updated_at` een `onupdate=clock_timestamp()` krijgen via event listener?
  (Huidig: handmatige update in endpoint code.)

## Risico's

- Data-migratie van `_missions_store` dict naar PostgreSQL: bestaande in-memory
  data gaat verloren bij deploy. Acceptabel — productie heeft nog geen echte
  mission data (alles was sample/demo).

---

## QA-checks

- [x] Model constraints getest (NOT NULL, UUID, defaults)
- [x] Tenant-isolatie op model-niveau bevestigd (RLS + NOT NULL)
- [x] Alembic migratie getest (upgrade + downgrade)
- [x] Geen drift na `alembic check`

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Review door reviewer-prompt: APPROVED
