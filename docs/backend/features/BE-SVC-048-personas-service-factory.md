# BE-SVC-048: Personas Service Factory (ADR-033)

## Status
APPROVED

## Sprint
AUDIT-SINGLE-TENANT-DB01 S2 (AUDIT-DB-06)

## Samenvatting
De `personas/router.py` importeerde `get_db` en `AsyncSession` direct -- schending van ADR-033. Een `get_persona_service` factory is toegevoegd aan `personas/dependencies.py`. Alle route handlers gebruiken nu `service: PersonaService = Depends(get_persona_service)` in plaats van inline `PersonaService(db)`.

## Scope
- `src/core/api/v1/personas/router.py` -- `get_db` en `AsyncSession` imports verwijderd
- `src/core/api/v1/personas/dependencies.py` -- `get_persona_service` factory toegevoegd
- `tests/architecture/test_personas_router_no_direct_db.py` -- nieuwe architecture test

## Motivatie
ADR-033 vereist dat `router.py` bestanden GEEN directe imports hebben van `get_db`, `AsyncSession`, `select`, `func`, `update` of `delete`. Deze moeten in `dependencies.py` als injectable factories staan.

## Implementatie

```python
# personas/dependencies.py -- nieuw
async def get_persona_service(db: AsyncSession = Depends(get_db)) -> PersonaService:
    return PersonaService(db)
```

Alle 8 route handlers (list, active GET/POST, get, create, update, delete, seed-defaults) zijn bijgewerkt naar het `Depends(get_persona_service)` patroon.

## Tenant isolatie
Ongewijzigd: elke service-aanroep passeert `current_user.tenant_id` (JWT-bron, ADR-003).

## Tests
- `tests/architecture/test_personas_router_no_direct_db.py` -- GROEN
- `tests/unit/test_persona_endpoints.py` -- 51 passed

## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met geldige JWT en opgeloste tenant.
- Voorwaarde: Endpoint `GET /api/v1/personas/` is bereikbaar; `get_persona_service` factory is gedefinieerd in `src/core/api/v1/personas/dependencies.py`.
- Actie (request): Verstuur `GET /api/v1/personas/?limit=50&offset=0` met een geldige `Authorization` header.
- Systeemverwerking: FastAPI injecteert `current_user` en `service = Depends(get_persona_service)`; de factory maakt een `PersonaService(db_session=db)`. De handler roept `service.get_all_personas(current_user.tenant_id, limit=limit, offset=offset)` aan.
- Succesrespons: HTTP 200 met body `{"data": [<PersonaResponse objecten>], "limit": 50, "offset": 0}`.
- Foutrespons: HTTP 401 indien niet geauthenticeerd; HTTP 500 bij onverwachte servicefout.
- Uitzonderingen: Alle acht handlers in `personas/router.py` gebruiken nu `Depends(get_persona_service)` in plaats van inline `PersonaService(db)`; tenant-isolatie blijft via `current_user.tenant_id`.
