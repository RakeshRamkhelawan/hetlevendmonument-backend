# BE-SVC-059: Privacy router re-export cleanup (ADR-033 S3)

## Sprint
AUDIT-DB-14 S3

## Datum
2026-07-01

## Beschrijving
Verwijderd: `from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for test overrides`
uit `src/core/api/v1/privacy/router.py`.

Privacy composite router re-exporteerde get_db als dode re-export. Sub-routers
(dsar, consent, ai_transparency, human_review) beheren hun eigen dependency injection.

## Gewijzigde bestanden
- `src/core/api/v1/privacy/router.py` — get_db re-export verwijderd (1 regel)
- `tests/architecture/test_privacy_router_no_direct_db.py` — nieuwe architecture test (GREEN)

## Verificatie
- `detect_db_imports.py`: 0 offenders voor privacy/router.py
- Architecture test: GROEN
- DSM ceiling: 0 violations
- pyright: 0 nieuwe errors

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/privacy/router.py` bevat geen `get_db` re-export meer.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/architecture/test_privacy_router_no_direct_db.py`.
- Systeemverwerking: De composite router includeert `dsar_router`, `consent_router`, `ai_transparency_router` en `human_review_router`; elke sub-router beheert eigen dependencies.
- Succesrespons: 0 offenders voor privacy/router.py; architecture test GROEN.
- Foutrespons: `detect_db_imports.py` toont het bestand als offender als de re-export terugkeert.
- Uitzonderingen: Geen runtime endpoint-wijziging.
