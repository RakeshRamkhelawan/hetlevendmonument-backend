# BE-SVC-057: Gatekeeper router re-export cleanup (ADR-033 S3)

## Sprint
AUDIT-DB-12 S3

## Datum
2026-07-01

## Beschrijving
Verwijderd: `from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for test overrides`
uit `src/core/api/v1/gatekeeper/router.py`.

Composite router re-exporteerde get_db als dode re-export. Gatekeeper sub-routers
(decisions + hitl) beheren hun eigen dependency injection via hun eigen dependencies.py.

## Gewijzigde bestanden
- `src/core/api/v1/gatekeeper/router.py` — get_db re-export verwijderd (1 regel)
- `tests/architecture/test_gatekeeper_router_no_direct_db.py` — nieuwe architecture test (GREEN)

## Verificatie
- `detect_db_imports.py`: 0 offenders voor gatekeeper/router.py
- Architecture test: GROEN
- DSM ceiling: 0 violations
- pyright: 0 nieuwe errors

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/gatekeeper/router.py` bevat geen `get_db` re-export meer.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/architecture/test_gatekeeper_router_no_direct_db.py`.
- Systeemverwerking: De composite router includeert `decisions_router` en `hitl_router`; beide sub-routers hebben hun eigen `dependencies.py`.
- Succesrespons: 0 offenders voor gatekeeper/router.py; architecture test GROEN.
- Foutrespons: `detect_db_imports.py` toont het bestand als offender als de re-export terugkeert.
- Uitzonderingen: Geen runtime endpoint-wijziging.
