# BE-SVC-056: FocusBuilder router re-export cleanup (ADR-033 S3)

## Sprint
AUDIT-DB-11 S3

## Datum
2026-07-01

## Beschrijving
Verwijderd: `from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for test overrides`
uit `src/core/api/v1/focus_builder/router.py`.

Zelfde patroon als BE-SVC-055: composite router re-exporteerde get_db als dode re-export.
Geen tests patchen `focus_builder.router.get_db` -- alle sub-router tests gebruiken
hun eigen dependency factories.

## Gewijzigde bestanden
- `src/core/api/v1/focus_builder/router.py` — get_db re-export verwijderd (1 regel)
- `tests/architecture/test_focus_builder_router_no_direct_db.py` — nieuwe architecture test (GREEN)

## Verificatie
- `detect_db_imports.py`: 0 offenders voor focus_builder/router.py
- Architecture test: GROEN
- DSM ceiling: 0 violations
- pyright: 0 nieuwe errors

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/focus_builder/router.py` bevat geen `get_db` re-export meer.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/architecture/test_focus_builder_router_no_direct_db.py`.
- Systeemverwerking: De composite router includeert zeven sub-routers; geen sub-router tests patchten `focus_builder.router.get_db`.
- Succesrespons: 0 offenders voor focus_builder/router.py; architecture test GROEN; pyright 0 errors.
- Foutrespons: `detect_db_imports.py` toont het bestand als offender als de re-export terugkeert.
- Uitzonderingen: Geen runtime endpoint-wijziging.
