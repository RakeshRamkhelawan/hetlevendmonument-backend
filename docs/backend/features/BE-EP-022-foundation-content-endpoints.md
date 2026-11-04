# Backend Feature Specification

## Metadata

- **Feature ID:** BE-EP-022
- **Feature naam:** Foundation Portal Content Endpoints
- **Status:** DRAFT
- **Auteur:** ADR-029 Dag 2
- **Reviewer:** TBD
- **Datum:** 2026-08-24
- **Gerelateerde user story / ticket:** ADR-029 -- Foundation Portal white-label portal voor Stichting Ketikotivlaardingen.NL
- **Gerelateerde router / module:** `src.core.api.v1.foundation.content`
- **Gerelateerde frontend endpoints:** `FoundationApiClient` -- `getContent()`, `getContentById()`, `uploadContent()`
- **Gerelateerde database tabellen:** `foundation_content`, `content_tags`, `portal_users`, `tenants`
- **Versie:** 1.0

---

## Doel en scope

### Doel

Exposeren van publieke content-endpoints voor het Foundation Portal zodat bezoekers goedgekeurde content kunnen browsen, bekijken en uploaden, met strikte tenant-isolatie via URL-path slug resolutie en RLS.

### In scope

- `GET /api/v1/{tenantSlug}/foundation/content` -- lijst goedgekeurde content (publiek)
- `GET /api/v1/{tenantSlug}/foundation/content/{content_id}` -- detail van een content item (publiek)
- `POST /api/v1/{tenantSlug}/foundation/content` -- nieuwe content uploaden (JWT)
- Bijbehorende Pydantic request/response schemas
- Tenant resolutie via `public_tenant_scope()`
- Rate limiting op alle drie endpoints

### Out of scope

- Content moderatie endpoints (curatie queue -- BE-EP-029-010)
- Geo/map endpoints (BE-EP-029-002)
- Magic-link auth (BE-EP-029-003)
- File-upload mechanisme (binaire bestanden) -- huidige implementatie is JSON-only en verwijst naar media uitsluitend via `external_url`; opslag-backend (S3/MinIO/lokaal pad) is voor een toekomstige file-upload endpoint out of scope
- AI tagging pipeline -- wordt async verwerkt na upload
- OAI-PMH metadata harvest (BE-EP-029-009)
- Admin endpoints (BE-EP-029-010 t/m 012)

---

## Build summary

- **Nieuw gebouwd:**
  - `src/core/api/v1/foundation/__init__.py`
  - `src/core/api/v1/foundation/router.py` -- Laag-3 composite router (ADR-033)
  - `src/core/api/v1/foundation/content.py` -- Laag-1 sub-router met 3 endpoints
  - `src/core/api/v1/foundation/schemas.py` -- Pydantic v2 schemas
  - `src/core/api/v1/foundation/dependencies.py` -- `require_portal_user`
  - `src/core/api/registries/foundation.py` -- Router registry
  - OAuth2 portal scopes in `src/core/auth/scopes.py`
- **Gewijzigd:**
  - `src/core/api/router_registry.py` -- foundation registry includen
  - `src/core/auth/scopes.py` -- PORTAL_READ, PORTAL_UPLOAD toevoegen
- **Verwijderd:** N.v.t.
- **Beinvloede bestaande flows:** Geen breaking changes; nieuwe router onder `/api/v1/{tenantSlug}/foundation`

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-022 | Foundation Content Endpoints | Endpoint set | `src/core/api/v1/foundation/content.py` | Nieuw | BE-FLW-029-001, BE-FLW-029-002 |
| BE-RTR-029-001 | Foundation Router Registry | Router | `src/core/api/registries/foundation.py` | Nieuw | -- |
| BE-SCH-029-001 | FoundationContentCreateRequest | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-001 |
| BE-SCH-029-002 | FoundationContentListResponse | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-002 |
| BE-SCH-029-003 | FoundationContentDetailResponse | Pydantic schema | `src/core/api/v1/foundation/schemas.py` | Nieuw | BE-FLW-029-002 |
| BE-DEP-029-001 | require_portal_user | FastAPI Depends | `src/core/api/v1/foundation/dependencies.py` | Nieuw | BE-FLW-029-001 |
| BE-SEC-029-001 | Portal OAuth2 scopes | Security | `src/core/auth/scopes.py` | Wijziging | -- |

---

## API-flows

### Flow ID: BE-FLW-029-001 -- Content uploaden

- **Naam:** Gebruiker uploadt nieuwe content naar het portal
- **Trigger:** `POST /api/v1/{tenantSlug}/foundation/content`
- **Voorwaarden:** Geldig JWT bearer token (portal auth), tenant actief
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> `require_portal_user` -> DB INSERT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()` -- zet ContextVar tenant_id
  2. Valideer JWT via `require_portal_user` -- extract `aud: "portal"` claim
  3. Pydantic validatie van request body (`FoundationContentCreateRequest`)
  4. Creeer `FoundationContent` ORM object met `status = ContentStatus.PENDING`
  5. Sla op in DB via `db.add()` + `await db.commit()`
  6. Schrijf audit log via `best_effort()` wrapper
- **DB-operaties:** INSERT INTO `foundation_content`
- **Successtatus + response:** 201 Created + `FoundationContentDetailResponse`
- **Foutpaden:**
  - 401: Ontbrekende of ongeldige JWT
  - 403: Tenant mismatch tussen JWT en URL slug
  - 404: Tenant slug onbekend of inactief
  - 422: Pydantic validatiefout
  - 429: Rate limit overschreden
  - 500: DB fout
- **Eindtoestand:** `foundation_content` row met `status = pending`; curatie queue wacht op goedkeuring

### Flow ID: BE-FLW-029-002 -- Content ophalen (lijst)

- **Naam:** Publieke lijst van goedgekeurde content bekijken
- **Trigger:** `GET /api/v1/{tenantSlug}/foundation/content`
- **Voorwaarden:** Publiek (geen auth), tenant actief
- **Request-pad:** Client -> Traefik -> FastAPI -> `public_tenant_scope()` -> DB SELECT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()` -- zet ContextVar tenant_id
  2. Bouw SQLAlchemy query: `select(FoundationContent).where(status == APPROVED)`
  3. Pas optionele filters toe (`category`, `type`, `q` full-text search)
  4. Voer COUNT(*) uit voor total
  5. Voer paginated query uit (LIMIT/OFFSET)
  6. Serialiseer resultaten via Pydantic
- **DB-operaties:** SELECT COUNT(*) + SELECT FROM `foundation_content`
- **Successtatus + response:** 200 OK + `FoundationContentListResponse`
- **Foutpaden:**
  - 404: Tenant slug onbekend of inactief
  - 429: Rate limit overschreden (60/min per IP)
  - 500: DB fout
- **Eindtoestand:** Geen DB wijzigingen (read-only)

### Flow ID: BE-FLW-029-003 -- Content detail ophalen

- **Naam:** Detail van een specifiek content item bekijken
- **Trigger:** `GET /api/v1/{tenantSlug}/foundation/content/{content_id}`
- **Voorwaarden:** Publiek (geen auth), tenant actief
- **Request-pad:** Client -> TraAPI -> `public_tenant_scope()` -> DB SELECT -> response
- **Service-stappen:**
  1. Valideer `tenantSlug` via `public_tenant_scope()`
  2. Zoek content by ID + tenant_id (RLS WHERE hook filtert automatisch)
  3. Check dat `status == APPROVED` (of `privacy == PUBLIC`)
  4. Eager load `tags` relatie via `selectinload`
  5. Serialiseer naar `FoundationContentDetailResponse`
- **DB-operaties:** SELECT FROM `foundation_content` + JOIN `content_tags`
- **Successtatus + response:** 200 OK + `FoundationContentDetailResponse`
- **Foutpaden:**
  - 404: Content niet gevonden OF niet approved OF verkeerde tenant
  - 429: Rate limit overschreden
  - 500: DB fout
- **Eindtoestand:** Geen DB wijzigingen (read-only)

---

## Detaildocumentatie per artefact

---

## [BE-EP-022] Foundation Content Endpoints

### 1. Type

Endpoint set / Laag-1 sub-router (ADR-033)

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/content.py`
- **Klasse / functie:** `router = APIRouter()`

### 3. Gerelateerde flow

BE-FLW-029-001, BE-FLW-029-002, BE-FLW-029-003

### 4. Doel

Exposeren van de eerste drie Foundation Portal content-endpoints: publieke lijst, publiek detail, en geauthenticeerde upload.

### 5. Functionele beschrijving

Bezoekers van een Foundation Portal (bijv. Ketikotivlaardingen.NL) kunnen:
1. Goedgekeurde content browsen via een gepagineerde lijst met filters
2. Detailinformatie van een specifiek verhaal, kunstwerk, audiofragment, etc. bekijken
3. Ingelogde gebruikers kunnen nieuwe content uploaden (gaat naar pending voor curatie)

Content die nog niet approved is, is niet zichtbaar voor publieke bezoekers.

### 6. Technische beschrijving

- **Router structuur:** Laag-3 composite (`src/core/api/v1/foundation/router.py`) includet deze Laag-1 router met `prefix="/content"`
- **Tenant resolutie:** `public_tenant_scope(tenantSlug, db)` context manager zet `tenant_id` ContextVar; ORM `do_orm_execute` hook (ADR-004) voegt auto-WHERE `tenant_id = ?` toe aan alle queries
- **RLS policies:** `foundation_content` en `content_tags` hebben RLS policies; `portal_users` heeft RLS
- **Dataflow:**
  - List/detail: Request -> slug validatie -> ContextVar set -> SQLAlchemy query -> RLS filter -> response
  - Upload: Request -> slug validatie -> JWT validatie -> Pydantic validatie -> DB insert -> audit log -> response
- **JSONB:** `metadata_` veld (JSONB) wordt opgeslagen als-is; geen `flag_modified()` nodig bij insert
- **File handling:** De huidige implementatie heeft GEEN file-upload mechanisme. `POST /content` accepteert uitsluitend een JSON request body (`FoundationContentCreateRequest`); media wordt uitsluitend via het `external_url` tekstveld gerefereerd (link naar extern gehoste content). De velden `file_url`, `file_mime`, `file_size_bytes` bestaan in het model/response-schema maar worden door deze endpoint nooit gezet en blijven `NULL`.

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:**
  - GET list: Nee (publiek)
  - GET detail: Nee (publiek)
  - POST upload: Ja (JWT bearer token met `aud: "portal"`)
- **Vereiste rol / scope:**
  - GET list: Geen
  - GET detail: Geen
  - POST upload: `portal:upload` scope (of `portal:read` fallback voor backwards compat)
- **Tenant-isolatie:** Ja, via `public_tenant_scope()` ContextVar + ORM hook + RLS policies
- **Feature flag:** N.v.t.

### 8. Request-specificatie per endpoint

#### GET /api/v1/{tenantSlug}/foundation/content

- **Methode:** GET
- **Route:** `/api/v1/{tenantSlug}/foundation/content`
- **Path parameters:**
  - `tenantSlug`: str (validatie via `validate_foundation_slug()`)
- **Query parameters:**
  - `category`: str | None -- filter op `FoundationContent.category`
  - `type`: str | None -- filter op `FoundationContent.type` (story, artwork, audio, document, poetry, link)
  - `q`: str | None -- full-text search op `title_nl`, `title_en`, `description_nl`, `description_en`, `body_nl`, `body_en`
  - `page`: int = 1 (ge >= 1)
  - `page_size`: int = 20 (ge = 1, le = 100)
- **Request body:** Geen
- **Verplichte headers:** Geen (publiek)
- **Rate limit:** 60 requests per minuut, IP-gekeyd (`portal_public_read_limit`)

#### GET /api/v1/{tenantSlug}/foundation/content/{content_id}

- **Methode:** GET
- **Route:** `/api/v1/{tenantSlug}/foundation/content/{content_id}`
- **Path parameters:**
  - `tenantSlug`: str
  - `content_id`: int (ge >= 1)
- **Query parameters:** Geen
- **Request body:** Geen
- **Verplichte headers:** Geen (publiek)
- **Rate limit:** 60 requests per minuut, IP-gekeyd (`portal_public_read_limit`)

#### POST /api/v1/{tenantSlug}/foundation/content

- **Methode:** POST
- **Route:** `/api/v1/{tenantSlug}/foundation/content`
- **Path parameters:**
  - `tenantSlug`: str
- **Query parameters:** Geen
- **Request body (schema):** `FoundationContentCreateRequest` (JSON, `Content-Type: application/json`)
  - `type`: str (verplicht) -- enum: story, artwork, audio, document, poetry, link
  - `title_nl`: str (verplicht, max 255)
  - `title_en`: str | None (max 255)
  - `description_nl`: str | None
  - `description_en`: str | None
  - `body_nl`: str | None
  - `body_en`: str | None
  - `creator_name`: str | None (max 255)
  - `is_anonymous`: bool = False
  - `language`: str = "nl" (max 8)
  - `privacy`: str = "public" -- enum: public, community
  - `rights_confirmed`: bool = False
  - `external_url`: str | None (max 1024) -- optionele link naar extern gehoste media; geen file-upload in huidige implementatie
  - `lat`: float | None
  - `lng`: float | None
  - `location_name`: str | None (max 200)
  - `license`: str | None (max 50) -- bijv. "CC-BY", "CC0"
  - `category`: str | None (max 100)
  - `metadata`: dict | None -- JSONB object (schema-veldnaam `metadata`; ORM-attribuut heet `metadata_`)
- **Verplichte headers:** `Authorization: Bearer <portal_jwt>`, `Content-Type: application/json`
- **Rate limit:** 10 requests per minuut, IP-gekeyd (`portal_public_write_limit`)

### 9. Response-specificatie

#### GET /api/v1/{tenantSlug}/foundation/content

- **Successtatus:** 200 OK
- **Response schema:** `FoundationContentListResponse`
  - `success`: bool = True
  - `data`: list[`FoundationContentListItem`]
    - `id`: int
    - `type`: str
    - `title_nl`: str
    - `title_en`: str | None
    - `description_nl`: str | None
    - `creator_name`: str | None
    - `is_anonymous`: bool
    - `language`: str
    - `privacy`: str
    - `status`: str
    - `file_url`: str | None
    - `external_url`: str | None
    - `lat`: float | None
    - `lng`: float | None
    - `location_name`: str | None
    - `license`: str | None
    - `category`: str | None
    - `created_at`: str (ISO 8601)
    - `tags`: list[`TagResponse`]
      - `tag_type`: str
      - `value`: str
  - `total`: int
  - `page`: int
  - `page_size`: int
  - `pages`: int
- **Foutstatussen:** 404, 429, 500

#### GET /api/v1/{tenantSlug}/foundation/content/{content_id}

- **Successtatus:** 200 OK
- **Response schema:** `FoundationContentDetailResponse`
  - `success`: bool = True
  - `data`: `FoundationContentDetailItem`
    - Alle velden van `FoundationContentListItem` PLUS:
    - `description_en`: str | None
    - `body_nl`: str | None
    - `body_en`: str | None
    - `file_mime`: str | None
    - `file_size_bytes`: int | None
    - `ai_tagging_failed`: bool
    - `moderation_score`: float | None
    - `metadata_`: dict | None
    - `uploader_id`: int | None
    - `updated_at`: str (ISO 8601)
- **Foutstatussen:** 404, 429, 500

#### POST /api/v1/{tenantSlug}/foundation/content

- **Successtatus:** 201 Created
- **Response schema:** `FoundationContentDetailResponse` (zelfde als GET detail)
- **Foutstatussen:** 400, 401, 403, 404, 422, 429, 500

### 10. Validaties en constraints

- `tenantSlug`: moet voldoen aan `validate_foundation_slug()` -- geen reserved slugs, alleen alfanumeriek + hyphen
- `content_id`: int >= 1
- `type`: enum-waarde uit ContentType
- `title_nl`: verplicht, max 255 tekens
- `rights_confirmed`: default `False`; er is in de huidige implementatie geen server-side validator die `True` afdwingt (geen `@model_validator` in `FoundationContentCreateRequest`)
- `external_url`: optioneel; geen server-side validatie dat minstens een vorm van media/link aanwezig moet zijn -- er is geen file-upload mechanisme in deze endpoint
- `lat`: -90.0 tot 90.0
- `lng`: -180.0 tot 180.0
- `page_size`: 1 tot 100
- `license`: max 50 tekens, optioneel

### 11. Business rules

- Alleen content met `status = APPROVED` is zichtbaar in publieke lijst/detail endpoints
- Upload zet `status` automatisch op `PENDING` (curatie workflow)
- `is_anonymous = True` verbergt `creator_name` en `uploader_id` in publieke responses
- `privacy = COMMUNITY` content is alleen zichtbaar voor ingelogde portal users
- Er is geen file-upload mechanisme in de huidige implementatie; `file_url`, `file_mime`, `file_size_bytes` blijven altijd `NULL` na een upload via deze endpoint
- Media kan optioneel gerefereerd worden via `external_url` (link naar extern gehoste content)

### 12. Afhankelijkheden

- `src.core.services.foundation_tenant_resolver.public_tenant_scope`
- `src.core.middleware.tenant_context.set_tenant_id / clear_tenant_context`
- `src.core.database.database.get_db`
- `src.core.models.foundation_content.FoundationContent, ContentType, ContentStatus, Privacy`
- `src.core.governance.rate_limiter.portal_public_read_limit, portal_public_write_limit`
- `src.core.utils.best_effort.best_effort`
- `src.core.auth.jwt_handler.decode_token` (voor portal JWT)
- `src.core.database.tenant_query_filter.TenantFilterBypass` (voor tenant resolutie query)

### 13. Foutafhandeling

- **400 Bad Request:** Niet gebruikt door deze endpoint (geen file-upload validatie in huidige implementatie)
- **401 Unauthorized:** Ontbrekende of ongeldige JWT bij upload endpoint
- **403 Forbidden:** Tenant mismatch (JWT claim != URL slug); user is_blocked
- **404 Not Found:** Tenant slug onbekend/inactief; content_id bestaat niet of is niet approved
- **409 Conflict:** Niet gebruikt
- **422 Unprocessable Entity:** Pydantic validatiefout (ontbrekende velden, te lang, ongeldige enum)
- **429 Too Many Requests:** Rate limit overschreden (60/min publiek, 10/min upload)
- **500 Internal Server Error:** DB fout, onverwachte exception
- **503 Service Unavailable:** Niet gebruikt

### 14. Transacties en data-integriteit

- Upload endpoint: enkele `await db.commit()` voor INSERT; bij faal `await db.rollback()`
- `best_effort()` wrapper voor audit logging: faalt nooit de hoofdtransactie
- `public_tenant_scope()` garandeert ContextVar cleanup in `finally` block (geen tenant leakage naar volgende request)
- Magic link verify (bij auth flow): `used_at` update in ZELFDE transactie als JWT creatie

### 15. Telemetry / logging / tracing

- Content list: INFO log met tenant_id, filters, result count
- Content detail: INFO log met tenant_id, content_id
- Content upload: INFO log met tenant_id, uploader_id, content_type, title
- Rate limit hits: WARNING log met key en IP
- Errors: ERROR log met exception type, traceback, tenantSlug
- OpenTelemetry spans: `foundation.content.list`, `foundation.content.detail`, `foundation.content.upload`

### 16. Caching

- **Gecached:** Nee
- Geen caching-laag op deze endpoints (MVP); CDN (CloudFlare) kan publieke GETs cachen op edge

### 17. Acceptatiecriteria

- [ ] Publieke lijst toont alleen approved content
- [ ] Publieke lijst is filterbaar op category en type
- [ ] Publieke lijst is doorzoekbaar met `q` parameter
- [ ] Publieke detail toont alle velden inclusief tags
- [ ] Upload endpoint vereist geldig JWT
- [ ] Upload zet status automatisch op pending
- [ ] Upload valideert `rights_confirmed = True`
- [ ] Upload accepteert `external_url` als optionele link naar media (geen file-upload mechanisme in huidige implementatie)
- [ ] Tenant A kan nooit content van tenant B zien (cross-tenant test)
- [ ] Onbekende tenantSlug geeft 404
- [ ] Onbekend content_id geeft 404
- [ ] Rate limiting activeert na 60 publieke requests/min
- [ ] Rate limiting activeert na 10 upload requests/min
- [ ] Anonymous content verbergt creator_name in response
- [ ] Community privacy content alleen zichtbaar voor ingelogde users
- [ ] Audit log wordt geschreven bij upload
- [ ] ContextVar tenant_id wordt altijd opgeruimd (geen leakage)

### 18. Integratoruitleg

- **Content lijst ophalen:** `GET /api/v1/{tenantSlug}/foundation/content?page=1&page_size=20&category=verhalen`
- **Content detail:** `GET /api/v1/{tenantSlug}/foundation/content/123`
- **Content uploaden:** `POST /api/v1/{tenantSlug}/foundation/content` met `Authorization: Bearer <token>` header en JSON request body (`Content-Type: application/json`)
- **Response wrapper:** Alle responses volgen het patroon `{"success": true, "data": {...}}`
- **Paginering:** Gebruik `page` en `page_size` query params; `total` en `pages` in response

### 19. Trainingssamenvatting

- **Actor:** Publieke bezoeker (list/detail) of ingelogde portal gebruiker (upload)
- **Voorwaarde:** Voor upload: JWT token geldig met `aud: "portal"`; tenant slug bestaat en is actief
- **Actie (request):** GET lijst/detail zonder auth; POST upload met Bearer token
- **Systeemverwerking:** Tenant resolutie -> RLS filtering -> DB query/insert -> audit log
- **Succesrespons:** 200 OK (list/detail) of 201 Created (upload) met content data
- **Foutrespons:** 404 (onbekend), 401/403 (auth), 422 (validatie), 429 (rate limit), 500 (server)
- **Uitzonderingen:** Upload vereist `rights_confirmed=True`; anonymous content verbergt uploader info

---

## [BE-RTR-029-001] Foundation Router Registry

### 1. Type

Router / APIRouter-groep (Laag-3 composite)

### 2. Locatie

- **Bestandspad:** `src/core/api/registries/foundation.py`
- **Klasse / functie:** `register(app: FastAPI) -> int`

### 3. Gerelateerde flow

--

### 4. Doel

Registreren van de Foundation Portal router in de centrale router registry.

### 5. Functionele beschrijving

Inclusief de Foundation Portal router in de FastAPI app onder `/api/v1/{tenantSlug}/foundation`.

### 6. Technische beschrijving

```python
def register(app: FastAPI) -> int:
    from src.core.api.v1.foundation.router import router as foundation_router
    app.include_router(foundation_router, prefix="/api/v1")
    return 1
```

### 7. Zichtbaarheids- en toegangsregels

- **Tenant-isolatie:** N.v.t. (router zelf doet geen tenant checks; endpoints gebruiken `public_tenant_scope`)

### 8. Request-specificatie

N.v.t. (registry functie, geen endpoint)

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

N.v.t.

### 11. Business rules

N.v.t.

### 12. Afhankelijkheden

- `src.core.api.v1.foundation.router`

### 13. Foutafhandeling

N.v.t.

### 14. Transacties en data-integriteit

N.v.t.

### 15. Telemetry / logging / tracing

N.v.t.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [ ] Registry registreert exact 1 router
- [ ] Router is bereikbaar op `/api/v1/{tenantSlug}/foundation/*`

### 18. Integratoruitleg

N.v.t.

### 19. Trainingssamenvatting

- **Actor:** FastAPI app factory
- **Voorwaarde:** App wordt opgestart
- **Actie:** `foundation.register(app)` aanroepen
- **Systeemverwerking:** Router inclusie in app
- **Succesrespons:** 1 (aantal geregistreerde routers)
- **Foutrespons:** ImportError als router bestand ontbreekt
- **Uitzonderingen:** N.v.t.

---

## [BE-SCH-029-001] FoundationContentCreateRequest

### 1. Type

Pydantic schema (request)

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/schemas.py`
- **Klasse / functie:** `class FoundationContentCreateRequest(BaseModel)`

### 3. Gerelateerde flow

BE-FLW-029-001

### 4. Doel

Valideren van inkomende content upload requests.

### 5. Functionele beschrijving

Definieert alle velden die een gebruiker kan insturen bij het uploaden van nieuwe content.

### 6. Technische beschrijving

Pydantic v2 model. Velden gebruiken `Field()` voor constraints (min/max length, numerieke bounds).
In de huidige implementatie bevat `FoundationContentCreateRequest` GEEN `@model_validator`; alle velden zijn losse `Field()`-declaraties zonder cross-field validatie. `rights_confirmed` heeft default `False` en wordt niet server-side afgedwongen op `True`. Er is geen `file`-veld; `external_url` is een los, optioneel tekstveld (max 1024 tekens) zonder verplichting.

### 7. Zichtbaarheids- en toegangsregels

N.v.t. (schema)

### 8. Request-specificatie

Zie endpoint POST specificatie hierboven.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `type`: enum-waarde
- `title_nl`: min 1, max 255
- `rights_confirmed`: default False, niet server-side afgedwongen op True (geen validator)
- `external_url`: optioneel, geen verplichting (geen file-veld in huidige implementatie)
- `lat`: -90.0 tot 90.0
- `lng`: -180.0 tot 180.0

### 11. Business rules

- Content zonder rechtenbevestiging wordt geweigerd (422) -- LET OP: in de huidige implementatie is dit nog niet afgedwongen door een `@model_validator`; zie sectie 6
- Er is geen file-veld; `external_url` is optioneel en wordt niet verplicht afgedwongen

### 12. Afhankelijkheden

- Pydantic v2

### 13. Foutafhandeling

N.v.t.

### 14. Transacties en data-integriteit

N.v.t.

### 15. Telemetry / logging / tracing

N.v.t.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [ ] Schema valideert alle verplichte velden
- [ ] Schema weigert content zonder rights_confirmed
- [ ] N.v.t. -- geen `file` veld in huidige implementatie; schema dwingt geen minimum media-referentie af

### 18. Integratoruitleg

N.v.t.

### 19. Trainingssamenvatting

- **Actor:** Portal gebruiker
- **Voorwaarde:** Ingelogd
- **Actie:** POST content met velden
- **Systeemverwerking:** Pydantic validatie
- **Succesrespons:** Validatie OK, door naar endpoint logica
- **Foutrespons:** 422 met detail velden
- **Uitzonderingen:** rights_confirmed moet True zijn

---

## [BE-DEP-029-001] require_portal_user

### 1. Type

FastAPI Depends-functie

### 2. Locatie

- **Bestandspad:** `src/core/api/v1/foundation/dependencies.py`
- **Klasse / functie:** `async def require_portal_user(...)`

### 3. Gerelateerde flow

BE-FLW-029-001

### 4. Doel

Valideren van portal JWT tokens en retourneren van de bijbehorende PortalUser.

### 5. Functionele beschrijving

Extraheert het Bearer token uit de Authorization header, valideert de JWT signature en claims, controleert dat `aud = "portal"`, en retourneert de PortalUser uit de database.

### 6. Technische beschrijving

```python
async def require_portal_user(
    authorization: str = Header(..., alias="Authorization"),
    session: AsyncSession = Depends(get_db),
) -> PortalUser:
    # 1. Extract Bearer token
    # 2. decode_token() met expected_aud="portal"
    # 3. SELECT PortalUser WHERE id = token.sub AND tenant_id = current tenant
    # 4. Check is_blocked == False
    # 5. Return PortalUser
```

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** Ja (portal JWT)
- **Vereiste rol / scope:** Minstens `portal:read`
- **Tenant-isolatie:** Ja, via JWT claim + DB WHERE

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- Token moet `aud: "portal"` bevatten
- User moet bestaan in `portal_users` tabel
- User `is_blocked` moet False zijn

### 11. Business rules

- Geblokkeerde users krijgen 403 ondanks geldig token
- Verkeerd `aud` claim (bijv. RBAC token) geeft 401

### 12. Afhankelijkheden

- `src.core.auth.jwt_handler.decode_token`
- `src.core.database.database.get_db`
- `src.core.models.foundation_content.PortalUser`

### 13. Foutafhandeling

- **401:** Ontbrekende token, ongeldige signature, verlopen token, verkeerd aud claim
- **403:** User is geblokkeerd, tenant mismatch
- **404:** User bestaat niet meer (zeldzaam, na delete)

### 14. Transacties en data-integriteit

N.v.t.

### 15. Telemetry / logging / tracing

- INFO: geslaagde auth met user_id
- WARNING: mislukte auth met reden

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [ ] Valideert geldig portal JWT
- [ ] Weigert RBAC token (verkeerd aud)
- [ ] Weigert geblokkeerde users
- [ ] Retourneert PortalUser object

### 18. Integratoruitleg

- Stuur altijd `Authorization: Bearer <portal_jwt>` bij upload endpoints
- Portal JWT wordt verkregen via magic-link flow (`/foundation/auth/magic-link`)

### 19. Trainingssamenvatting

- **Actor:** Ingelogde portal gebruiker
- **Voorwaarde:** Geldig portal JWT
- **Actie:** Request sturen met Authorization header
- **Systeemverwerking:** JWT decode -> user lookup -> blocked check
- **Succesrespons:** PortalUser object in dependency
- **Foutrespons:** 401 of 403
- **Uitzonderingen:** Geblokkeerde users krijgen 403

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De Foundation Content API is de eerste set endpoints van het Foundation Portal. Het stelt bezoekers in staat om culturele content (verhalen, kunst, audio, etc.) te ontdekken en bij te dragen.

**Publieke endpoints (geen auth nodig):**
- `GET /api/v1/{tenantSlug}/foundation/content` -- lijst van goedgekeurde content
- `GET /api/v1/{tenantSlug}/foundation/content/{id}` -- detail van een item

**Geauthenticeerde endpoints:**
- `POST /api/v1/{tenantSlug}/foundation/content` -- upload nieuwe content (JWT vereist)

**Tenant slug:** Vervang `{tenantSlug}` door de slug van de stichting, bijvoorbeeld `ketikotivlaardingen`. De slug wordt gevalideerd; onbekende slugs geven 404.

**Paginering:** Gebruik `page` en `page_size` query parameters. De response bevat `total`, `page`, `page_size`, en `pages`.

**Filters:**
- `category` -- filter op content categorie (bijv. "herinneringen")
- `type` -- filter op content type (`story`, `artwork`, `audio`, `document`, `poetry`, `link`)
- `q` -- full-text zoekterm

**Upload voorbeeld (curl):**
```bash
curl -X POST "https://api.sanskritisetu.org/api/v1/ketikotivlaardingen/foundation/content" \
  -H "Authorization: Bearer <PORTAL_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"type": "story", "title_nl": "Mijn verhaal", "rights_confirmed": true}'
```

---

## Open aannames

- `FoundationContent` model heeft al de velden `lat`, `lng`, `location_name`, `license`, `category`, `metadata_` (migratie is klaar)
- `PortalUser` model heeft al `role` veld met `PortalRole` enum
- Er is geen file-upload/storage-mechanisme in de huidige implementatie (geen lokale opslag, geen S3/MinIO); media wordt uitsluitend via `external_url` gerefereerd. Toekomstige file-upload is out of scope voor deze spec.
- AI tagging na upload wordt async afgehandeld door een aparte worker (niet in deze spec)
- `content_tags` worden via een aparte pipeline toegevoegd (niet door de uploader)
- Rate limiter is InMemory fallback in dev/test; Redis in productie

## Open vragen

- Moet `GET /foundation/content` ook `privacy = COMMUNITY` content tonen voor anonieme bezoekers?
- Moet er een `PUT /foundation/content/{id}` endpoint komen voor eigen content wijzigen?
- (Vervallen -- endpoint is al JSON-only; er is geen multipart-variant. Zie C-002 in review-BE-EP-022.md.)

## Risico's

- **Risico:** (Toekomstig, N.v.t. voor huidige implementatie) File upload zonder virusscan -- relevant zodra een file-upload endpoint wordt toegevoegd
  - **Mitigatie:** TODO(SP-VOLGENDE): ClamAV integratie of cloud-based scan, te ontwerpen bij implementatie van file-upload
- **Risico:** InMemory rate limiter bypass bij multi-worker deployment
  - **Mitigatie:** Redis backend in productie; InMemory alleen voor dev/test
- **Risico:** ContentTag JOIN queries vergeten tenant filter
  - **Mitigatie:** Code review checklist; ContentTag queries ALTIJD via FoundationContent JOIN
- **Risico:** Tenant ContextVar leakage bij exception in endpoint
  - **Mitigatie:** `public_tenant_scope()` gebruikt try/finally; tests voor leakage

---

## QA-checks

- [ ] Endpoint functioneel getest (happy path)
- [ ] Alle foutstatus-codes getest (400, 401, 403, 404, 422, 429, 500)
- [ ] Auth en permissies getest (unauthenticated upload blocked)
- [ ] Tenant-isolatie getest (cross-tenant content invisible)
- [ ] Validaties getest (ongeldige invoer, ontbrekende velden)
- [ ] Edge cases getest (leeg, null, grenzen, anonieme content)
- [ ] Data-integriteit en transacties getest (commit/rollback)
- [ ] Performance / load getest (n.v.t. voor MVP)
- [ ] Caching getest (n.v.t.)
- [ ] Logging en tracing gecontroleerd

---

## Definition of Done

- [ ] Feature is gebouwd
- [ ] Alle endpoints, services en modellen zijn geinventariseerd
- [ ] Alle relevante foutstatussen zijn beschreven
- [ ] Functionele beschrijving aanwezig
- [ ] Technische beschrijving aanwezig
- [ ] Acceptatiecriteria zijn testbaar
- [ ] Integratoruitleg is aanwezig
- [ ] Trainingssamenvatting is aanwezig
- [ ] Open aannames zijn benoemd
- [ ] QA-checks zijn uitgevoerd
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
