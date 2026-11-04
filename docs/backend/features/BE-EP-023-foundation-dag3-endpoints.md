# Backend Feature Specification

## Metadata

- **Feature ID:** BE-EP-023
- **Feature naam:** Foundation Portal Dag 3 Endpoints (Magic Link, Settings, Takedown, Newsletter)
- **Status:** FINAL
- **Auteur:** ADR-029 Dag 3
- **Reviewer:** Independent Senior Python/FastAPI + Security Engineer
- **Datum:** 2026-08-25
- **Gerelateerde user story / ticket:** ADR-029 -- Foundation Portal white-label portal voor Stichting Ketikotivlaardingen.NL
- **Gerelateerde router / module:** `src.core.api.v1.foundation.auth`, `src.core.api.v1.foundation.settings`, `src.core.api.v1.foundation.takedown`, `src.core.api.v1.foundation.newsletter`
- **Gerelateerde frontend endpoints:** `FoundationApiClient` -- `requestMagicLink()`, `verifyMagicLink()`, `getSettings()`, `submitTakedown()`, `subscribeNewsletter()`, `unsubscribeNewsletter()`
- **Gerelateerde database tabellen:** `magic_link_tokens`, `foundation_portal_settings`, `takedown_requests`, `newsletter_subscriptions`, `portal_users`, `tenants`
- **Versie:** 1.1
- **Auteur:** ADR-029 Dag 3
- **Reviewer:** TBD
- **Datum:** 2026-08-25
- **Gerelateerde user story / ticket:** ADR-029 -- Foundation Portal white-label portal voor Stichting Ketikotivlaardingen.NL
- **Gerelateerde router / module:** `src.core.api.v1.foundation.auth`, `src.core.api.v1.foundation.settings`, `src.core.api.v1.foundation.takedown`, `src.core.api.v1.foundation.newsletter`
- **Gerelateerde frontend endpoints:** `FoundationApiClient` -- `requestMagicLink()`, `verifyMagicLink()`, `getSettings()`, `submitTakedown()`, `subscribeNewsletter()`, `unsubscribeNewsletter()`
- **Gerelateerde database tabellen:** `magic_link_tokens`, `foundation_portal_settings`, `takedown_requests`, `newsletter_subscriptions`, `portal_users`, `tenants`
- **Versie:** 1.0

---

## Doel en scope

### Doel

Exposeren van vier nieuwe endpoint-groepen voor het Foundation Portal: magic-link authenticatie (passwordless), publieke portal settings (white-label), content takedown (NTD), en newsletter inschrijving.

### In scope

- `POST /{tenantSlug}/foundation/auth/magic-link` -- magic link aanvragen (publiek)
- `POST /{tenantSlug}/foundation/auth/magic-link/verify` -- magic link verifiëren (publiek)
- `POST /{tenantSlug}/foundation/auth/logout` -- logout (publiek, stateless)
- `GET /{tenantSlug}/foundation/settings` -- portal branding/settings (publiek)
- `POST /{tenantSlug}/foundation/takedown` -- takedown request (JWT)
- `POST /{tenantSlug}/foundation/newsletter/subscribe` -- inschrijven (publiek)
- `POST /{tenantSlug}/foundation/newsletter/unsubscribe` -- uitschrijven (publiek)
- Bijbehorende Pydantic request/response schemas
- Tenant resolutie via `public_tenant_scope()`
- Public endpoint registry updates

### Out of scope

- Echte e-mail verzending (NotificationService mock in test)
- Admin takedown review interface
- Newsletter verzending (Brevo integratie)
- Geo/map endpoints (BE-EP-029-002)
- Content moderatie endpoints (curatie queue -- BE-EP-022)

---

## Build summary

- **Nieuw gebouwd:**
  - `src/core/api/v1/foundation/auth.py` -- Magic link auth endpoints
  - `src/core/api/v1/foundation/settings.py` -- Portal settings endpoint
  - `src/core/api/v1/foundation/takedown.py` -- Takedown endpoint
  - `src/core/api/v1/foundation/newsletter.py` -- Newsletter endpoints
  - `src/core/api/v1/foundation/router.py` -- Bijgewerkt met nieuwe routers
  - `src/core/api/v1/foundation/schemas.py` -- Nieuwe Pydantic schemas
- **Gewijzigd:**
  - `src/core/shared/public_registry.py` -- Public paths uitgebreid
  - `tests/integration/api/v1/foundation/conftest.py` -- `portal_settings` fixture
- **Verwijderd:** N.v.t.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-023-001 | Magic Link Auth | Endpoint set | `src/core/api/v1/foundation/auth.py` | Nieuw | BE-FLW-029-004 |
| BE-EP-023-002 | Portal Settings | Endpoint | `src/core/api/v1/foundation/settings.py` | Nieuw | BE-FLW-029-005 |
| BE-EP-023-003 | Takedown | Endpoint | `src/core/api/v1/foundation/takedown.py` | Nieuw | BE-FLW-029-006 |
| BE-EP-023-004 | Newsletter | Endpoint set | `src/core/api/v1/foundation/newsletter.py` | Nieuw | BE-FLW-029-007 |
| BE-SCH-023-001 | MagicLinkRequest | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-004 |
| BE-SCH-023-002 | PortalSettingsResponse | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-005 |
| BE-SCH-023-003 | TakedownCreateRequest | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-006 |
| BE-SCH-023-005 | NewsletterUnsubscribeRequest | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-007 |
| BE-SCH-023-006 | NewsletterResponse | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-007 |

---

## API-flows

### Flow ID: BE-FLW-029-004 -- Magic Link Auth

- **Naam:** Passwordless login via magic link
- **Trigger:** `POST /{tenantSlug}/foundation/auth/magic-link`
- **Voorwaarden:** Geldig e-mailadres, tenant actief
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> DB INSERT token -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()`
  2. Zoek `PortalUser` bij e-mail (stilzwijgend, geen reveal)
  3. Genereer cryptografische token (`secrets.token_urlsafe(32)`)
  4. Sla SHA-256 hash op in `magic_link_tokens` (15 min expiry)
  5. Stuur e-mail via NotificationService (`best_effort` wrapper)
  6. Retourneer generieke message (geen enumeratie)
- **DB-operaties:** INSERT INTO `magic_link_tokens`
- **Successtatus + response:** 202 Accepted + generieke message
- **Foutpaden:** 404 (tenant), 429 (rate limit)

### Flow ID: BE-FLW-029-005 -- Portal Settings

- **Naam:** Publieke portal branding ophalen
- **Trigger:** `GET /{tenantSlug}/foundation/settings`
- **Voorwaarden:** Publiek (geen auth), tenant actief
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> DB SELECT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()`
  2. SELECT `FoundationPortalSettings` WHERE `tenant_id = ?`
  3. Retourneer settings als JSON
- **DB-operaties:** SELECT FROM `foundation_portal_settings`
- **Successtatus + response:** 200 OK + `PortalSettingsResponse`
- **Foutpaden:** 404 (tenant of settings niet gevonden)

### Flow ID: BE-FLW-029-006 -- Takedown Request

- **Naam:** Content takedown indienen
- **Trigger:** `POST /{tenantSlug}/foundation/takedown`
- **Voorwaarden:** Geldig JWT bearer token, tenant actief, content bestaat
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> `require_portal_user` -> DB INSERT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()`
  2. Valideer JWT via `require_portal_user`
  3. Pydantic validatie van request body
  4. Verifieer content bestaat in tenant
  5. INSERT `TakedownRequest` met status PENDING
  6. Notificatie naar admin via `best_effort`
- **DB-operaties:** INSERT INTO `takedown_requests`
- **Successtatus + response:** 201 Created + `TakedownResponse`
- **Foutpaden:** 401 (auth), 403 (cross-tenant), 404 (content), 422 (validatie)

### Flow ID: BE-FLW-029-007 -- Newsletter Subscribe/Unsubscribe

- **Naam:** Newsletter inschrijving/uitschrijving
- **Trigger:** `POST /{tenantSlug}/foundation/newsletter/subscribe` of `/unsubscribe`
- **Voorwaarden:** Publiek (geen auth), tenant actief
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> DB UPSERT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()`
  2. Pydantic validatie van e-mail
  3. Subscribe: INSERT of UPDATE `newsletter_subscriptions` status SUBSCRIBED
  4. Unsubscribe: UPDATE status UNSUBSCRIBED
  5. Retourneer generieke message
- **DB-operaties:** INSERT/UPDATE `newsletter_subscriptions`
- **Successtatus + response:** 201 Created (subscribe) of 200 OK (unsubscribe) + generieke message
- **Foutpaden:** 404 (tenant), 422 (validatie)

---

## Detaildocumentatie per artefact

---

## [BE-EP-023-001] Magic Link Auth Endpoints

### 1. Type

Endpoint set / Laag-1 sub-router (ADR-033)

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/auth.py`
- **Klasse / functie:** `router = APIRouter(prefix="/auth")`

### 3. Gerelateerde flow

BE-FLW-029-004

### 4. Doel

Passwordless authenticatie voor portal gebruikers via cryptografische magic links.

### 5. Functionele beschrijving

Bezoekers kunnen een magic link aanvragen via hun e-mailadres. Als het e-mailadres bekend is, wordt een token gegenereerd en per e-mail verstuurd. De token kan worden geverifieerd om een JWT access token te verkrijgen.

### 6. Technische beschrijving

- **Token generatie:** `secrets.token_urlsafe(32)` (32 bytes, URL-safe base64)
- **Token hashing:** SHA-256 voor veilige opslag
- **Token expiry:** 15 minuten
- **Replay protection:** `used_at` timestamp; tweede verificatie geeft 410 Gone
- **Sentinel pattern:** Voor niet-bestaande e-mails wordt GEEN token opgeslagen (FK constraint voorkomt sentinel values); generieke response retourneert toch
- **JWT:** `aud: "portal"` claim verplicht

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** Nee (publiek)
- **Rate limit:** Magic-link request 5/min IP; 3/uur per e-mail

### 8. Request-specificatie

#### POST /{tenantSlug}/foundation/auth/magic-link

- **Request body:** `MagicLinkRequest`
  - `email`: str (min 3, max 255)
- **Response:** `MagicLinkResponse` -- generieke message

#### POST /{tenantSlug}/foundation/auth/magic-link/verify

- **Request body:** `MagicLinkVerifyRequest`
  - `token`: str (min 1)
- **Response:** `TokenResponse`
  - `access_token`: str
  - `token_type`: "bearer"

#### POST /{tenantSlug}/foundation/auth/logout

- **Request body:** Geen
- **Response:** 204 No Content (stateless JWT)

### 9. Validaties en constraints

- Token verloopt na 15 minuten
- Token kan slechts eenmaal worden gebruikt
- Geblokkeerde users krijgen 403

---

## [BE-EP-023-002] Portal Settings Endpoint

### 1. Type

Endpoint / Laag-1 sub-router

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/settings.py`

### 3. Doel

Publieke white-label branding ophalen per tenant.

### 4. Functionele beschrijving

Bezoekers kunnen de naam, kleuren, logo, en contactinformatie van een portal ophalen zonder in te loggen.

### 5. Technische beschrijving

- Data uit `FoundationPortalSettings` model
- Tenant-scoped via `public_tenant_scope()`
- Rate limit: 60/min per IP

---

## [BE-EP-023-003] Takedown Endpoint

### 1. Type

Endpoint / Laag-1 sub-router

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/takedown.py`

### 3. Doel

NTD (Notice-and-Takedown) requests indienen voor content.

### 4. Functionele beschrijving

Geauthenticeerde portal users kunnen een takedown request indienen voor specifieke content. De request wordt opgeslagen met status PENDING en een notificatie wordt naar admins gestuurd.

### 5. Technische beschrijving

- Vereist `require_portal_user` (JWT)
- Cross-tenant geblokkeerd
- `best_effort` notificatie naar admin
- Rate limit: 5/uur per IP

---

## [BE-EP-023-004] Newsletter Endpoints

### 1. Type

Endpoint set / Laag-1 sub-router

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/newsletter.py`

### 3. Doel

Double opt-in newsletter inschrijving per tenant.

### 4. Functionele beschrijving

Bezoekers kunnen zich inschrijven of uitschrijven voor een tenant-specifieke newsletter. E-mail enumeratie wordt voorkomen door generieke messages.

### 5. Technische beschrijving

- Subscribe genereert unsubscribe token hash (SHA-256)
- Status enum: `SUBSCRIBED`, `UNSUBSCRIBED`
- Generieke responses (geen enumeratie)
- Rate limit: 3/uur per IP

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
- [x] Review door reviewer-prompt: **APPROVED WITH MINOR GAPS** (see `docs/backend/review/review-BE-EP-023.md`)
- [x] Tests: 67/67 integratietests PASS (65 bestaand + 2 nieuw na review fixes)
- [x] Review fixes doorgevoerd: rate limiters, schema bug, race condition, JWT scope, unsubscribe token
- [x] ruff: 0 errors
- [x] mypy: 0 nieuwe errors
- [x] pyright: 0 errors
