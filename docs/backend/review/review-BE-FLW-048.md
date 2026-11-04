# Review: BE-FLW-048 — Workflow step execution via Dramatiq (tenant cleanup)

| Veld | Waarde |
| --- | --- |
| Spec | `docs/backend/features/BE-UTL-048-workflow-tasks-tenant-cleanup.md` (gedeelde spec) |
| Uitkomst | **APPROVED** |
| Datum | 2026-07-31 (doc-gate gesloten; feature zelf gereviewd 2026-07-28) |

BE-FLW-048 is de flow-ID van feature BE-UTL-048 (ADR-036 Fase A dag 1, AUDIT-003) en
heeft geen eigen spec. De volledige review staat in
[`review-BE-UTL-048.md`](review-BE-UTL-048.md).

Dit bestand bestaat omdat `scripts/validate_feature_docs.py` de review-check uitvoert op
het alfabetisch eerste ID per gedeelde spec: `BE-FLW-048` sorteert voor `BE-UTL-048`,
waardoor de flow-ID de check kreeg en de doc-gate rood stond terwijl de feature wel
gereviewd was.

Flow zoals gereviewd:

```text
Dramatiq actor ontvangt workflow-step
  -> set_tenant_id(tenant_id)
  -> try: agent instantieren + step uitvoeren
  -> finally: set_tenant_id(None)   <-- het gat dat AUDIT-003 dichtte
```

Kern van de fix: het `try`-blok begint nu direct na `set_tenant_id()`, zodat een
exception tijdens agent-instantiatie de ContextVar niet meer laat staan op een
hergebruikte workerthread.
