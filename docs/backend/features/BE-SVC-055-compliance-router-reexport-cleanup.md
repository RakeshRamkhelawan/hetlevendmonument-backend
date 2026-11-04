# BE-SVC-055: Compliance router re-export cleanup (ADR-033 S3)

## Sprint
AUDIT-DB-10 S3

## Datum
2026-07-01

## Beschrijving
Verwijderd: `from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for test overrides`
uit `src/core/api/v1/compliance/router.py`.

De composite router re-exporteerde get_db zodat tests de dependency konden overriden via
`app.dependency_overrides[router.get_db]`. Na ADR-033 patchen tests direct op
`src.core.api.dependencies.get_db` of de specifieke sub-router dependency. De re-export
was dode code en triggerde de `detect_db_imports.py` scanner.

## Gewijzigde bestanden
- `src/core/api/v1/compliance/router.py` — get_db re-export verwijderd (1 regel)
- `tests/architecture/test_compliance_router_no_direct_db.py` — nieuwe architecture test (GREEN)

## Verificatie
- `detect_db_imports.py`: 0 offenders voor compliance/router.py
- Architecture test: GROEN
- DSM ceiling: 0 violations
- pyright: 0 nieuwe errors

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/compliance/router.py` bevat geen `get_db` re-export meer.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/architecture/test_compliance_router_no_direct_db.py`.
- Systeemverwerking: De composite router includeert acht sub-routers; elke sub-router beheert zijn eigen dependency-injectie.
- Succesrespons: 0 offenders voor compliance/router.py; architecture test GROEN.
- Foutrespons: `detect_db_imports.py` toont het bestand als offender als de re-export terugkeert.
- Uitzonderingen: Geen runtime endpoint-wijziging.
