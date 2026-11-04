# Review BE-RTR-011 — Workflow Domain Migration naar v1/workflow/

## Uitkomst: APPROVED WITH MINOR GAPS

Datum: 2026-06-03
Sprint: SP-API-003 Dag 1
Reviewer: Automated spec review

## Bevindingen

### CRITICAL
_Geen._

### HIGH
_Geen._

### MEDIUM

**M-001**: `workflow_crud_router.py` gebruikt zowel `from src.core.api.v1.workflow.dependencies import ...`
als directe imports van `src.core.auth.scope_validator` en `src.core.middleware.tenant_context`.
Dubbele importpaden; enkel via dependencies.py is schoner.
Status: **ACCEPTED** — functioneel correct; cleanup in dag 2+ mogelijk.

**M-002**: `workflow_execution_router.py` is ~200 regels maar bevat zowel CRUD-logica voor de
GracefulCanceller als de scoped cancel. Kan in dag 2 verder worden gesplitst.
Status: **ACCEPTED** — binnen grens, split is optioneel.

### LOW

**L-001**: Sub-router wrappers (suggestions/builder/versioning etc.) delegeren enkel naar
legacy flat bestanden. Dit is correct Strangler Fig patroon maar importketen is
`registry -> domain_router -> composite -> sub_router -> flat file -> echte logica`.
Status: **ACCEPTED** — bewust ontwerp; flat files worden in week 8 hard verwijderd.

**L-002**: `workflow_suggestions_router.py` bevat enkel een re-export; heeft geen eigen
`router`-object. De composite importeert `router` uit de flat file via de wrapper.
Werkt correct maar is inconsistent met de CRUD/execution sub-routers.
Status: **ACCEPTED** — cosmetic; functioneel correct.

## Samenvatting

Migratie is structureel correct. Alle 128 tests passeren. ADR-033 regels gerespecteerd:
- `registries/workflows.py` <= 80 regels (66r)
- Lazy imports in registry
- `domain_router` exporteert correct
- Flat bestanden hebben `# orphan:exempt`
- Equivalentietest toegevoegd en GROEN
