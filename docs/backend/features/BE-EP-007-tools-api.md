# BE-EP-007 — Tools API (9 Endpoints)

**Sprint:** SP-B02  
**Datum:** 2026-05-28  
**Status:** APPROVED

---

## Overzicht

Volledige CRUD API voor tenant-scoped tools. Vervangt de P5-stub-router. Alle 9 endpoints gebruiken async SQLAlchemy, soft-delete, versioning en JWT-gebaseerde tenant-isolatie.

**Router:** `src/core/api/v1/tools/router.py`  
**Prefix:** `/api/v1/tools`  
**Registratie:** `_register_p5_crud_routers` (altijd ingeschakeld, niet achter feature-flag)

---

## Endpoints

| Methode | Pad | Functie | Response |
|---------|-----|---------|----------|
| POST | `/` | `create_tool` | 201 ToolResponse |
| GET | `/` | `list_tools` | 200 ToolListResponse |
| GET | `/{tool_id}` | `get_tool` | 200 ToolResponse |
| PUT | `/{tool_id}` | `update_tool` | 200 ToolResponse |
| DELETE | `/{tool_id}` | `delete_tool` | 200 `{"detail": "Tool deleted"}` |
| POST | `/{tool_id}/execute` | `execute_tool` | 501 (engine niet beschikbaar) |
| POST | `/{tool_id}/clone` | `clone_tool` | 201 ToolResponse |
| GET | `/{tool_id}/versions` | `get_tool_versions` | 200 `{"data": [...], "total": N}` |
| POST | `/{tool_id}/test` | `test_tool` | 200 ToolExecutionResponse |

---

## Kernpatronen

**Tenant-isolatie:** alle queries filteren op `Tool.tenant_id == current_user.tenant_id` (uit JWT). `tenant_id` nooit uit request body geaccepteerd.

**Soft-delete:** `deleted_at.is_(None)` filter op alle GET-queries; DELETE zet `deleted_at = datetime.now(timezone.utc)`.

**Version bump (PUT):** snapshot van huidige staat opgeslagen als `ToolVersion` vóór de update; daarna `tool.version = old_version + 1`.

**Paginering:** `list_tools` en `get_tool_versions` gebruiken beide `select(func.count()).select_from(subquery)` voor de echte totaaltelling.

**Execute (501):** endpoint verifieert eerst eigenaarschap (404 bij ontbrekende tool), retourneert daarna HTTP 501 — execution engine niet gekoppeld voor dit tool-type.

---

## Trainingssamenvatting

### Flow 1: Tool aanmaken

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | JWT aanwezig; body bevat `name`, `description`, `tool_type` |
| **Actie** | `POST /api/v1/tools/` |
| **Systeemverwerking** | `Tool` aangemaakt met `tenant_id=current_user.tenant_id`; `db.add` + `commit` + `refresh`; id is auto-increment |
| **Succesrespons** | HTTP 201, `ToolResponse` met server-gegenereerd `id` en `created_at` |
| **Foutrespons** | 401/403 (auth), 422 (validatie ontbrekende velden) |
| **Uitzonderingen** | `tenant_id` in de body wordt genegeerd — altijd uit JWT |

### Flow 2: Tools oplijsten met paginering

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Geldige auth |
| **Actie** | `GET /api/v1/tools/?limit=50&skip=0` (optioneel: `status=`, `tool_type=`) |
| **Systeemverwerking** | Filter op `tenant_id + deleted_at IS NULL`; count-query voor `total`; paginering via `offset/limit` |
| **Succesrespons** | HTTP 200, `{"data": [...], "total": N, "page": 1, "per_page": 50}` |
| **Foutrespons** | 401/403 |
| **Uitzonderingen** | Soft-deleted tools worden nooit getoond |

### Flow 3: Tool updaten met versiehistorie

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Tool bestaat en `deleted_at IS NULL` |
| **Actie** | `PUT /api/v1/tools/{id}` met gedeeltelijke update-body |
| **Systeemverwerking** | (1) Snapshot van huidige staat opgeslagen als `ToolVersion(version=old_version)`; (2) velden bijgewerkt; (3) `tool.version = old_version + 1`; (4) single commit |
| **Succesrespons** | HTTP 200, bijgewerkte `ToolResponse` |
| **Foutrespons** | 404 (tool niet gevonden of soft-deleted) |
| **Uitzonderingen** | Snapshot altijd vóór de bump — race-safe |

### Flow 4: Tool clonen

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Bron-tool bestaat en is actief |
| **Actie** | `POST /api/v1/tools/{id}/clone?new_name=my_copy` |
| **Systeemverwerking** | Bron-tool geladen met tenant-filter; kloon aangemaakt met `tenant_id=current_user.tenant_id`, `version=1`, `deleted_at=None` |
| **Succesrespons** | HTTP 201, nieuwe `ToolResponse` |
| **Foutrespons** | 404 (bron niet gevonden) |
| **Uitzonderingen** | `tenant_id` van de kloon altijd uit JWT, nooit gekopieerd van de bron |
