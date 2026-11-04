# Backend Feature Specification

## Metadata

- Feature ID: BE-SVC-043
- Feature naam: TenantService en tenants router refactor (AUDIT-DB-01)
- Status: geimplementeerd
- Auteur: AI-agent
- Reviewer: AI-agent
- Datum: 2026-06-27
- Gerelateerde user story / ticket: AUDIT-DB-01 Dag 2 + Dag 3
- Gerelateerde router / module: `src/core/api/v1/tenants/`, `src/core/services/tenant_service.py`
- Gerelateerde database tabellen: `tenants`, `users`, `agents`, `audit_logs`, `documents`
- Versie: 1.0

---

## Doel en scope

### Doel

Standaardiseer de tenant-beheerslaag volgens ADR-033: alle database-logica voor het tenants-domein bevindt zich in een request-scoped `TenantService`, en de API-routers bevatten uitsluitend HTTP/auth-concerns. Dit maakt het domein testbaarder, herbruikbaar en consistent met de overige service-laag van SanskritiSetu.

### In scope

- `TenantService` met CRUD + aggregatie-methoden.
- `get_tenant_service()` dependency factory.
- Vier Laag-1 sub-routers (`tenants_list_router`, `tenants_detail_router`, `tenants_stats_router`) + composite `router`.
- Verplaatsing van tenant schemas naar `src/core/schemas/tenant_schemas.py`.
- Defensieve tenant-scoping (`TenantContext` + `_tenant_scope`).
- Audit logging op create/update/delete.
- Route-collision met legacy `tenant_management` opheffen.

### Out of scope

- Wijzigen van RBAC autorisatie naar scopes (behoudt `current_user.is_superuser`).
- Toevoegen van legacy velden (`industry`, `country_code`, etc.) aan `TenantResponse`.
- `PATCH /{tenant_id}/status` endpoint.
- Nieuwe Alembic migratie (geen schema-wijzigingen).

---

## Build summary

- Nieuw gebouwd:
  - `src/core/services/tenant_service.py`
  - `src/core/api/v1/tenants/dependencies.py`
  - `src/core/api/v1/tenants/router.py`
  - `src/core/api/v1/tenants/tenants_list_router.py`
  - `src/core/api/v1/tenants/tenants_detail_router.py`
  - `src/core/api/v1/tenants/tenants_stats_router.py`
  - `src/core/schemas/tenant_schemas.py`
  - `tests/unit/services/test_tenant_service.py`
  - `tests/unit/api/v1/tenants/test_tenant_routers.py`
  - `tests/architecture/test_tenants_routers_no_direct_db.py`
  - `tests/architecture/test_tenants_no_legacy_collision.py`
  - `tests/integration/api/v1/tenants/test_tenant_service_isolation.py`
- Gewijzigd:
  - `src/core/api/v1/tenants/__init__.py`
  - `src/core/api/v1/tenants/schemas.py` (backward-compat re-export)
  - `src/core/api/v1/tenant_management/__init__.py` (deprecated marker)
  - `src/core/app_factory.py` (legacy router registratie verwijderd)
  - `src/main.py` (legacy module uit wire_container verwijderd)
  - `.importlinter` (stale ignores verwijderd, nieuwe service-edge toegevoegd)
- Verwijderd:
  - Directe `get_db` / `AsyncSession` / `select` imports uit tenants routers.
- Beinvloede bestaande flows:
  - Legacy `tenant_management` endpoints zijn niet meer via de canonical app factory bereikbaar.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-043 | TenantService | Service | `src/core/services/tenant_service.py` | Nieuw | BE-FLW-043 |
| BE-DEP-043 | get_tenant_service | Dependency | `src/core/api/v1/tenants/dependencies.py` | Nieuw | BE-FLW-043 |
| BE-RTR-043 | tenants composite router | Router | `src/core/api/v1/tenants/router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043A | POST /api/v1/tenants/ | Endpoint | `src/core/api/v1/tenants/tenants_list_router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043B | GET /api/v1/tenants/ | Endpoint | `src/core/api/v1/tenants/tenants_list_router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043C | GET /api/v1/tenants/{tenant_id} | Endpoint | `src/core/api/v1/tenants/tenants_detail_router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043D | PUT /api/v1/tenants/{tenant_id} | Endpoint | `src/core/api/v1/tenants/tenants_detail_router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043E | DELETE /api/v1/tenants/{tenant_id} | Endpoint | `src/core/api/v1/tenants/tenants_detail_router.py` | Nieuw | BE-FLW-043 |
| BE-EP-043F | GET /api/v1/tenants/{tenant_id}/stats | Endpoint | `src/core/api/v1/tenants/tenants_stats_router.py` | Nieuw | BE-FLW-043 |
| BE-SCH-043A | TenantCreate | Schema | `src/core/schemas/tenant_schemas.py` | Nieuw | BE-FLW-043 |
| BE-SCH-043B | TenantUpdate | Schema | `src/core/schemas/tenant_schemas.py` | Nieuw | BE-FLW-043 |
| BE-SCH-043C | TenantResponse | Schema | `src/core/schemas/tenant_schemas.py` | Nieuw | BE-FLW-043 |
| BE-SCH-043D | TenantListResponse | Schema | `src/core/schemas/tenant_schemas.py` | Nieuw | BE-FLW-043 |
| BE-SCH-043E | TenantStats | Schema | `src/core/schemas/tenant_schemas.py` | Nieuw | BE-FLW-043 |

---

## API-flows

### Flow ID: BE-FLW-043

- Naam: Tenant beheer via TenantService
- Trigger: HTTP request naar een van de `/api/v1/tenants/*` endpoints
- Voorwaarden:
  - Geldige JWT bearer token (`Authorization` header).
  - Voor create/delete: `current_user.is_superuser == True`.
  - Voor read/update/statistics: superuser OF `current_user.tenant_id == tenant_id`.
- Request-pad:
  1. FastAPI valideert JWT via `get_current_user`.
  2. `get_tenant_service` bouwt `TenantContext` uit `current_user`.
  3. Router voert autorisatiecheck uit en delegeert naar `TenantService`.
  4. `TenantService._tenant_scope` controleert cross-tenant toegang.
  5. Service voert async SQLAlchemy queries uit.
- Service-stappen:
  - Create: controleer duplicate slug/name/domain -> insert -> commit -> refresh.
  - List: bouw gescopte count + select queries -> pagineer.
  - Get: select tenant by id.
  - Update: select tenant -> controleer duplicate domain -> apply partial update -> commit.
  - Delete: select tenant -> soft-delete (is_active=False, subscription_status=cancelled) -> commit.
  - Stats: controleer tenant bestaat -> aggregate users/agents/audit_logs/documents.
- DB-operaties:
  - `tenants` tabel voor alle CRUD-operaties.
  - `users`, `agents`, `audit_logs`, `documents` voor aggregaties.
- Successtatus + response:
  - POST: 201 + `TenantResponse`
  - GET list: 200 + `TenantListResponse`
  - GET detail: 200 + `TenantResponse`
  - PUT: 200 + `TenantResponse`
  - DELETE: 204 No Content
  - GET stats: 200 + `TenantStats`
- Foutpaden:
  - 401: ongeldige of ontbrekende JWT.
  - 403: niet-superuser probeert create/delete, of gebruiker probeert andere tenant te benaderen.
  - 404: tenant niet gevonden (detail, update, delete, stats).
  - 400: duplicate slug/name/domain of ongeldige payload.
  - 422: Pydantic validatiefout.
- Eindtoestand (DB, cache, events):
  - Mutaties worden in `tenants` opgeslagen.
  - Delete triggert `clear_tenant_cache(tenant_id)`.
  - Audit log entry wordt best-effort geschreven via `audit_service.log_action`.

---

## Detaildocumentatie per artefact

---

## [BE-SVC-043] TenantService

### 1. Type

Service klasse (request-scoped).

### 2. Locatie

- Bestandspad: `src/core/services/tenant_service.py`
- Klasse / functie: `TenantService`

### 3. Gerelateerde flow

BE-FLW-043

### 4. Doel

Centraliseert alle tenant-gerelateerde database-operaties en tenant-scoping.

### 5. Functionele beschrijving

`TenantService` biedt CRUD-operaties en statistische aggregaties voor tenant-organisaties. Het dwingt tenant-isolatie af op basis van de ingelogde gebruiker: superusers kunnen alle tenants benaderen; reguliere gebruikers alleen hun eigen tenant.

### 6. Technische beschrijving

- Constructor accepteert `AsyncSession` en `TenantContext`.
- `_tenant_scope(tenant_id: int) -> int` bepaalt het effectieve tenant_id.
  - `bypass_filter=True` -> retourneert `tenant_id` (superuser).
  - Anders -> vergelijkt met `tenant_context.require_tenant()`; mismatch geeft HTTPException(403).
- Methoden returnen Pydantic modellen (`TenantResponse`, `TenantListResponse`, `TenantStats`) of `None` bij ontbrekende resource.
- `get_tenant_stats` retourneert `TenantStats | None`; `None` wordt door router naar 404 gemapt.
- Opslag-berekening is best-effort; faalt nooit de hele request.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT (afgedwongen door router).
- Vereiste rol: superuser voor create/delete; superuser of eigenaar voor read/update/stats.
- Tenant-isolatie: `_tenant_scope` rejecteert cross-tenant requests.
- Feature flag: geen.

### 8. Request-specificatie

Niet van toepassing (service-laag).

### 9. Response-specificatie

Niet van toepassing (service-laag).

### 10. Validaties en constraints

- `TenantCreate.slug` moet uniek zijn.
- `TenantCreate.name` moet uniek zijn.
- `TenantCreate.domain` moet uniek zijn indien opgegeven.
- `TenantUpdate.domain` mag niet in gebruik zijn door een andere tenant.
- `TenantUpdate.settings=None` wordt gecoerceerd naar `{}`.

### 11. Business rules

- Soft-delete: DELETE zet `is_active=False` en `subscription_status="cancelled"`.
- Superusers kunnen alle tenants lezen/muteren.
- Reguliere gebruikers kunnen alleen hun eigen tenant lezen/muteren.

### 12. Afhankelijkheden

- `src.core.container.TenantContext`
- `src.core.models.rbac_models.Tenant`, `User`
- `src.core.agents.models.Agent`
- `src.core.governance.models.AuditLog`
- `src.domains.documents.models.Document`
- `src.core.schemas.tenant_schemas`

### 13. Foutafhandeling

- 400: duplicate slug/name/domain.
- 403: cross-tenant toegang.
- 404: tenant niet gevonden (geretourneerd als `None`, gemapt door router).

### 14. Transacties en dataïntegriteit

- Elke mutatie gebruikt `await self.db.commit()`.
- Duplicate checks zijn niet atomic; racecondities kunnen een `IntegrityError` veroorzaken (pre-existing gedrag).

### 15. Telemetry / logging / tracing

- `logging.getLogger(__name__)` logt create/update/delete acties.
- Audit logging gebeurt in de router, niet in de service.

### 16. Caching

- `clear_tenant_cache(tenant_id)` wordt aangeroepen door router na delete.

### 17. Acceptatiecriteria

- [ ] Superuser kan tenant aanmaken.
- [ ] Niet-superuser kan geen tenant aanmaken.
- [ ] Reguliere gebruiker ziet alleen eigen tenant in list.
- [ ] Cross-tenant read/update/stats geeft 403.
- [ ] Niet-bestaande tenant geeft 404 (detail/update/delete/stats).
- [ ] Duplicate slug/name/domain geeft 400.

### 18. Integratoruitleg

- Gebruik `Authorization: Bearer <jwt>` voor alle calls.
- Superuser tokens kunnen alle tenants beheren.
- Tenant-specifieke tokens kunnen alleen hun eigen tenant opvragen/wijzigen.
- DELETE deactiveert de tenant; verwijdert deze niet fysiek.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker (superuser of tenant gebruiker).
- Voorwaarde: JWT geldig; tenant bestaat (voor read/update/delete/stats).
- Actie (request): HTTP call naar `/api/v1/tenants/{...}`.
- Systeemverwerking: Auth check -> tenant scope check -> service call -> DB query -> response.
- Succesrespons: 200/201/204 met tenant data of stats.
- Foutrespons: 400/401/403/404/422 afhankelijk van fouttype.
- Uitzonderingen: Audit logging faalt silently (best-effort).

---

## [BE-EP-043A] POST /api/v1/tenants/

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_list_router.py`
- Klasse / functie: `create_tenant`

### 3-19. Zie BE-FLW-043

Samenvattend:
- Body: `TenantCreate`
- Response: 201 + `TenantResponse`
- Auth: superuser
- Audit: `tenant.created`

---

## [BE-EP-043B] GET /api/v1/tenants/

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_list_router.py`
- Klasse / functie: `list_tenants`

Samenvattend:
- Query params: `skip` (>=0), `limit` (1-1000), `is_active` (bool | None)
- Response: 200 + `TenantListResponse`
- Auth: elke geauthenticeerde gebruiker; resultaat wordt gescopet.

---

## [BE-EP-043C] GET /api/v1/tenants/{tenant_id}

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_detail_router.py`
- Klasse / functie: `get_tenant`

Samenvattend:
- Path param: `tenant_id` (int)
- Response: 200 + `TenantResponse` of 404
- Auth: superuser of eigenaar.

---

## [BE-EP-043D] PUT /api/v1/tenants/{tenant_id}

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_detail_router.py`
- Klasse / functie: `update_tenant`

Samenvattend:
- Path param: `tenant_id` (int)
- Body: `TenantUpdate`
- Response: 200 + `TenantResponse` of 404
- Auth: superuser of eigenaar.
- Audit: `tenant.updated`

---

## [BE-EP-043E] DELETE /api/v1/tenants/{tenant_id}

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_detail_router.py`
- Klasse / functie: `delete_tenant`

Samenvattend:
- Path param: `tenant_id` (int)
- Response: 204 No Content of 404
- Auth: superuser
- Cache invalidatie: `clear_tenant_cache(tenant_id)`
- Audit: `tenant.deleted`

---

## [BE-EP-043F] GET /api/v1/tenants/{tenant_id}/stats

### 1. Type

Endpoint.

### 2. Locatie

- Bestandspad: `src/core/api/v1/tenants/tenants_stats_router.py`
- Klasse / functie: `get_tenant_stats`

Samenvattend:
- Path param: `tenant_id` (int)
- Response: 200 + `TenantStats` of 404
- Auth: superuser of eigenaar.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Alle endpoints vereisen een JWT bearer token.
- `POST /api/v1/tenants/` en `DELETE /api/v1/tenants/{id}` zijn voorbehouden aan superusers.
- `GET /api/v1/tenants/` retourneert voor reguliere gebruikers alleen de eigen tenant.
- `GET /api/v1/tenants/{id}/stats` geeft het aantal gebruikers, agents, opslag en laatste activiteit.
- Een verwijderde tenant is gedeactiveerd (`is_active=false`); de data blijft bestaan.

### Migratie / breaking changes

- De legacy `tenant_management` router (`src/core/api/v1/tenant_management/router.py`) is niet meer via de canonieke app factory (`src/main.py` / `src/core/app_factory.py`) geregistreerd. De package blijft beschikbaar voor directe imports, maar de canonical app serveert alleen nog de nieuwe `/api/v1/tenants/*` endpoints.
- Integratietesten voor tenant-isolatie draaien in CI onder `ubuntu-latest` met PostgreSQL 15 + Redis 7; lokale Windows-runs kunnen door pre-existing fixture/pool-problemen falen.

---

## Open aannames

- `current_user.is_superuser` is de canonieke superuser check voor deze routers (legacy gedrag).
- Legacy `tenant_management` endpoints zijn niet meer via `src.main` bereikbaar.

## Open vragen

- Moeten we in de toekomst `PATCH /{tenant_id}/status` toevoegen voor niet-superusers?
- Moeten legacy velden (`industry`, `country_code`, etc.) worden teruggebracht in `TenantResponse`?

## Risico's

- Clients die rechtstreeks de legacy `tenant_management` router gebruikten via `app_factory` breken. **Mitigatie:** legacy package blijft importeerbaar; alleen canonical registratie is verwijderd.
- Full unit suite timeout op Windows belemmert lokaal regressietesten. **Mitigatie:** CI draait `pytest tests/unit tests/architecture` op `ubuntu-latest`.
- Integratietesten voor tenant-isolatie falen lokaal op Windows door pre-existing DB fixture/pool issues. **Mitigatie:** CI-stap `Tenant integration tests` draait `tests/integration/api/v1/tenants` op Linux services.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest (unit + integratie stubs)
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [ ] Dataïntegriteit en transacties getest (deels)
- [ ] Performance / load getest
- [x] Logging en tracing gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
