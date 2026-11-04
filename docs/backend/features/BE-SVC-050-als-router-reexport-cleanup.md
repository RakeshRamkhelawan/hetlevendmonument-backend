# BE-SVC-050: ALS Router Re-export Cleanup (ADR-033)

## Status
APPROVED

## Sprint
AUDIT-SINGLE-TENANT-DB01 S2 (AUDIT-DB-08)

## Samenvatting
De `als/router.py` re-exporteerde `get_db` met `# noqa: F401` voor testoverrides. Dit patroon triggert `detect_db_imports.py` en `dsm_api_violation_finder.py`. De re-export is verwijderd; tests kunnen `src.core.api.dependencies.get_db` direct patchen.

## Scope
- `src/core/api/v1/als/router.py` -- `get_db` re-export verwijderd
- `tests/architecture/test_als_router_no_direct_db.py` -- nieuwe architecture test

## Motivatie
ADR-033 composite routers mogen geen `get_db` re-exporteren. Tests moeten de canonieke bron (`src.core.api.dependencies.get_db`) patchen in plaats van de router als doorgeefluik te gebruiken.

## Tests
- `tests/architecture/test_als_router_no_direct_db.py` -- GROEN
- `tests/unit/test_als_router.py` -- passed

## Trainingssamenvatting

- Actor: CI-pipeline of ontwikkelaar die ADR-033 naleving controleert.
- Voorwaarde: `src/core/api/v1/als/router.py` is een composite router zonder `get_db` re-export.
- Actie (request): Draai `python scripts/detect_db_imports.py` en `tests/architecture/test_als_router_no_direct_db.py`.
- Systeemverwerking: De composite router includeert alleen de sub-routers (`als_tasks_router`, `als_health_router`, `als_agents_router`); tests die een dependency willen overriden patchen `src.core.api.dependencies.get_db` direct.
- Succesrespons: `detect_db_imports.py` rapporteert 0 offenders voor `als/router.py`; architecture test is GROEN.
- Foutrespons: Indien de re-export terugkeert, verschijnt het bestand in de `offenders`-lijst van `detect_db_imports.py`.
- Uitzonderingen: Geen runtime endpoint-wijziging; alleen testoverride-locatie aangepast.
