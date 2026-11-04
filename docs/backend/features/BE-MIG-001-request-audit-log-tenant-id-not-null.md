# BE-MIG-001: request_audit_logs.tenant_id NOT NULL

**Sprint:** Startup Pipeline Fix Dag 1  
**Datum:** 2026-06-05  
**Status:** APPROVED  

## Samenvatting

Alembic migratie die `request_audit_logs.tenant_id` van nullable naar NOT NULL wijzigt, conform ADR-005.

## Context

- **Probleem (B-001c):** `RequestAuditLog.tenant_id` was `nullable=True`. ADR-005 mandateert expliciet `tenant_id NOT NULL` + RLS.
- **Impact:** Compliance gap; audit logs zonder tenant context zijn niet te filteren per tenant.

## Wijzigingen

### Alembic migratie: `src/alembic/versions/20260605_request_audit_log_tenant_id_not_null.py`

- **Upgrade:**
  1. `UPDATE request_audit_logs SET tenant_id = '0' WHERE tenant_id IS NULL`
  2. `ALTER TABLE request_audit_logs ALTER COLUMN tenant_id SET NOT NULL`
- **Downgrade:**
  1. `ALTER TABLE request_audit_logs ALTER COLUMN tenant_id DROP NOT NULL`

### Code: `src/core/middleware/audit_middleware.py`

- `_extract_user_info()`: retourneert nu altijd een string voor `tenant_id` (fallback `"0"`)

## Testdekking

- Migratie up+down getest op PostgreSQL testdatabase (poort 5455)
- Roundtrip: `upgrade head` → `downgrade 3ee55ea8e623` → `upgrade head` slaagt

## Rollback

```bash
alembic -c src/alembic.ini downgrade 3ee55ea8e623
```

## Acceptatiecriteria

- [x] `request_audit_logs.tenant_id` is NOT NULL
- [x] Bestaande NULL-rows zijn gemigreerd naar `'0'`
- [x] Downgrade werkt correct

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
