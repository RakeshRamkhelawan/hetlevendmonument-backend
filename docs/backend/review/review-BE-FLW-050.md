# Review: BE-FLW-050 — Periodieke purge van verlopen soft-deleted memory_items

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-GDPR-003-memory-item-purge.md` (gedeelde spec) |
| Uitkomst | **APPROVED** |
| Datum | 2026-07-31 (doc-gate gesloten; feature zelf gereviewd 2026-07-29) |

BE-FLW-050 is een flow-ID van feature BE-GDPR-003 (ADR-036 Fase A dag 3) en heeft geen
eigen spec. De volledige review staat in
[`review-BE-GDPR-003.md`](review-BE-GDPR-003.md).

Dit bestand bestaat omdat `scripts/validate_feature_docs.py` de review-check uitvoert op
het alfabetisch eerste ID per spec: `BE-FLW-050` sorteert voor `BE-GDPR-003`, waardoor de
flow-ID de check kreeg en de doc-gate rood stond terwijl de feature wel gereviewd was.
Gevonden tijdens OP-11 dag 2 bij het valideren van de eigen docs.

Flow zoals gereviewd:

```text
Dramatiq scheduler (dagelijks 03:40 UTC)
  -> purge_soft_deleted_memory_items (per tenant)
  -> memory_purge_service: verlopen soft-deleted rijen (30-dagen grace)
  -> fysieke verwijdering van rij EN embedding
  -> auditregel memory_purge_executed in de ADR-019 hash chain
```

Integratiebewijs op echte PostgreSQL + pgvector (2026-07-31):
`tests/integration/test_memory_purge_tenant_isolation.py` 3/3 groen -- rij en embedding
fysiek weg, purge tenant-scoped, per-tenant orchestratie.
