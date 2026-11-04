# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-057
- Feature naam: Edu-codes autorisatie (curator/admin JWT op /edu/codes)
- Status: Gebouwd
- Auteur: implementatie-agent iter/wk1-edu-codes-auth
- Reviewer: (open -- review volgt via regie)
- Datum: 2026-09-24
- Gerelateerde user story / ticket: sprint "Week 1 markt-blokkers", markt-review 2026-09-24
- Gerelateerde router / module: `src/core/api/v1/foundation/edu.py`, `src/core/shared/public_registry.py`
- Gerelateerde frontend endpoints: geen (portal-curator UI gebruikt dezelfde routes met JWT)
- Gerelateerde database tabellen: `educational_access`, `study_collections`, `portal_users`
- Versie: 1.0

---

## Doel en scope

### Doel

De drie code-beheerendpoints van de edu-leeromgeving (`POST /edu/codes`,
`GET /edu/codes`, `DELETE /edu/codes/{id}`) hingen zonder enige authenticatie in
de foundation-router. Iedere anonieme aanroeper kon toegangscodes minten, de
lijst met docent-e-mails en klasnamen (PII) uitlezen en codes revoken. Deze
feature sluit die deur: code-beheer vereist een geldig portal-JWT met rol
`curator` of `admin`, gebonden aan de eigen tenant.

### In scope

- `require_curator` (portal-JWT, aud="portal", scope="portal_uploader", rol
  curator/admin) op alle drie de `/edu/codes`-endpoints.
- Expliciete tenant-binding: `current_user.tenant_id` moet overeenkomen met de
  tenant uit de `{tenantSlug}` in het pad, anders 403 (zelfde patroon als
  `admin/curatie.py`).
- `PublicEndpointRegistry` verscherpt: de TenantMiddleware laat alleen nog
  `/foundation/edu/session` en `/foundation/edu/content*` tokenloos door
  (cookie-flow); `/foundation/edu/codes*` valt fail-closed buiten de
  publieke set.
- Rode-tests-eerst: 1 unit-test (registry) + 5 integratietests die vóór de fix
  rood waren en nu groen zijn, plus 2 karakterisatietests (happy path).

### Out of scope

- **Docent-rol voor eigen codes.** ADR-029 (r.230-235) beschrijft dat een
  geactiveerde docent `edu_access_codes` voor eigen klassen kan aanmaken. Dat
  concept bestaat NIET in de modellen: `EducationalAccess` heeft geen
  `portal_user_id`/creator-koppeling, alleen een vrije `email`-string, en de
  portal-auth (`auth.py`) kent geen teacher-registratieflow die een JWT met
  teacher-rol uitgeeft (rollen die tokens krijgen: visitor/curator/admin).
  "Eigen codes" vereist een schema-migratie (creator-FK) en een
  teacher-loginflow -- dat is een aparte feature, geen security-hotfix. Bewuste
  scope-beperking: code-beheer is nu **curator/admin-only**.
- Frontend-aanpassingen (de curator-UI stuurt al een Authorization-header mee;
  anonieme calls waren nooit een bedoelde flow).
- Wijzigingen aan `/edu/session` en `/edu/content*` (cookie-flow blijft
  ongewijzigd publiek door de middleware, met sessie-eis in de dependency).

---

## Build summary

- Nieuw gebouwd: geen nieuwe endpoints; autorisatie toegevoegd aan bestaande.
- Gewijzigd:
  - `src/core/api/v1/foundation/edu.py` -- `Depends(require_curator)` +
    tenant-check op `create_edu_code`, `list_edu_codes`, `revoke_edu_code`.
  - `src/core/shared/public_registry.py` -- edu-doorlaat versmald van
    `/foundation/edu/` (alles) naar `/foundation/edu/session` +
    `/foundation/edu/content`.
  - `tests/unit/test_foundation_edu_session.py` -- registry-regressietest voor
    `/edu/codes*`.
  - `tests/integration/api/v1/foundation/test_edu.py` -- nieuwe testklasse
    `TestEduCodesAuth` (7 tests).
- Verwijderd: niets.
- Beinvloede bestaande flows: alleen `/edu/codes*`; sessie- en content-flows
  zijn ongewijzigd (26 bestaande integratietests groen).

### Keuze Depends vs Security (onderzocht)

FastAPI's `Security()` verschilt alleen van `Depends()` doordat het OAuth2-scopes
naar OpenAPI/Swagger publiceert; functioneel zijn ze identiek
([FastAPI reference: Dependencies - Depends() and Security()](https://fastapi.tiangolo.com/reference/dependencies/),
geraadpleegd 2026-09-24). Het portal-JWT-mechanisme hier gebruikt geen
OAuth2-scheme maar een eigen Bearer-header-dependency (`require_portal_user`),
dus `Depends(require_curator)` is het correcte patroon -- consistent met alle
bestaande foundation-admin-endpoints (`admin/curatie.py`, 11 endpoints).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-057 | Edu-codes autorisatie | Auth guard (rol + tenant) | `src/core/api/v1/foundation/edu.py` | Wijziging | BE-FLW-edu-codes |
| BE-EP-044 | Edu code management endpoints | Endpoint | `src/core/api/v1/foundation/edu.py` | Wijziging (auth toegevoegd) | BE-FLW-edu-codes |
| BE-DEP-edu-curator | require_curator (bestaand, hergebruikt) | Depends-dependency | `src/core/api/v1/foundation/dependencies.py` | Ongewijzigd | BE-FLW-edu-codes |
| BE-MID-tenant-registry | PublicEndpointRegistry edu-regel | Middleware-config | `src/core/shared/public_registry.py` | Wijziging | BE-FLW-edu-codes |

---

## API-flows

### Flow ID: BE-FLW-edu-codes

- Naam: Edu access-code beheer (mint / list / revoke)
- Trigger (HTTP-methode + route):
  - `POST /{tenantSlug}/foundation/edu/codes`
  - `GET /{tenantSlug}/foundation/edu/codes`
  - `DELETE /{tenantSlug}/foundation/edu/codes/{id}`
- Voorwaarden (auth, tenant, feature flag):
  1. TenantMiddleware: pad is NIET publiek -> geldig portal-JWT vereist
     (Bearer-header), anders 401 "Missing or invalid authentication".
  2. `require_portal_user`: JWT met aud="portal", scope="portal_uploader",
     geldige `tenant_id`- en `sub`-claims, PortalUser bestaat en is niet
     geblokkeerd -> anders 401.
  3. `require_curator`: rol is `curator` of `admin` -> anders 403.
  4. Endpoint: `current_user.tenant_id == tenant.id` (opgelost uit
     `{tenantSlug}`) -> anders 403 "User does not belong to this tenant".
- Request-pad: client -> Traefik -> TenantMiddleware (JWT) -> endpoint ->
  `require_curator` -> `public_tenant_scope` -> tenant-check -> ORM.
- Service-stappen: ongewijzigd (code-generatie, hashing, StudyCollection-link,
  revoke via `is_active=False`).
- DB-operaties: ongewijzigd, al tenant-scoped via `EducationalAccess.tenant_id`.
- Successtatus + response: 201 (mint, plaintext code eenmalig), 200 (lijst,
  nooit hashes/plaintext), 204 (revoke).
- Foutpaden:
  - Geen/verlopen/verkeerd token: 401 (middleware of dependency).
  - Juiste token, verkeerde rol (visitor/uploader): 403.
  - Edu-sessie-cookie zonder JWT: 401 (cookie is geen JWT; pad niet publiek).
  - Curator van tenant A op slug van tenant B: 403 (beide richtingen getest).
  - Onbekende tenant-slug: 404 via `public_tenant_scope`.
  - Onbekend code-id bij revoke: 404 "Educational code not found".
- Eindtoestand (DB, cache, events): ongewijzigd; geen nieuwe events of caches.

---

## Detaildocumentatie per artefact

## [BE-SEC-057] Edu-codes autorisatie

### 1. Type

- Auth guard / permission check (rol + tenant-binding) op drie endpoints.

### 2. Locatie

- Bestandspad: `src/core/api/v1/foundation/edu.py`
- Functies: `create_edu_code`, `list_edu_codes`, `revoke_edu_code`
- Registry: `src/core/shared/public_registry.py`, `PublicEndpointRegistry.is_public`

### 3. Gerelateerde flow

- BE-FLW-edu-codes (hierboven).

### 4. Doel

- Voorkomen dat anonieme of laag-privilege aanroepers codes minten, PII
  (docent-e-mails, klasnamen) lezen of codes revoken.

### 5. Functionele beschrijving

- Alleen curatoren en admins van een stichting beheren de edu-toegangscodes van
  die stichting. Docenten en leerlingen gebruiken codes alleen via de publieke
  code-invoer (`POST /edu/session`); die flow is ongewijzigd.

### 6. Technische beschrijving

- `current_user: PortalUser = Depends(require_curator)` als eerste auth-stap in
  de drie handlers; `require_curator` -> `require_portal_user` valideert het
  JWT cryptografisch (aud="portal"), scope en DB-status.
- Na `public_tenant_scope(tenantSlug, session)` volgt
  `if current_user.tenant_id != tenant.id: raise 403` -- identiek aan het
  curatie.py-patroon.
- Registry: de substring-regel `"/foundation/edu/" in path -> True` is vervangen
  door twee specifieke regels (`/foundation/edu/session`,
  `/foundation/edu/content`). `/foundation/edu/codes` matcht geen enkele
  publieke regel meer en valt op de fail-closed `return False`.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: portal-JWT (Bearer).
- Vereiste rol / scope: scope="portal_uploader" + rol curator of admin.
- Tenant-isolatie: dubbel -- JWT-tenant moet gelijk zijn aan pad-tenant, EN alle
  queries filteren op `tenant_id` van de opgeloste pad-tenant.
- Feature flag: geen.

### 8. Request-specificatie

- Methode: POST / GET / DELETE
- Route: `/{tenantSlug}/foundation/edu/codes` (+ `/{id}` voor DELETE)
- Path parameters: `tenantSlug` (str), `id` (int, alleen DELETE)
- Query parameters: `teacher_email`, `active_only` (alleen GET)
- Request body (schema): `CreateEduCodeRequest` (alleen POST)
- Verplichte headers: `Authorization: Bearer <portal-JWT>`

### 9. Response-specificatie

- Successtatus: 201 / 200 / 204
- Response schema: `EduCodeCreateResponse` / `EduCodeListResponse` / geen body
- Foutstatussen: 401, 403, 404, 422, 429 (rate limit POST), 500

### 10. Validaties en constraints

- Ongewijzigd: Pydantic-validatie op `CreateEduCodeRequest` (e-mail, klasnaam,
  valid_hours 1-168).

### 11. Business rules

- Code-beheer is curator/admin-only (bewuste scope-beperking, zie Out of scope).
- Plaintext codes en hashes worden nooit via GET teruggegeven (bestaand).
- POST blijft rate-limited (5/min/IP) als defense-in-depth.

### 12. Afhankelijkheden

- `require_curator`, `require_portal_user`, `public_tenant_scope` uit
  `src/core/api/v1/foundation/dependencies.py` (ADR-033-facade).
- `PublicEndpointRegistry` in `src/core/shared/public_registry.py`
  (TenantMiddleware, SecurityMiddleware, QuotaMiddleware).

### 13. Foutafhandeling

- 400: n.v.t. (geen eigen validatie toegevoegd)
- 401: ontbrekend/ongeldig/verlopen JWT; edu-cookie zonder JWT
- 403: rol visitor/uploader; JWT-tenant != pad-tenant
- 404: onbekende tenant-slug; onbekend code-id bij DELETE
- 409: n.v.t.
- 422: Pydantic-validatiefout op POST-body
- 429: auth-rate-limit op POST (bestaand)
- 500: unieke-code-generatie mislukt na 5 pogingen (bestaand)
- 503: n.v.t. (geen sessie-store nodig voor code-beheer)

### 14. Transacties en data-integriteit

- Ongewijzigd: POST commit access + collection in een sessie; DELETE zet
  `is_active=False` en commit.

### 15. Telemetry / logging / tracing

- TenantMiddleware logt AUTH FAIL op ontbrekend token (bestaand gedrag, nu ook
  actief voor /edu/codes). Geen nieuwe logging toegevoegd; geen PII gelogd.

### 16. Caching

- Gecached: nee (tenant-resolutie-cache ongewijzigd).

### 17. Acceptatiecriteria

- Anoniem: 401 op POST, GET en DELETE /edu/codes. (test:
  `test_anonymous_gets_401_on_all_code_endpoints`)
- Portal-visitor (scope portal_uploader, rol visitor): 403 op alle drie.
  (`test_visitor_role_gets_403_on_all_code_endpoints`)
- Geldige edu-sessie-cookie (teacher) zonder JWT: 401 op GET.
  (`test_edu_session_cookie_grants_no_codes_access`)
- Curator eigen tenant: 201 mint, 200 list, 204 revoke, item verdwenen uit
  actieve lijst. (`test_curator_can_mint_list_and_revoke`)
- Admin eigen tenant: 201 mint. (`test_admin_can_mint_code`)
- Curator tenant 2 op slug tenant 1: 403 op alle drie.
  (`test_curator_of_other_tenant_gets_403`)
- Curator tenant 1 op slug tenant 2: 403.
  (`test_curator_cannot_use_other_tenants_slug`)
- Registry: `/edu/codes` en `/edu/codes/{id}` niet publiek; `/edu/session` en
  `/edu/content*` wel. (`test_edu_codes_paths_are_not_public` +
  bestaande registry-tests)

### 18. Integratoruitleg

- Roep code-beheer altijd aan met `Authorization: Bearer <portal-JWT>` van een
  curator of admin.
- De JWT moet bij dezelfde tenant horen als de `{tenantSlug}` in de URL.
- De publieke code-invoer voor leerlingen/docenten (`POST /edu/session`) blijft
  zonder JWT werken; daar verandert niets.
- Een edu-sessie-cookie geeft GEEN toegang tot code-beheer.

### 19. Trainingssamenvatting

- Actor: curator of admin van een foundation-tenant.
- Voorwaarde: geldig portal-JWT (aud=portal, scope=portal_uploader) met rol
  curator/admin en tenant_id gelijk aan de pad-tenant.
- Actie (request): POST/GET/DELETE `/{tenantSlug}/foundation/edu/codes[/id]`.
- Systeemverwerking: TenantMiddleware (JWT vereist, pad niet publiek) ->
  require_portal_user (JWT + DB) -> require_curator (rol) -> tenant-binding ->
  bestaande code-logica.
- Succesrespons: 201 met eenmalige plaintext code / 200 lijst zonder hashes /
  204 revoke.
- Foutrespons: 401 zonder of met ongeldig JWT (ook bij alleen edu-cookie), 403
  bij visitor-rol of vreemde tenant, 404 bij onbekende slug of code-id.
- Uitzonderingen: docent-self-service voor eigen codes is bewust uitgesteld;
  vereist creator-FK op EducationalAccess plus teacher-loginflow.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Code-beheer is een beheerdersfunctie: altijd Bearer-token van curator/admin.
- Gebruik de tenant-slug van de eigen stichting in het pad; cross-tenant calls
  geven 403.
- Leerlingen/docenten krijgen alleen via `POST /edu/session` met een code
  toegang tot `/edu/content*`; dat blijft publiek (rate-limited).

---

## Open aannames

- De curator-UI (frontend) stuurt al een Authorization-header mee op deze
  routes; niet geverifieerd in deze iteratie (geen frontend-wijziging nodig
  volgens repo-grep op edu/codes-aanroepen -- frontend koppeling wordt door de
  regie bevestigd).

## Open vragen

- Moet docent-self-service (ADR-029 r.230-235) alsnog worden ingepland? Zo ja:
  aparte feature met migratie (`EducationalAccess.created_by_portal_user_id`)
  en teacher-loginflow.

## Risico's

- Clients die /edu/codes anoniem aanriepen (misbruik of misconfiguratie) krijgen
  nu 401 -- dat is het beoogde effect, maar een legitieme ongedocumenteerde
  caller zou breken. Geen gevonden in de repo.
- `SecurityMiddleware` en `QuotaMiddleware` gebruiken dezelfde registry;
  /edu/codes valt nu onder hun niet-publieke pad (meer controle, geen risico).

---

## QA-checks

- [x] Endpoint functioneel getest (happy path): curator mint/list/revoke, admin mint
- [x] Alle foutstatus-codes getest: 401 (3x), 403 (2 vormen), 404 via bestaande tests
- [x] Auth en permissies getest: anoniem, visitor, edu-cookie, curator, admin
- [x] Tenant-isolatie getest: beide richtingen 403
- [x] Validaties getest (ongeldige invoer): ongewijzigd, bestaande tests groen
- [x] Edge cases getest: revoke van onbekend id (bestaand), actieve-lijst-filter
- [x] Data-integriteit en transacties getest: ongewijzigd
- [ ] Performance / load getest (indien relevant): n.v.t. (auth-check is O(1) DB-lookup)
- [ ] Caching getest (indien van toepassing): n.v.t.
- [x] Logging en tracing gecontroleerd: middleware AUTH FAIL-log bestaand

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar (en getest: 6 rood -> groen)
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [ ] Review door reviewer-prompt: volgt via regie (Gate 2)
