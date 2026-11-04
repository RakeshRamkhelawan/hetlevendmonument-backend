# BE-TI-FIX-001: SP-AUDIT-FIX-001 Dag 1 -- Tenant-filter fixes (RCG-2)

**Sprint:** SP-AUDIT-FIX-001 Dag 1
**Datum:** 2026-06-26
**Commit:** 1381c88f

## Scope

Vier tenant-isolatiegaten gedicht gevonden tijdens de bottom-to-top audit (2026-06-26).
Alle gefixte methoden voerden DB-queries uit zonder `tenant_id` in de WHERE-clause,
waardoor data van andere tenants bereikbaar was.

## Wijzigingen

| Bevinding | Bestand | Fix |
|-----------|---------|-----|
| AUDIT-TI-001 | `src/core/agents/knowledge_agent/knowledge_service.py` | `get_entry()` filtert nu op `tenant_id` |
| AUDIT-TI-002 | `src/core/als/collective/collective_memory.py` | `_merge_insights()` filtert nu op `tenant_id` |
| AUDIT-TI-005 | `src/core/als/collective/collective_memory.py` | `_increment_access_count()` filtert nu op `tenant_id` |
| AUDIT-TI-004 | `src/core/api/v1/analytics_ingest/events_router.py` | Health-check vervangen door `SELECT 1` (geen cross-tenant aggregatie) |
| AUDIT-GDPR-002 | `src/core/governance/dsar_service.py` | `PointTransaction` query gefilterd op `tenant_id` |

## Patroon

```python
# VOOR (FOUT -- geen tenant filter)
result = await session.execute(select(Model).where(Model.id == record_id))

# NA (GOED -- ADR-005 compliant)
result = await session.execute(
    select(Model).where(Model.id == record_id, Model.tenant_id == self.tenant_id)
)
```

## Tests

`tests/unit/gdpr/test_tenant_isolation_dag1.py` -- 7/7 GROEN

- `test_get_entry_accepts_tenant_id_param`
- `test_get_entry_query_includes_tenant_filter`
- `test_get_entry_with_wrong_tenant_returns_none`
- `test_increment_access_count_query_includes_tenant_filter`
- `test_merge_insights_query_includes_tenant_filter`
- `test_health_check_does_not_aggregate_all_tenants`
- `test_point_transaction_query_contains_tenant_filter`

## Status

APPROVED -- pyright 0 errors, 7 tests GROEN, geen regressies.
