# BE-MIG-010 -- GDPR Base Consolidatie + ORM Drift Fix (SP-DB-01)

**ID:** BE-MIG-010
**Sprint:** SP-WE-18 + SP-DB-01 (1 dag sprint)
**Datum:** 2026-06-14
**ADR:** ADR-005 (tenant_id NOT NULL + RLS)

## Samenvatting

`src/core/database/gdpr_deletion.py` definieerde een EIGEN `Base = declarative_base()`
(regel 37). Dit maakte de `DeletionAudit` tabel ONZICHTBAAR voor Alembic: de hoofd-Base
in `src/core/database/database.py` wordt gebruikt door `alembic/env.py`, maar de
aparte Base werd er nooit mee gesynchroniseerd.

### Rootcause

De tabel bestond wel in de DB (aangemaakt door een eerdere handmatige migratie), maar
was onzichtbaar voor Alembic autogenerate. Eventuele schemawijzigingen zouden dus
niet worden gedetecteerd.

### Wijzigingen

| Bestand | Wijziging |
|---------|-----------|
| `src/core/database/gdpr_deletion.py` | `Base = declarative_base()` -> `from src.core.database.database import Base` |
| `src/core/database/gdpr_deletion.py` | `DeletionAudit.tenant_id`: FK + nullable=True -> NOT NULL + server_default="0" (ADR-005) |
| `src/core/database/gdpr_deletion.py` | `hard_delete()`: audit log na delete, wrapped in `best_effort` (CLAUDE.md Pattern 3) |
| `src/core/database/gdpr_deletion.py` | `generate_deletion_report()`: `limit`/`offset` params + `min(limit, 10000)` cap (CLAUDE.md Pattern 5) |
| `src/core/database/gdpr_deletion.py` | Logger f-strings -> %s format (CLAUDE.md Pattern 10) |
| `src/core/database/model_registry.py` | `("core.gdpr", "src.core.database.gdpr_deletion", ["DeletionAudit"])` toegevoegd |
| `tests/unit/test_sp_db01_gdpr_base.py` | 2 AST-tests: geen eigen declarative_base(), importeert uit database module |
| `Makefile` | `check-migrations` target toegevoegd |

### Alembic drift verificatie

```text
alembic check -> "No new upgrade operations detected."
alembic heads -> "20260605a (head)" (precies 1)
```

Geen nieuwe migratie nodig: tabel bestond al en is na de Base-fix correct
zichtbaar voor autogenerate.

## Tests

```text
tests/unit/test_sp_db01_gdpr_base.py::test_gdpr_deletion_uses_shared_base PASSED
tests/unit/test_sp_db01_gdpr_base.py::test_gdpr_deletion_imports_from_database_module PASSED
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
