# BE-SVC-049: Sync Router DB-cleanup (ADR-033)

## Status
APPROVED

## Sprint
AUDIT-SINGLE-TENANT-DB01 S2 (AUDIT-DB-07)

## Samenvatting
De `sync/router.py` importeerde `AsyncSession` en `get_db` voor stub-handlers die de DB nooit daadwerkelijk gebruikten. De ongebruikte parameters zijn verwijderd. De `get_db` re-export blijft in `sync/dependencies.py` voor testoverrides.

## Scope
- `src/core/api/v1/sync/router.py` -- `AsyncSession` import + ongebruikte `db` parameters verwijderd
- `tests/architecture/test_sync_router_no_direct_db.py` -- nieuwe architecture test

## Motivatie
`get_workflow_snapshot` en `save_workflow_snapshot` hadden `db: AsyncSession = Depends(get_db)` terwijl alle DB-code uitgecommentarieerd was (TODO stubs). Het verwijderen van ongebruikte dependencies verbetert de leesbaarheid en ADR-033 compliance.

## Opmerking
Sync snapshot handlers hebben geen `get_current_user` -- pre-existing security gap (unauthenticated stubs). Fix is gepland voor het moment dat de stubs geimplementeerd worden.

## Tests
- `tests/architecture/test_sync_router_no_direct_db.py` -- GROEN
- `tests/unit/test_sp_e02_sync_router.py` -- 18 passed

## Trainingssamenvatting

- Actor: Hocuspocus sync-server (op dit moment ongeauthenticeerd).
- Voorwaarde: `src/core/api/v1/sync/router.py` is gemount zonder `AsyncSession` of `get_db` imports.
- Actie (request): Verstuur `GET /workflows/{workflow_id}/snapshot`.
- Systeemverwerking: De handler ontvangt `workflow_id` en `request`; de stub-implementatie retourneert direct een lege binaire response zonder database-aanroep.
- Succesrespons: HTTP 200 met lege body (`b""`) en `Content-Type: application/octet-stream`.
- Foutrespons: HTTP 500 `Failed to load snapshot: <exception>` bij onverwachte fout.
- Uitzonderingen: De databasecode in de handler is nog steeds uitgecommentarieerd (TODO-stub); `get_db` is verwijderd omdat deze niet gebruikt werd.
