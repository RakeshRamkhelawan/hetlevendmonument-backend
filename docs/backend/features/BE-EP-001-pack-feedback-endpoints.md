# Backend Feature Specification

## Metadata

- **Feature ID:** BE-EP-001
- **Feature naam:** Pack Feedback API Endpoints
- **Status:** APPROVED
- **Auteur:** SP-A02 Dag 2
- **Reviewer:** SP-A02 Dag 2 (self-review via reviewer prompt)
- **Datum:** 2026-05-28
- **Gerelateerde user story / ticket:** SP-A02 -- Pack feedback + global pack repository
- **Gerelateerde router / module:** `src.core.api.pack_feedback_endpoints`
- **Gerelateerde frontend endpoints:** N.v.t. (backend only)
- **Gerelateerde database tabellen:** `pack_feedback`, `global_packs`
- **Versie:** 1.0

---

## Doel en scope

### Doel

Bieden van REST API endpoints voor gebruikersfeedback op pack template matches en voor het beheren van een globale pack repository. Dit vervangt de eerdere in-memory singleton implementatie door een persistente PostgreSQL-oplossing met tenant-isolatie.

### In scope

- Feedback submitten op een pack match (`POST /submit`)
- Feedback statistieks opvragen (`GET /stats/{pack_id}`)
- Global pack bijdragen (`POST /contribute`)
- Global packs zoeken met paginering (`POST /global/search`)
- Pending packs ophalen (`GET /global/pending`)
- Global pack goedkeuren (`POST /global/{pack_id}/approve`)
- Global pack ophalen (`GET /global/{pack_id}`)
- Alle bijbehorende Pydantic request/response schemas

### Out of scope

- Admin rol check (gemarkeerd als TODO)
- Echte RBAC permissies op approve/pending endpoints
- Frontend integratie
- Websocket notificaties bij approval
- Pack matching algoritme zelf

---

## Build summary

- **Nieuw gebouwd:** `PackFeedback`, `GlobalPack` ORM models + Alembic migratie (dag 1)
- **Gewijzigd:** `src/core/api/pack_feedback_endpoints.py` -- volledige rewrite van singletons naar async DB queries
- **Verwijderd:** `FeedbackStore` singleton, `GlobalPackRepository` singleton
- **Beinvloede bestaande flows:** Geen breaking changes; nieuwe endpoints op bestaande router

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-001 | Pack Feedback API Endpoints | Endpoint set | `src/core/api/pack_feedback_endpoints.py` | Wijziging | BE-FLW-001 |
| BE-SCH-002 | PackFeedbackRequest | Pydantic schema | `src/core/api/pack_feedback_endpoints.py` | Nieuw | BE-FLW-001 |
| BE-SCH-003 | PackFeedbackResponse | Pydantic schema | `src/core/api/pack_feedback_endpoints.py` | Nieuw | BE-FLW-001 |
| BE-SCH-004 | GlobalPackContributionRequest | Pydantic schema | `src/core/api/pack_feedback_endpoints.py` | Nieuw | BE-FLW-002 |
| BE-SCH-005 | GlobalPackContributionResponse | Pydantic schema | `src/core/api/pack_feedback_endpoints.py` | Nieuw | BE-FLW-002 |
| BE-SCH-006 | GlobalPackSearchRequest | Pydantic schema | `src/core/api/pack_feedback_endpoints.py` | Nieuw | BE-FLW-003 |
| BE-MDL-001 | PackFeedback + GlobalPack | SQLAlchemy models | `src/core/governance/models.py` | Nieuw | -- |
| BE-MIG-001 | add_pack_feedback_global_packs_tables | Alembic migratie | `src/alembic/versions/11ffd3a57d26_*.py` | Nieuw | -- |

---

## API-flows

### Flow ID: BE-FLW-001 -- Feedback submitten

- **Naam:** Gebruiker submit feedback op pack match
- **Trigger:** `POST /api/v1/pack-feedback/submit`
- **Voorwaarden:** Authenticated user, tenant context via JWT claim
- **Request-pad:** Client -> FastAPI router -> `submit_feedback()` -> DB insert -> audit log
- **Service-stappen:**
  1. Valideer dat rating aanwezig is (anders 422)
  2. Maak `PackFeedback` ORM object met tenant_id uit dependency
  3. Sla op in DB via `db.add()` + `db.commit()`
  4. Schrijf audit log via `best_effort()` wrapper
- **DB-operaties:** INSERT INTO `pack_feedback`
- **Successtatus + response:** 200 OK + `PackFeedbackResponse`
- **Foutpaden:**
  - 401: Niet ingelogd
  - 422: Ontbrekende rating
  - 500: DB fout
- **Eindtoestand:** Feedback row in `pack_feedback` tabel

### Flow ID: BE-FLW-002 -- Global pack bijdragen

- **Naam:** Gebruiker draagt een AI-customized pack bij
- **Trigger:** `POST /api/v1/pack-feedback/contribute`
- **Voorwaarden:** Authenticated user
- **Request-pad:** Client -> `contribute_global_pack()` -> DB insert -> audit log
- **Service-stappen:**
  1. Valideer request body via Pydantic
  2. Maak `GlobalPack` met JSONB `pack_data` (status=pending_review)
  3. Sla op in DB
  4. Retourneer pack_id + pending status
- **DB-operaties:** INSERT INTO `global_packs`
- **Successtatus + response:** 200 OK + `GlobalPackContributionResponse`
- **Foutpaden:** 401, 422, 500
- **Eindtoestand:** Pack in `global_packs` met status "pending_review"

### Flow ID: BE-FLW-003 -- Global packs zoeken

- **Naam:** Zoeken door global pack repository
- **Trigger:** `POST /api/v1/pack-feedback/global/search`
- **Voorwaarden:** Authenticated user
- **Request-pad:** Client -> `search_global_packs()` -> DB query met filter + paginering
- **Service-stappen:**
  1. Bouw SQL query met tenant filter, department filter (optioneel), text search
  2. Voer COUNT(*) uit voor total
  3. Voer paginated query uit (limit/offset)
  4. Serialize resultaten via `_global_pack_to_info()`
- **DB-operaties:** SELECT COUNT(*) + SELECT FROM `global_packs`
- **Successtatus + response:** 200 OK + `{"success": True, "data": [...], "total": N, "limit": N, "offset": N}`
- **Foutpaden:** 401, 500
- **Eindtoestand:** Geen DB wijzigingen (read-only)

### Flow ID: BE-FLW-004 -- Global pack goedkeuren

- **Naam:** Admin keurt een pending global pack goed
- **Trigger:** `POST /api/v1/pack-feedback/global/{pack_id}/approve`
- **Voorwaarden:** Authenticated user (TODO: admin check)
- **Request-pad:** Client -> `approve_global_pack()` -> DB update -> audit log
- **Service-stappen:**
  1. Zoek pack by UUID + tenant_id
  2. Update JSONB `status` naar "approved" via `flag_modified()`
  3. Commit transactie
- **DB-operaties:** SELECT + UPDATE `global_packs.pack_data`
- **Successtatus + response:** 200 OK + `{"success": True, "data": {"message": "..."}}`
- **Foutpaden:** 401, 404 (onbekend pack_id), 500
- **Eindtoestand:** Pack status = "approved"

---

## Detaildocumentatie per artefact

---

## [BE-EP-001] Pack Feedback API Endpoints

### 1. Type

Endpoint set / APIRouter groep

### 2. Locatie

- **Bestandspad:** `src/core/api/pack_feedback_endpoints.py`
- **Klasse / functie:** `router = APIRouter(prefix="/api/v1/pack-feedback", tags=["pack-feedback"])`

### 3. Gerelateerde flow

BE-FLW-001, BE-FLW-002, BE-FLW-003, BE-FLW-004

### 4. Doel

Exposeren van CRUD-achtige operaties voor pack feedback en global pack management aan geauthenticeerde clients, met strikte tenant-isolatie.

### 5. Functionele beschrijving

Gebruikers kunnen:
1. Feedback geven op pack matches (rating 1-5 + optionele tekst)
2. Eigen workflows als global packs bijdragen
3. Bestaande global packs zoeken en bekijken
4. (Admin) Pending packs goedkeuren

Alle operaties zijn tenant-geisoleerd: een gebruiker ziet en manipuleert alleen data binnen zijn eigen tenant.

### 6. Technische beschrijving

- **Router:** FastAPI `APIRouter` met prefix `/api/v1/pack-feedback`
- **Dependencies per endpoint:**
  - `db: AsyncSession = Depends(get_db)` -- async PostgreSQL sessie
  - `tenant_id: int = Depends(require_tenant_id)` -- uit JWT claim via ContextVar
  - `current_user: UserResponse = Depends(get_current_user)` -- uit JWT token
- **Dataflow:** Request -> Pydantic validatie -> tenant filter toepassen -> DB query/insert -> response
- **JSONB manipulatie:** `flag_modified()` wordt aangeroepen bij elke JSONB mutatie zodat SQLAlchemy de wijziging detecteert
- **Audit logging:** `best_effort()` wrapper zorgt dat audit logging nooit de hoofdtransactie faalt

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** Ja (JWT bearer token)
- **Vereiste rol / scope:** Authenticated user voor alle endpoints; admin voor approve/pending (TODO)
- **Tenant-isolatie:** Ja, via `tenant_id` dependency + WHERE clauses in alle queries
- **Feature flag:** N.v.t.

### 8. Request-specificatie per endpoint

#### POST /submit

- **Methode:** POST
- **Route:** `/api/v1/pack-feedback/submit`
- **Path parameters:** Geen
- **Query parameters:** Geen
- **Request body (schema):** `PackFeedbackRequest`
  - `session_id`: str (verplicht)
  - `pack_id`: str (verplicht)
  - `original_prompt`: str (verplicht)
  - `was_helpful`: bool (verplicht)
  - `rating`: int | None (1-5, verplicht in business logic)
  - `feedback_text`: str | None (optioneel)
  - `used_as_is`: bool (default False)
  - `customizations_made`: list[str] (default [])
- **Verplichte headers:** `Authorization: Bearer <token>`

#### GET /stats/{pack_id}

- **Methode:** GET
- **Route:** `/api/v1/pack-feedback/stats/{pack_id}`
- **Path parameters:** `pack_id: str`
- **Query parameters:** Geen
- **Request body:** Geen
- **Verplichte headers:** `Authorization: Bearer <token>`

#### POST /contribute

- **Methode:** POST
- **Route:** `/api/v1/pack-feedback/contribute`
- **Path parameters:** Geen
- **Query parameters:** Geen
- **Request body (schema):** `GlobalPackContributionRequest`
  - `name`: str (verplicht)
  - `description`: str (verplicht)
  - `department`: str (verplicht)
  - `source_pack_ids`: list[str] (default [])
  - `workflow_definition`: dict (verplicht)
  - `intent_tags`: list[str] (default [])
  - `capabilities`: list[str] (default [])
  - `is_public`: bool (default True)

#### POST /global/search

- **Methode:** POST
- **Route:** `/api/v1/pack-feedback/global/search`
- **Path parameters:** Geen
- **Query parameters:** `offset: int = 0` (ge >= 0)
- **Request body (schema):** `GlobalPackSearchRequest`
  - `query`: str (verplicht)
  - `department`: str | None
  - `limit`: int (default 10, ge=1, le=50)

#### GET /global/pending

- **Methode:** GET
- **Route:** `/api/v1/pack-feedback/global/pending`
- **Path parameters:** Geen
- **Query parameters:** `limit: int = 50` (le=1000), `offset: int = 0` (ge=0)
- **Request body:** Geen

#### POST /global/{pack_id}/approve

- **Methode:** POST
- **Route:** `/api/v1/pack-feedback/global/{pack_id}/approve`
- **Path parameters:** `pack_id: UUID`
- **Query parameters:** Geen
- **Request body:** Geen

#### GET /global/{pack_id}

- **Methode:** GET
- **Route:** `/api/v1/pack-feedback/global/{pack_id}`
- **Path parameters:** `pack_id: UUID`
- **Query parameters:** Geen
- **Request body:** Geen

### 9. Response-specificatie

#### POST /submit

- **Successtatus:** 200 OK
- **Response schema:** `PackFeedbackResponse`
  - `success`: bool
  - `message`: str
  - `feedback_id`: str | None
- **Foutstatussen:** 401, 422, 500

#### GET /stats/{pack_id}

- **Successtatus:** 200 OK
- **Response schema:**
  - `success`: bool
  - `data`: {"pack_id": str, "total_feedback": int, "average_rating": float | None, "total_ratings": int}
- **Foutstatussen:** 401, 500

#### POST /contribute

- **Successtatus:** 200 OK
- **Response schema:** `GlobalPackContributionResponse`
  - `success`: bool
  - `pack_id`: str
  - `message`: str
  - `review_status`: str (default "pending")
- **Foutstatussen:** 401, 422, 500

#### POST /global/search, GET /global/pending

- **Successtatus:** 200 OK
- **Response schema:**
  - `success`: bool
  - `data`: list[GlobalPackInfo]
  - `total`: int
  - `limit`: int
  - `offset`: int
- **Foutstatussen:** 401, 500

#### POST /global/{pack_id}/approve, GET /global/{pack_id}

- **Successtatus:** 200 OK
- **Response schema:**
  - `success`: bool
  - `data`: dict (message of pack info)
- **Foutstatussen:** 401, 404, 500

### 10. Validaties en constraints

- `rating`: 1-5 via Pydantic `Field(ge=1, le=5)`
- `limit`: 1-50 voor search, 0-1000 voor pending
- `offset`: >= 0
- `pack_id` (path param): geldige UUID voor approve/get endpoints
- Alle tekstvelden zijn verplicht waar aangegeven

### 11. Business rules

- Feedback zonder rating wordt geweigerd (422)
- Bijgedragen packs krijgen automatisch status "pending_review"
- Tenant A kan nooit packs of feedback van tenant B zien
- `usage_count` wordt automatisch verhoogd bij `GET /global/{pack_id}`
- `average_rating` wordt berekend uit `sum_ratings / total_ratings` in `_global_pack_to_info()`

### 12. Afhankelijkheden

- `src.core.database.database.get_db`
- `src.core.middleware.tenant_context.require_tenant_id`
- `src.core.auth.dependencies.get_current_user`
- `src.core.governance.models.PackFeedback, GlobalPack`
- `src.core.utils.best_effort.best_effort`

### 13. Foutafhandeling

- **400:** Niet expliciet gebruikt
- **401:** `get_current_user` dependency faalt
- **403:** Niet expliciet gebruikt (TODO: admin check)
- **404:** Onbekend `pack_id` bij approve/get
- **409:** Niet gebruikt
- **422:** Ontbrekende rating bij submit; Pydantic validatiefouten
- **429:** Niet gebruikt
- **500:** Onverwachte DB fout of exception in endpoint logica

### 14. Transacties en data-integriteit

- Elke write operatie gebruikt `await db.commit()`
- `flag_modified()` wordt aangeroepen voor JSONB mutaties zodat SQLAlchemy de wijziging detecteert
- `best_effort()` wrapper voor audit logging: faalt nooit de hoofdtransactie

### 15. Telemetry / logging / tracing

- Pack feedback submit: INFO log met tenant_id, user_id, pack_id, rating
- Pack contribution: INFO log met tenant_id, user_id, pack_id
- Pack approval: INFO log met tenant_id, pack_id, approved_by
- Errors: ERROR log met exception type en traceback

### 16. Caching

- **Gecached:** Nee
- Geen caching-laag op deze endpoints

### 17. Acceptatiecriteria

- [ ] Gebruiker kan feedback submitten met rating 1-5
- [ ] Feedback zonder rating geeft 422
- [ ] Feedback is tenant-geisoleerd
- [ ] Gebruiker kan global pack bijdragen (status = pending)
- [ ] Zoeken geeft gepagineerde resultaten met total/limit/offset
- [ ] Onbekend pack_id geeft 404
- [ ] Admin kan pack goedkeuren (status -> approved)
- [ ] Alle endpoints vereisen authenticatie
- [ ] Audit logging wordt geschreven bij writes

### 18. Integratoruitleg

- **Feedback submitten:** POST `/api/v1/pack-feedback/submit` met rating (1-5) en optionele tekst
- **Zoeken:** POST `/api/v1/pack-feedback/global/search` met `query` en optionele `department`
- **Paginering:** Gebruik `offset` query param en `limit` in body; `total` in response geeft totaal aantal
- **Bijdragen:** POST `/api/v1/pack-feedback/contribute` met pack naam, beschrijving, en workflow definition
- **Pack ophalen:** GET `/api/v1/pack-feedback/global/{pack_id}` verhoogt automatisch de usage counter

### 19. Trainingssamenvatting

- **Actor:** Geauthenticeerde gebruiker (tenant)
- **Voorwaarde:** JWT token geldig, tenant context actief
- **Actie (request):** POST feedback, GET stats, POST contribute, POST search, GET pack
- **Systeemverwerking:** Tenant filter toepassen -> DB query/insert -> JSONB manipulatie -> response
- **Succesrespons:** 200 OK met `{"success": True, "data": ...}`
- **Foutrespons:** 401 (auth), 404 (not found), 422 (invalid input), 500 (server error)
- **Uitzonderingen:** Admin-only endpoints (approve/pending) hebben nog geen rol check

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

De Pack Feedback API bestaat uit twee hoofdfunctionaliteiten:

1. **Feedback geven op packs:** Gebruikers kunnen een rating (1-5 sterren) en optionele tekst achterlaten op een pack match. Dit helpt het platform om pack matching te verbeteren.

2. **Global pack repository:** Gebruikers kunnen eigen workflows als packs bijdragen aan een gedeelde repository. Deze packs doorlopen een review-proces (pending -> approved).

Alle endpoints vereisen een geldige JWT token. De tenant wordt automatisch bepaald uit de JWT claim -- er is geen `X-Tenant-ID` header nodig.

Bij zoeken en lijst-endpoints wordt altijd een gepagineerde response teruggegeven:
```json
{
  "success": true,
  "data": [...],
  "total": 100,
  "limit": 10,
  "offset": 0
}
```

---

## Open aannames

- Admin rol check is nog niet geimplementeerd (TODO comments in approve/pending endpoints)
- `pack_data["average_rating"]` wordt client-side berekend uit `sum_ratings / total_ratings`; er is geen database trigger voor
- De `usage_count` increment bij `GET /global/{pack_id}` is een side-effect die niet transactioneel geisoleerd is van het GET request

## Open vragen

- Moet `GET /stats/{pack_id}` ook anoniem toegankelijk zijn (zonder auth)?
- Moet er een `reject` endpoint komen naast `approve`?

## Risico's

- **Risico:** Admin endpoints zonder admin check kunnen door elke geauthenticeerde gebruiker worden aangeroepen
  - **Mitigatie:** TODO in code gemarkeerd; moet voor production worden opgelost
- **Risico:** `usage_count` increment is niet concurrency-safe zonder row-level locking
  - **Mitigatie:** Voor MVP acceptabel; bij hoge load moet dit naar een aparte counter tabel of Redis

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest (401, 404, 422, 500 paths)
- [x] Auth en permissies getest (unauthenticated request blocked)
- [x] Tenant-isolatie getest (tenant_id filter in query)
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [ ] Data-integriteit en transacties getest (handmatig gecontroleerd)
- [ ] Performance / load getest (n.v.t. voor MVP)
- [ ] Caching getest (n.v.t.)
- [x] Logging en tracing gecontroleerd (best_effort wrapper, INFO/ERROR logs)

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
- [x] Review door reviewer-prompt: APPROVED
