# Review: BE-MDL-002 Document ORM Model Extension

**Reviewer:** general-purpose subagent (quality/security)
**Datum:** 2026-05-28
**Status:** APPROVED WITH MINOR GAPS

---

## Bevindingen

### CRITICAL: 0

### HIGH: 0

### MEDIUM: 1

- `is_deleted` boolean blijft bestaan naast `deleted_at`. Dit is bewust voor backward compat tijdens de migratieperiode, maar moet verwijderd worden in een toekomstige sprint.

### LOW: 1

- `created_at` gebruikt `clock_timestamp()` in PostgreSQL maar wordt in SQLite tests expliciet in Python gezet. Dit verdient een code comment.

---

## Samenvatting

Model voldoet aan ADR-005 (tenant_id NOT NULL, RLS), ADR-010 (geen module-level state), en CLAUDE.md patronen (`clock_timestamp()`, soft delete). Migratie heeft werkende downgrade en data backfill.

**Verdict: APPROVED WITH MINOR GAPS**
