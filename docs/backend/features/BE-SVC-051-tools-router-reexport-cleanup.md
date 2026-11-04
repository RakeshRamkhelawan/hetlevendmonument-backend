# BE-SVC-051: Tools Router Re-export Cleanup (ADR-033)

## Status
APPROVED

## Sprint
AUDIT-SINGLE-TENANT-DB01 S2 (AUDIT-DB-09)

## Samenvatting
De `tools/router.py` re-exporteerde `get_db`. Deze re-export is verwijderd. De bestaande test die `src.core.api.v1.tools.router.get_db` patchte is bijgewerkt naar de correcte target `src.core.api.v1.tools.dependencies.get_db` (waar `crud_router` daadwerkelijk van importeert).

## Scope
- `src/core/api/v1/tools/router.py` -- `get_db` re-export verwijderd
- `tests/unit/test_sp_b02_tools_api.py:210` -- patch target gecorrigeerd

## Motivatie
De vorige patch target (`tools.router.get_db`) werkte al niet correct omdat `crud_router.py` importeert van `tools.dependencies`, niet van `tools.router`. De correctie verbetert zowel test-kwaliteit als ADR-033 compliance.

## Tests
- `tests/architecture/test_tools_router_no_direct_db.py` -- GROEN
- `tests/unit/test_sp_b02_tools_api.py` -- 41 passed

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/tools/router.py` is een composite router zonder `get_db` re-export; `crud_router` importeert `get_db` van `src.core.api.v1.tools.dependencies`.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/unit/test_sp_b02_tools_api.py`.
- Systeemverwerking: De scanner vindt geen directe database-import in `tools/router.py`; tests patchen de canonieke dependency `src.core.api.v1.tools.dependencies.get_db`.
- Succesrespons: 0 offenders voor tools/router.py; 41 tests passed.
- Foutrespons: `detect_db_imports.py` meldt een offender als de re-export terugkeert; tests falen als het patch-target onjuist blijft.
- Uitzonderingen: Geen runtime endpoint-wijziging.
