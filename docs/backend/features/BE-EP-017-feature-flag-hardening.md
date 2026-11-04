# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-017
- Feature naam: Feature Flag API & Database RLS Hardening
- Status: READY
- Auteur: Antigravity
- Reviewer: Antigravity (Quality Reviewer Subagent)
- Datum: 2026-06-01
- Gerelateerde user story / ticket: SP-FF-02
- Gerelateerde router / module: src/core/api/feature_flags_endpoints.py
- Gerelateerde frontend endpoints: /api/features, /api/tenant/features, /api/tenant/tier, /api/admin/features/{feature}/toggle, /api/tenant/features/{feature}/check
- Gerelateerde database tabellen: feature_flags
- Versie: 1.0.0

---

## Doel en scope

### Doel

Hardening en migratie van de Feature Flag engine en API endpoints conform PostgreSQL Row-Level Security (RLS) en FastAPI best practices. Dit zorgt voor 100% waterdichte tenant-isolatie en elimineert database session leaks en test-regressies.

### In scope

- Creatie van de `feature_flags` database tabel met cascade ondelete en unieke index.
- Activering van Row-Level Security (RLS) op de `feature_flags` tabel met het safe `NULLIF` patroon.
- Refactoring van alle endpoints in `feature_flags_endpoints.py` naar de FastAPI `Depends(get_db)` sessie-injectie om transactional test rollbacks te ondersteunen.
- Integratie van `FeatureFlagManager` in de reguliere ASGI-lifespan en test-applicatie bootstrap.
- Robuuste integratietesten onder een onbevoorrechte rol (`rls_ff_tester`) om RLS-isolatie direct te testen.

### Out of scope

- Stripe betalingsverwerking (afgehandeld in Monetization Fases 1-3).
- Dynamische rate limits updates via feature flags.

---

## Build summary

- Nieuw gebouwd:
  - Alembic migratie `20260601b_add_feature_flags_and_rls.py` (BE-MIG-009)
  - `FeatureFlag` SQLAlchemy Model registratie in `src/core/feature_flags/models.py` (BE-MDL-011)
  - `rls_ff_tester` role-based isolation test cases in `test_feature_flag_security.py` (BE-SEC-017)
- Gewijzigd:
  - FastAPI endpoints in `feature_flags_endpoints.py` (Depends-gebaseerde database sessies) (BE-EP-017)
  - Lifespan initialization `src/core/app_lifespan.py`
  - Test bootstrap `src/main.py` en `tests/integration/conftest.py`
- Verwijderd:
  - Handmatige `async with get_db_session()` aanroepen in feature flag endpoints.
- Beinvloede bestaande flows:
  - Feature flag check flow (`GET /tenant/features/{feature}/check`)
  - Feature flag admin toggle flow (`POST /admin/features/{feature}/toggle`)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MIG-009 | add_feature_flags_and_rls | Alembic-migratie | `src/alembic/versions/20260601b_add_feature_flags_and_rls.py` | Nieuw | DB Setup |
| BE-MDL-011 | FeatureFlag Model | SQLAlchemy Model | `src/core/feature_flags/models.py` | Nieuw | DB Entity |
| BE-EP-017 | Feature Flags API Endpoints | API-endpoints | `src/core/api/feature_flags_endpoints.py` | Wijziging | Feature Toggling & Checks |
| BE-SEC-017 | Feature Flags RLS Isolation | Security | `tests/integration/security/test_feature_flag_security.py` | Nieuw | Security Validation |

---

## API-flows

### Flow ID: BE-FLW-002

- Naam: Feature Toggle & Verification Flow
- Trigger (HTTP-methode + route of event): `POST /api/admin/features/{feature}/toggle`
- Voorwaarden (auth, tenant, feature flag): Administrator-rechten (JWT met admin scope) + geldige `target_tenant_id`
- Request-pad: Admin Client -> API Gateway (Traefik) -> FastAPI Endpoint (`toggle_feature`) -> DB & Redis Cache
- Service-stappen:
  1. Valideer administrator privilege via `require_admin`.
  2. Valideer de op te geven `feature` parameter tegen de `Feature` enum.
  3. Start database transactie binnen `TenantFilterBypass` context.
  4. Voer `SELECT set_config('app.current_tenant', ...)` uit om de Postgres RLS parameter in te stellen.
  5. Zoek of maak de `FeatureFlag` record aan in Postgres en commit de transactie.
  6. Invalideer de Redis cache sleutel voor de betreffende tenant en feature flag.
- DB-operaties: INSERT/UPDATE op `feature_flags` tabel.
- Successtatus + response: `200 OK` met JSON body `{"success": true, "feature": "...", "tenant_id": "...", "enabled": bool}`
- Foutpaden:
  - `400 Bad Request` bij ongeldige feature flag naam.
  - `401 Unauthorized` bij ongeldig of ontbrekend JWT token.
  - `403 Forbidden` indien de gebruiker geen administrator is.
- Eindtoestand (DB, cache, events): Database bevat de nieuwe flag-instelling; Redis cache-sleutel is gewist (invalidatie).

---

## Detaildocumentatie per artefact

---

## [BE-EP-017] Feature Flags API Endpoints

### 1. Type

API Endpoints

### 2. Locatie

- Bestandspad: `src/core/api/feature_flags_endpoints.py`
- Klasse / functie: `list_all_features`, `get_tenant_features`, `get_tenant_tier`, `toggle_feature`, `check_feature`

### 3. Gerelateerde flow

BE-FLW-002 (Feature Toggle & Verification Flow)

### 4. Doel

Exposeren van feature flags en tiers en administreren van tenant-specifieke toggles.

### 5. Functionele beschrijving

Hiermee kunnen tenants hun actieve functionaliteiten en abonnementstier inzien, kan de frontend controleren of specifieke UI-elementen getoond mogen worden, en kunnen beheerders functionaliteiten per tenant aan- of uitzetten.

### 6. Technische beschrijving

De endpoints gebruiken FastAPI dependency injection `Depends(get_db)` om asynchrone SQLAlchemy connecties te beheren. Dit zorgt ervoor dat test suites database-transacties correct kunnen delen en terugrollen.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja (JWT via cookie of header)
- Vereiste rol / scope: Admin rol vereist voor `toggle_feature`; regulier geauthenticeerde tenant scope voor overige endpoints.
- Tenant-isolatie: Gecentraliseerd via database Row-Level Security (RLS) en tenant-context middleware.
- Feature flag: N.v.t. (is de feature flag beheerder zelf).

### 8. Request-specificatie

- Methode: POST / GET
- Route: `/api/tenant/features`, `/api/tenant/tier`, `/api/admin/features/{feature}/toggle`, `/api/tenant/features/{feature}/check`
- Path parameters: `feature` (str)
- Query parameters: `target_tenant_id` (int, alleen voor admin toggle)
- Request body (schema): `ToggleFeatureRequest` (alleen voor toggle)
- Verplichte headers: `Authorization: Bearer <JWT>`

### 9. Response-specificatie

- Successtatus: `200 OK`
- Response schema: `TenantFeaturesResponse`, `FeatureInfo`, of generic dict.
- Foutstatussen: `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.

### 10. Validaties en constraints

- De `feature` path parameter moet exact matchen met een waarde uit de `Feature` enum.
- `target_tenant_id` moet een geldig integer tenant ID zijn.

### 11. Business rules

- Tiers hierarchie: Enterprise > Pro > Starter > Free. Hogere tiers erven automatisch alle features van lagere tiers.

### 12. Afhankelijkheden

- `get_db` FastAPI dependency
- `FeatureFlagManager` via `request.app.state.ff_manager`

### 13. Foutafhandeling

- Standaard HTTP exceptions (401, 403, 404) bij missende of ongeldige autorisaties.

### 14. Transacties en dataïntegriteit

- Transacties worden beheerd via FastAPI `get_db` generator (commit op succes, rollback op exception).

### 15. Telemetry / logging / tracing

- `logger.info` logt succesvolle admin toggles inclusief admin_user id en target tenant id (ASCII-only).

### 16. Caching

- Gecached: Ja (via Redis)
- Cache-sleutel: `feature_flags:{tenant_id}:{feature_name}`
- TTL: 600 seconden
- Invalidatie: Direct bij admin toggle actie.

### 17. Acceptatiecriteria

- [OK] Admin toggle endpoint schrijft correct naar Postgres `feature_flags` tabel.
- [OK] RLS policy verbergt data van andere tenants bij query via een onbevoorrechte rol.
- [OK] Depends(get_db) lekt geen database connecties.

### 18. Integratoruitleg

- Gebruik `GET /api/tenant/features` om alle geactiveerde features voor de ingelogde tenant op te vragen.
- Beheerders gebruiken `POST /api/admin/features/{feature}/toggle?target_tenant_id={id}` om features in/uit te schakelen.

### 19. Trainingssamenvatting

- Actor: Systeembeheerder
- Voorwaarde: Ingelogd als admin
- Actie (request): `POST /api/admin/features/memory_mcp/toggle?target_tenant_id=101` met `{"enabled": true}`
- Systeemverwerking: Update feature_flags tabel, wis cache.
- Succesrespons: `200 OK` met status `success=True`.
- Foutrespons: `403 Forbidden` (indien geen admin) of `400 Bad Request` (ongeldige feature).
- Uitzonderingen: Database onbereikbaar (`500`).

---

## [BE-SEC-017] Feature Flags RLS Isolation

### 1. Type

Security Control

### 2. Locatie

- Bestandspad: `tests/integration/security/test_feature_flag_security.py`
- Klasse / functie: `test_feature_flag_rls_isolation`

### 3. Gerelateerde flow

BE-FLW-002

### 4. Doel

Verifiëren dat Row-Level Security cross-tenant lekken betrouwbaar voorkomt.

### 5. Functionele beschrijving

Dit is een penetratietest die garandeert dat tenant A onder geen beding records van tenant B kan inzien of wijzigen.

### 6. Technische beschrijving

Omdat de superuser databaseverbinding in tests RLS standaard omzeilt, creëert de test tijdelijk een unprivileged rol (`rls_ff_tester`) in Postgres, past SELECT-rechten toe, schakelt over naar de rol, stelt de `app.current_tenant` GUC in, en valideert dat alleen records behorende bij die tenant worden teruggegeven.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Database superuser (om de testrol te maken/droppen)
- Vereiste rol / scope: N.v.t.
- Tenant-isolatie: N.v.t.
- Feature flag: N.v.t.

### 8. Request-specificatie

N.v.t. (interne database query)

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- De testrol `rls_ff_tester` mag na de testrun geen residu achterlaten (correct gereset via `RESET ROLE` en `RESET app.current_tenant`).

### 11. Business rules

- Fail-secure: Indien geen tenant context is geconfigureerd, moet de query 0 records retourneren.

### 12. Afhankelijkheden

- `postgres_session` fixture.

### 13. Foutafhandeling

- Eventuele DDL-fouten worden in de `finally` block afgevangen om te voorkomen dat de database verbinding in een ongeldige staat achterblijft.

### 14. Transacties en dataïntegriteit

- Draait binnen een geïsoleerde testtransactie die aan het einde wordt teruggerold.

### 15. Telemetry / logging / tracing

- N.v.t.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [OK] Query onder tenant 101 geeft exact 1 record terug (tenant 101).
- [OK] Query onder tenant 102 geeft exact 1 record terug (tenant 102).
- [OK] Query zonder tenant context geeft 0 records terug.

### 18. Integratoruitleg

N.v.t.

### 19. Trainingssamenvatting

- Actor: Test Suite
- Voorwaarde: Postgres test-instance is actief
- Actie (request): Draai `pytest tests/integration/security/test_feature_flag_security.py`
- Systeemverwerking: Bootstrap RLS, switch role, query database.
- Succesrespons: Test slaagt.
- Foutrespons: Assertiefout bij onjuiste filtering.
- Uitzonderingen: Geen.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Om te controleren of een specifieke feature is toegestaan voor de huidige tenant, stuur een `GET` request naar `/api/tenant/features/{feature}/check`.
- De respons bevat `enabled` (boolean) en eventueel `upgrade_url` indien de feature niet beschikbaar is onder de huidige tier.

---

## Open aannames

- Er wordt aangenomen dat de `app.current_tenant` parameter correct wordt gevuld door de `TenantMiddleware` bij elk HTTP request.

## Open vragen

Geen.

## Risico's

- Indien de database-migratie mislukt of wordt teruggedraaid, kan de applicatie crashen bij pogingen om feature flags te laden. Dit risico wordt geminimaliseerd door fallback cache-bypass logica in `FeatureFlagManager`.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [x] Dataïntegriteit en transacties getest
- [ ] Performance / load getest (indien relevant)
- [ ] Caching getest (indien van toepassing)
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
