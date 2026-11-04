# BE-MDL-005 — ToolVersion ORM Model

**Sprint:** SP-B02 Dag 1  
**Datum:** 2026-05-28  
**Status:** APPROVED

---

## Overzicht

SQLAlchemy ORM model voor de `tool_versions` tabel. Slaat immutable snapshots op van een `Tool` bij elke PUT-update, zodat de volledige versiegeschiedenis bewaard blijft.

**Bestand:** `src/core/tool_broker/models.py`

---

## Model definitie

| Kolom | Type | Constraints | Default |
|-------|------|-------------|---------|
| `id` | Integer | PK, autoincrement | — |
| `tool_id` | Integer | FK → tools.id CASCADE, NOT NULL, index | — |
| `tenant_id` | Integer | NOT NULL, index | — |
| `version` | Integer | NOT NULL | — |
| `snapshot` | JSONB | NOT NULL | — |
| `created_at` | DateTime(tz) | NOT NULL | `clock_timestamp()` |

**ADR-naleving:**
- ADR-005: `tenant_id NOT NULL`
- FK met `ondelete="CASCADE"` — versiehistorie verdwijnt automatisch bij hard-delete van de tool
- `tenant_id` als eigenstandige kolom voor RLS en directe tenant-filter queries (geen join nodig)
- §11.5 CLAUDE.md: `created_at` gebruikt `clock_timestamp()`

---

## Snapshot structuur

De `snapshot` JSONB bevat de volledige staat van de `Tool` vóór de update:

```json
{
  "id": 42,
  "name": "my_tool",
  "description": "...",
  "tool_type": "api",
  "status": "active",
  "code": null,
  "endpoint_url": "https://...",
  "parameters": [...],
  "metadata": {...},
  "tags": [...],
  "timeout_seconds": 30,
  "retry_policy": {...},
  "version": 3
}
```

De snapshot wordt gemaakt **vóór** het verhogen van `version` in de Tool-rij.

---

## Trainingssamenvatting

### Flow 1: Snapshot opslaan bij update

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Tool bestaat en behoort tot de tenant |
| **Actie** | `PUT /api/v1/tools/{id}` |
| **Systeemverwerking** | Router legt `old_version = tool.version` vast; bouwt snapshot-dict; maakt `ToolVersion`-rij aan met `version=old_version`; verhoogt `tool.version` naar `old_version + 1`; commit slaat beide in één transactie op |
| **Succesrespons** | HTTP 200 met bijgewerkte `ToolResponse` (`version` verhoogd) |
| **Foutrespons** | 404 als tool niet gevonden; 422 bij validatiefout |
| **Uitzonderingen** | Snapshot is altijd de staat vóór de update; bij rollback wordt geen versieregel opgeslagen |

### Flow 2: Versiegeschiedenis opvragen

| Fase | Detail |
|------|--------|
| **Actor** | Geverifieerde tenant-gebruiker |
| **Voorwaarde** | Tool bestaat in tenant |
| **Actie** | `GET /api/v1/tools/{id}/versions?skip=0&limit=50` |
| **Systeemverwerking** | Eigenaarschap geverifieerd via `Tool.tenant_id`; query filtert op `ToolVersion.tool_id + ToolVersion.tenant_id`; count-query geeft echte totaaltelling |
| **Succesrespons** | `{"data": [...], "total": N}` gesorteerd op versie aflopend |
| **Foutrespons** | 404 als tool niet bestaat of tot andere tenant behoort |
| **Uitzonderingen** | `total` reflecteert het werkelijke aantal versie-rijen, niet de paginagrootte |
