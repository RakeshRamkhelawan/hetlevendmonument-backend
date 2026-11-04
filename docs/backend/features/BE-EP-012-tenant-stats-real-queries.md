# BE-EP-012 — Tenant Stats Real DB Queries

**ID:** BE-EP-012
**Sprint:** SP-E06
**Datum:** 2026-05-29
**Bestand:** `src/core/api/v1/tenants/router.py` — `get_tenant_stats` endpoint
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

`GET /tenants/{tenant_id}/stats` retourneerde altijd hardcoded nulwaarden (`agent_count=0`, `storage_used_gb=0.0`, `last_activity=None`), waardoor het admin-dashboard onbetrouwbare informatie toonde (P1-12). Fix: drie echte DB-aggregatiequeries toegevoegd voor agent-aantallen, laatste audit-activiteit, en opslaggebruik. Opslagberekening is best-effort (try/except met logger.warning) omdat `file_size_bytes` nullable is en het een informatieve metriek betreft.

---

## Endpoint

| Methode | Pad | Authenticatie |
|---------|-----|---------------|
| GET | `/api/v1/tenants/{tenant_id}/stats` | JWT — eigen tenant of superuser |

---

## Response

**TenantStats (200):**
```json
{
  "user_count": 12,
  "agent_count": 5,
  "storage_used_gb": 0.0024,
  "last_activity": "2026-05-29T08:42:11+00:00"
}
```

- `user_count`: `COUNT(users.id) WHERE tenant_id = ?` (bestaande query)
- `agent_count`: `COUNT(agents.id) WHERE tenant_id = ?` (nieuw)
- `last_activity`: `MAX(audit_logs.timestamp) WHERE tenant_id = ?` (nieuw)
- `storage_used_gb`: `SUM(documents.file_size_bytes) / (1024^3) WHERE tenant_id = ?` (nieuw, best-effort)

---

## Architectuurbeslissingen

1. **Vier afzonderlijke aggregatiequeries:** Elke `COUNT`/`MAX`/`SUM` is een enkelvoudige scalar-query — geen N+1, geen JOIN. Consistent met de bestaande `user_count`-query.
2. **`AuditLog.timestamp`:** De AuditLog-tabel gebruikt `timestamp` (niet `created_at`) als tijdstempelkolom. `tenant_id` is nullable in dit model — SQL `WHERE tenant_id = ?` sluit NULL-rijen correct uit.
3. **Best-effort opslag:** `func.sum(Document.file_size_bytes)` in try/except met `logger.warning`. Motief: `file_size_bytes` is nullable en de metriek is informatief, niet kritiek.
4. **Geen tenant_id uit request body:** `tenant_id` komt uit het URL-path + permission-gate controleert autorisatie (CLAUDE.md §6).

---

## Trainingssamenvatting

### Flow: Admin raadpleegt tenant-statistieken

| Veld | Inhoud |
|------|--------|
| **Actor** | Tenant-admin of superuser die het beheer-dashboard bezoekt |
| **Voorwaarde** | Tenant bestaat; gebruiker is ingelogd met geldig JWT (eigen tenant of superuser) |
| **Actie** | `GET /api/v1/tenants/{tenant_id}/stats` |
| **Systeemverwerking** | 1. Permission check. 2. `COUNT(User.id)`. 3. `COUNT(Agent.id)`. 4. `MAX(AuditLog.timestamp)`. 5. `SUM(Document.file_size_bytes)` (best-effort). Alle queries gefilterd op `tenant_id`. |
| **Succesrespons** | HTTP 200 + `TenantStats` met echte DB-waarden |
| **Foutrespons** | HTTP 403 bij andere tenant (niet superuser). HTTP 500 bij DB-fout in user/agent/last_activity query. |
| **Uitzonderingen** | `Document`-tabel leeg of `file_size_bytes` altijd NULL → `storage_used_gb=0.0` (logging via warning). Geen tenants met agents → `agent_count=0` (correct, niet hardcoded). |

---

## Tests

- `tests/unit/test_sp_e06_small_fixes.py::TestTenantStats` (8 tests; alle 8 PASS)
