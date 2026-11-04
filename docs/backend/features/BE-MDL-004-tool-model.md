# BE-MDL-004 — Tool ORM Model

**Sprint:** SP-B02 Dag 1  
**Datum:** 2026-05-28  
**Status:** APPROVED

---

## Overzicht

SQLAlchemy ORM model voor de `tools` tabel. Implementeert het volledige CRUD-datamodel voor tenant-scoped tool-registraties inclusief soft-delete, versioning en JSONB opslag van configuratie.

**Bestand:** `src/core/tool_broker/models.py`

---

## Model definitie

| Kolom | Type | Constraints | Default |
|-------|------|-------------|---------|
| `id` | Integer | PK, autoincrement | — |
| `tenant_id` | Integer | NOT NULL, index | — |
| `name` | String(200) | NOT NULL | — |
| `description` | Text | nullable | — |
| `tool_type` | String(50) | NOT NULL | — |
| `status` | String(20) | NOT NULL | `'active'` |
| `is_active` | Boolean | NOT NULL | `true` |
| `version` | Integer | NOT NULL | `1` |
| `deleted_at` | DateTime(tz) | nullable | — |
| `created_at` | DateTime(tz) | NOT NULL | `clock_timestamp()` |
| `updated_at` | DateTime(tz) | nullable | — |
| `code` | Text | nullable | — |
| `endpoint_url` | String(2000) | nullable | — |
| `parameters` | JSONB | nullable | — |
| `metadata_` | JSONB (col: `metadata`) | nullable | — |
| `tags` | JSONB | nullable | — |
| `timeout_seconds` | Integer | NOT NULL | `30` |
| `retry_policy` | JSONB | nullable | — |
| `usage_count` | Integer | NOT NULL | `0` |
| `created_by` | Integer | nullable | — |

**Indexen:**
- `ix_tools_tenant_id` op `tenant_id`
- `ix_tools_tenant_deleted` composiet op `(tenant_id, deleted_at)` — primair query-pad

**ADR-naleving:**
- ADR-005: `tenant_id NOT NULL`
- §11.5 CLAUDE.md: `created_at` gebruikt `clock_timestamp()` (niet `func.now()`)
- Soft-delete via nullable `deleted_at` (nooit hard delete)

---

## Trainingssamenvatting

### Flow 1: Tool aanmaken

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Geldig JWT met `tenant_id`; `name`, `description`, `tool_type` aanwezig |
| **Actie** | `POST /api/v1/tools/` met tool-configuratie |
| **Systeemverwerking** | ORM maakt `Tool` aan met `tenant_id=current_user.tenant_id`; `version=1`, `is_active=true` via server_default; `created_at=clock_timestamp()` |
| **Succesrespons** | HTTP 201 met `ToolResponse` inclusief auto-gegenereerd `id` |
| **Foutrespons** | 401/403 bij ontbrekende auth; 422 bij validatiefout |
| **Uitzonderingen** | `id` is altijd auto-increment — nooit hardcoded |

### Flow 2: Soft-delete

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Tool bestaat en behoort tot de tenant |
| **Actie** | `DELETE /api/v1/tools/{id}` |
| **Systeemverwerking** | Zet `deleted_at = datetime.now(timezone.utc)`; voert geen `DELETE` SQL uit |
| **Succesrespons** | HTTP 200 `{"detail": "Tool deleted"}` |
| **Foutrespons** | 404 als tool niet bestaat of al soft-deleted |
| **Uitzonderingen** | Soft-deleted tools verschijnen niet in `GET /api/v1/tools/` |
