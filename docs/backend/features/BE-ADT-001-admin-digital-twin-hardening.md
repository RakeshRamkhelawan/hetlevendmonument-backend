# BE-ADT-001: Admin Digital Twin Hardening

**Sprint:** SP-ADT-001 Dag 1
**Datum:** 2026-06-15
**Status:** APPROVED

## Samenvatting

Twee bevindingen uit SP-DSM-DAG6 Laag A review gefixed in `admin_digital_twin.py`:
1. SQL f-string interpolatie vervangen door SQLAlchemy bind-param (KRITIEK)
2. Rate-limit decorator toegevoegd aan GET /stats (MEDIUM)

## Context

- **KRITIEK (BE-SEC-019):** `text(f"SET LOCAL app.current_tenant = '{int(tenant_id)}'")` gebruikte f-string interpolatie in een raw SQL statement. De `int()`-cast maakte directe injectie onmogelijk, maar het patroon zelf (f-string in `text()`) moet weg conform CLAUDE.md en security.md: "Use parameterized queries — never concatenate user input into SQL."
- **MEDIUM (BE-EP-033):** GET `/admin/digital-twin/stats` miste `@consent_read_limit` decorator. Alle GET-endpoints vereisen dit per backend-patterns.md regel 4 (consent_read_limit 60/min).

## Gewijzigde bestanden

### `src/core/api/admin_digital_twin.py`

**Fix BE-SEC-019 — bind-param:**
```python
# Was (fout):
await db.execute(text(f"SET LOCAL app.current_tenant = '{int(tenant_id)}'"))

# Nu (correct):
await db.execute(
    text("SET LOCAL app.current_tenant = :tid"),
    {"tid": str(int(tenant_id))},
)
```

**Fix BE-EP-033 — rate-limit:**
```python
# Import toegevoegd:
from src.core.governance.rate_limiter import consent_read_limit

# Decorator-stack (voor @router.get):
@consent_read_limit
@router.get("/stats")
async def get_digital_twin_stats(...):
```

### `tests/unit/api/test_admin_digital_twin.py`

- `test_rls_uses_bind_param` (hernoemd van `test_rls_uses_int_tenant_id`): assertions bijgewerkt naar bind-param patroon — controleert `:tid` in statement string en `params["tid"] == "12"` in params dict.
- `_track_execute` in `test_rls_set_local_called_before_stats`: signature bijgewerkt naar `*args: object` om 2-argument `db.execute(stmt, params)` aanroep te ondersteunen.

## Backend Inventory

| ID | Type | Artefact | Sprint |
|----|------|---------|--------|
| BE-SEC-019 | Bugfix | SQL bind-param: text(f"...") → text(":tid") + params dict | SP-ADT-001 |
| BE-EP-033 | Endpoint-fix | GET /admin/digital-twin/stats + @consent_read_limit | SP-ADT-001 |
| BE-ADT-001 | Sprint-doc | admin_digital_twin.py hardening | SP-ADT-001 |

## Testdekking

```
tests/unit/api/test_admin_digital_twin.py       -- 5 pass (happy + RLS behavioral)
tests/architecture/test_dsm_dag6_preexisting_findings.py -- 2 pass (waren RED, nu GREEN)
Totaal: 7/7 PASS
```

## API-flow: GET /admin/digital-twin/stats

1. `@consent_read_limit` — rate limit check (60/min)
2. `@router.get("/stats")` — FastAPI route handler
3. JWT tenant_id wordt gelezen via `_user_tenant(current_user)`
4. system_admin override verwerkt indien aanwezig
5. `db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": str(int(tenant_id))})` — RLS scope via bind-param
6. `get_twin_stats(db=db, tenant_id=tenant_id)` — stats ophalen
7. `{"success": True, "data": stats}` — response

## Trainingssamenvatting

- Actor: admin-gebruiker (tenant-scoped) of system_admin (cross-tenant)
- Voorwaarde: geldige JWT met tenant_id en admin-rol; rate limit niet overschreden
- Actie: GET /admin/digital-twin/stats
- Systeemverwerking: RLS-scope via bind-param; stats ophalen via get_twin_stats
- Succesrespons: 200 `{"success": true, "data": {...}}` met aggregated twin stats
- Foutrespons: 429 bij rate-limit overschrijding; 403 bij onvoldoende rechten
- Uitzonderingen: system_admin mag override_tenant_id meegeven voor cross-tenant queries

## Acceptatiecriteria

- [x] `test_admin_digital_twin_no_text_fstring` GROEN
- [x] `test_admin_digital_twin_stats_has_rate_limit` GROEN
- [x] `test_rls_uses_bind_param` GROEN (bind-param assertions)
- [x] Geen f-string in text() aanroepen in admin_digital_twin.py
- [x] `@consent_read_limit` aanwezig voor `@router.get("/stats")`
