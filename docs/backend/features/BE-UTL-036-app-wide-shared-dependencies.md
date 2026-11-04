# BE-UTL-036 -- App-wide Shared Dependencies: require_admin_role + get_current_tenant_id

| Veld | Waarde |
|------|--------|
| Feature ID | BE-UTL-036 |
| Feature naam | App-wide Shared Dependencies: require_admin_role + get_current_tenant_id |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 1) |
| Reviewer | AI agent (review-BE-UTL-036.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 1 (Stap 0C) |
| Gerelateerde router / module | `src/core/api/dependencies.py`, `src/core/api/admin_digital_twin.py`, `src/core/api/admin_learning_endpoints.py`, `src/core/api/evaluation_endpoints.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Consolideer de twee meest gebruikte FastAPI-dependencies (`require_admin_role` en
`get_current_tenant_id`) in het centrale `src/core/api/dependencies.py` bestand en migreer alle
callsites die deze functies eerder importeerden vanuit domein-specifieke modules.

### In scope

- `src/core/api/dependencies.py`: voeg `require_admin_role` toe (async FastAPI dependency, checkt
  `current_user.roles` voor `"admin"` of `"system_admin"`) en `get_current_tenant_id` (thin wrapper
  om `require_tenant_id()` uit middleware)
- `src/core/api/admin_digital_twin.py`: import gewijzigd van `admin_endpoints` naar `dependencies`
- `src/core/api/admin_learning_endpoints.py`: import gewijzigd van `admin_endpoints` naar
  `dependencies`
- `src/core/api/evaluation_endpoints.py`: import gewijzigd van `search_endpoints` naar
  `dependencies`
- `tests/unit/api/test_admin_learning_endpoints.py`: import bijgewerkt van `admin_endpoints` naar
  `dependencies` (regression fix -- FastAPI `dependency_overrides` werkt op functie-object
  identiteit)

### Out of scope

- Inhoudelijke wijzigingen aan bestaande admin- of evaluatie-logica
- Nieuwe endpoints of API-paden
- Database-wijzigingen of Alembic migraties
- Wijzigingen aan `require_tenant_id()` in de middleware

---

## Build summary

### Nieuw gebouwd

Geen nieuwe bestanden.

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `dependencies.py` | `require_admin_role` + `get_current_tenant_id` toegevoegd | `src/core/api/dependencies.py` |
| `admin_digital_twin.py` | Import `admin_endpoints` -> `dependencies` | `src/core/api/admin_digital_twin.py` |
| `admin_learning_endpoints.py` | Import `admin_endpoints` -> `dependencies` | `src/core/api/admin_learning_endpoints.py` |
| `evaluation_endpoints.py` | Import `search_endpoints` -> `dependencies` | `src/core/api/evaluation_endpoints.py` |
| `test_admin_learning_endpoints.py` | Import + `dependency_overrides` bijgewerkt | `tests/unit/api/test_admin_learning_endpoints.py` |

### Verwijderd

Niets. De originele definities in `admin_endpoints` en `search_endpoints` zijn behouden als
backward-compatible re-exports totdat alle callsites zijn gemigreerd.

### Beinvloede bestaande flows

Geen functionele wijzigingen. De admin- en evaluatieflows werken identiek. De enige impact is dat
`dependency_overrides` in tests nu het object uit `dependencies` moet patchen i.p.v. het object
uit de oorspronkelijke module.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|----------------|-------------------|
| BE-UTL-036-a | `require_admin_role` | FastAPI dependency | `src/core/api/dependencies.py` | Wijziging (toegevoegd) | Admin API flows |
| BE-UTL-036-b | `get_current_tenant_id` | FastAPI dependency | `src/core/api/dependencies.py` | Wijziging (toegevoegd) | Alle tenant-scoped flows |
| BE-UTL-036-c | Import migratie (3 bestanden) | Refactor | `admin_digital_twin.py`, `admin_learning_endpoints.py`, `evaluation_endpoints.py` | Wijziging | Admin / evaluatie flows |
| BE-UTL-036-d | Test regression fix | Test | `tests/unit/api/test_admin_learning_endpoints.py` | Wijziging | Test suite |

---

## API-flows

### Flow: Admin Endpoint Authorisatie

| Veld | Waarde |
|------|--------|
| Naam | Admin Endpoint Authorisatie |
| Trigger | HTTP request naar een admin-endpoint (`/api/v1/admin/*`) |
| Voorwaarden | Geldig JWT token aanwezig; request bereikt FastAPI dependency-injectie |
| Request-pad | `Authorization: Bearer <token>` header |
| Service-stappen | 1. `get_current_user` verifieert JWT; 2. `require_admin_role(current_user)` checkt `current_user.roles`; 3. Bij `"admin"` of `"system_admin"` in roles: doorgaan; 4. Endpoint-handler aangeroepen |
| DB-operaties | Geen (roles uit JWT claims) |
| Successtatus | HTTP 200 -- endpoint-handler antwoord |
| Foutpaden | Geen geldige role: HTTP 403 Forbidden |
| Eindtoestand | Admin actie uitgevoerd of 403 geretourneerd |

### Flow: Tenant ID Ophalen via Shared Dependency

| Veld | Waarde |
|------|--------|
| Naam | Tenant ID Ophalen via Shared Dependency |
| Trigger | FastAPI dependency-injectie voor een tenant-scoped endpoint |
| Voorwaarden | `TenantMiddleware` heeft `set_tenant_id()` al aangeroepen in de request-context |
| Request-pad | Intern -- geen HTTP-specifiek pad |
| Service-stappen | 1. `get_current_tenant_id()` aangeroepen als `Depends`; 2. Delegeert naar `require_tenant_id()` uit middleware; 3. Leest `tenant_id` uit de ContextVar |
| DB-operaties | Geen |
| Successtatus | `int` tenant_id teruggegeven aan de endpoint-handler |
| Foutpaden | `tenant_id` niet in ContextVar: `RuntimeError` -- request heeft middleware omzeild |
| Eindtoestand | Endpoint-handler heeft tenant_id zonder directe middleware-import |

---

## Detaildocumentatie per artefact

### `require_admin_role`

| Veld | Waarde |
|------|--------|
| Type | FastAPI async dependency |
| Locatie | `src/core/api/dependencies.py` |
| Gerelateerde flow | Admin Endpoint Authorisatie |
| Doel | Centraliseer de admin-rolcheck zodat alle admin-endpoints dezelfde dependency gebruiken |
| Functionele beschrijving | Async FastAPI dependency. Accepteert `current_user: User = Depends(get_current_user)`. Checkt `current_user.roles` list op aanwezigheid van `"admin"` of `"system_admin"`. Bij ontbrekende role: raise `HTTPException(status_code=403)`. |
| Technische beschrijving | Gebruikt `get_current_user` als upstream dependency via `Depends`. Rolcheck is een simple `in`-expressie op de roles-lijst. Geen DB-aanroepen. |
| Zichtbaarheids- en toegangsregels | Publiek in `dependencies.py`; exporteerbaar via `__all__` |
| Request-specificatie | Geen request body; haalt data uit JWT via upstream dependency |
| Response-specificatie | `None` bij succes (dependency, geen response body) |
| Validaties en constraints | Roles moeten een lijst zijn; lege lijst of ontbrekende admin-role geeft 403 |
| Business rules | `"admin"` of `"system_admin"` zijn de twee geldige admin-rollen (CLAUDE.md JWT-standaard) |
| Afhankelijkheden | `get_current_user` uit `src.core.auth.dependencies` |
| Foutafhandeling | `HTTPException(status_code=403, detail="Admin role required")` |
| Caching | Niet van toepassing -- FastAPI evalueert dependencies per request |
| Acceptatiecriteria | Tests met admin-rol geven 200; tests zonder admin-rol geven 403; `dependency_overrides` via `dependencies.require_admin_role` werken correct |

### `get_current_tenant_id`

| Veld | Waarde |
|------|--------|
| Type | FastAPI dependency (thin wrapper) |
| Locatie | `src/core/api/dependencies.py` |
| Gerelateerde flow | Tenant ID Ophalen via Shared Dependency |
| Doel | Bied een centrale, naamgevings-consistente dependency voor tenant_id zodat endpoints geen directe middleware-import nodig hebben |
| Functionele beschrijving | Thin wrapper om `require_tenant_id()` uit `src.core.middleware.tenant_context`. Retourneert `int` tenant_id. |
| Technische beschrijving | `async def get_current_tenant_id() -> int: return require_tenant_id()` -- delegatie zonder extra logica. |
| Zichtbaarheids- en toegangsregels | Publiek in `dependencies.py` |
| Response-specificatie | `int` -- tenant_id |
| Foutafhandeling | `RuntimeError` als ContextVar leeg is (TenantMiddleware niet actief voor dit pad) |
| Caching | Niet van toepassing |
| Acceptatiecriteria | Retourneert correcte tenant_id in tests met actieve middleware; `RuntimeError` bij ontbrekende context |

### Trainingssamenvatting

#### Flow: Admin Dependency Consolidatie

| Veld | Waarde |
|------|--------|
| Actor | Backend engineer / AI agent |
| Voorwaarde | `require_admin_role` is gedefinieerd in `admin_endpoints.py` en wordt op drie plekken geimporteerd vanuit die module |
| Actie | Verplaats definitie naar `src/core/api/dependencies.py`; update alle import-statements en `dependency_overrides` in tests |
| Systeemverwerking | Python lost de `Depends(require_admin_role)` op via het functie-object; alle drie bestanden importeren nu hetzelfde object uit `dependencies.py` |
| Succesrespons | Admin-endpoints geven 200 met admin-token; 403 zonder; test `dependency_overrides` patchen `dependencies.require_admin_role` correct |
| Foutrespons | Als een callsite vergeten wordt bij te werken, dan patcht de `dependency_overrides` het verkeerde object en geeft de test een onverwacht 403 -- grep alle callsites voor de fix |
| Uitzonderingen | Als `admin_endpoints.py` ook andere code bevat die de verplaatste dependency gebruikt, verwijder de definitie niet -- re-export in plaats van verwijderen totdat alle afhankelijkheden gemigreerd zijn |

#### Flow: Dependency Override Regression Fix in Tests

| Veld | Waarde |
|------|--------|
| Actor | AI agent / test suite |
| Voorwaarde | `test_admin_learning_endpoints.py` gebruikt `app.dependency_overrides[admin_endpoints.require_admin_role]` -- na migratie is dit het verkeerde object |
| Actie | Update de import in de test naar `from src.core.api.dependencies import require_admin_role`; update de override-sleutel |
| Systeemverwerking | FastAPI matcht dependency_overrides op functie-object identiteit (`is`-vergelijking); na migratie moet de sleutel het nieuwe object zijn |
| Succesrespons | Test suite PASS; override werkt correct -- 200 of 403 afhankelijk van de test-intentie |
| Foutrespons | Als import niet bijgewerkt is: override heeft geen effect; test geeft onverwacht 403 of 200 -- inspecteer de override-sleutel |
| Uitzonderingen | Bij meerdere bestanden met hetzelfde patroon: grep op de oorspronkelijke module-naam in `tests/` en update alle matches in een batch |

---

## Integratorhandleiding

Geen publieke API-wijzigingen. Bestaande admin-endpoints en evaluatie-endpoints gedragen zich
identiek.

Voor toekomstige endpoints die admin-autorisatie of tenant_id nodig hebben:

```python
from src.core.api.dependencies import require_admin_role, get_current_tenant_id

@router.get("/admin/resource")
async def get_resource(
    _: None = Depends(require_admin_role),
    tenant_id: int = Depends(get_current_tenant_id),
):
    ...
```

Voor tests met `dependency_overrides`:

```python
from src.core.api.dependencies import require_admin_role

app.dependency_overrides[require_admin_role] = lambda: None  # bypass admin check
```

---

## Open aannames / Open vragen / Risico's

| Type | Omschrijving | Status |
|------|--------------|--------|
| Aanname | Alle drie callsite-bestanden zijn gemigreerd; geen andere bestanden importeren de dependency vanuit de oude modules | Bevestigd via grep |
| Aanname | Re-exports in `admin_endpoints.py` en `search_endpoints.py` bewaken backward compatibility totdat verdere migratie plaatsvindt | Bevestigd |
| Risico | Toekomstige tests die de override-sleutel hardcoden als de oude module-locatie falen stil | Gedocumenteerd in Trainingssamenvatting |

---

## QA-checks

- [x] `python -m py_compile src/core/api/dependencies.py` -- geen errors
- [x] `ruff check src/core/api/dependencies.py` -- 0 errors
- [x] `mypy src/core/api/dependencies.py` -- 0 errors
- [x] Admin-endpoints geven 200 met admin-token, 403 zonder
- [x] `pytest tests/unit/api/test_admin_learning_endpoints.py -v` -- PASS
- [x] Geen regressies in overige admin- en evaluatie-tests

---

## Definition of Done

- [x] `require_admin_role` + `get_current_tenant_id` in `dependencies.py`
- [x] Alle drie callsite-bestanden gemigreerd
- [x] Test regression fix in `test_admin_learning_endpoints.py`
- [x] Alle kwaliteitschecks groen
- [x] Feature spec aangemaakt (dit bestand)
- [x] Review APPROVED (`docs/backend/review/review-BE-UTL-036.md`)
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
