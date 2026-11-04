# BE-SVC-058: Governance router re-export cleanup (ADR-033 S3)

## Sprint
AUDIT-DB-13 S3

## Datum
2026-07-01

## Beschrijving
Verwijderd uit `src/core/api/v1/governance/router.py`:
- `from src.core.api.dependencies import get_db  # noqa: F401 -- re-export for test overrides`
- `"get_db"` uit `__all__` (voorkomt pyright reportUnsupportedDunderAll error)
- Docstring bijgewerkt: verwijzing naar `get_db` vervangen door `get_current_user`

Governance composite router re-exporteerde get_db als dode re-export. Na verwijdering
was get_db nog aanwezig in __all__ wat een pyright error veroorzaakte -- beide
tegelijk gefixed.

## Gewijzigde bestanden
- `src/core/api/v1/governance/router.py` — get_db re-export + __all__ entry + docstring gefixed
- `tests/architecture/test_governance_router_no_direct_db.py` — nieuwe architecture test (GREEN)

## Verificatie
- `detect_db_imports.py`: 0 offenders voor governance/router.py
- Architecture test: GROEN
- pyright: 0 errors (reportUnsupportedDunderAll opgelost)
- DSM ceiling: 0 violations

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/governance/router.py` bevat geen `get_db` re-export meer en geen `get_db` in `__all__`.
- Actie (request): Draai `python scripts/detect_db_imports.py`, `tests/architecture/test_governance_router_no_direct_db.py` en `python -m pyright`.
- Systeemverwerking: De composite router includeert `monitoring_router` en `quality_router`; overgebleven re-exports zijn `get_current_user`, `get_current_tenant_id` en `_require_governance_read`.
- Succesrespons: 0 offenders voor governance/router.py; architecture test GROEN; geen `reportUnsupportedDunderAll` pyright error.
- Foutrespons: `detect_db_imports.py` toont het bestand als offender; pyright rapporteert een error als `__all__` een niet-geimporteerd symbool bevat.
- Uitzonderingen: De docstring is bijgewerkt zodat deze verwijst naar `get_current_user` in plaats van `get_db`.
