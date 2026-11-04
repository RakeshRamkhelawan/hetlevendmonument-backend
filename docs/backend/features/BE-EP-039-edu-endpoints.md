# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-039 |
| Naam | Educatieve leeromgeving: sessie- en content-endpoints (`/edu/*`) |
| Status | Klaar / Geïmplementeerd |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | APPROVED (Onafhankelijke review-agent Gate 2) |
| Datum | 2026-09-10 |
| User story / ticket | ADR-029 `docs/adr/029-foundation-portal-architecture.md` regels 191-201 (afgeschermde leeromgeving); audit P0-5 `docs/reports/ADR-029_AUDIT_VERIFIED_2026-08-30.md` regels 245-268 (AUTH-BYPASS-GAT + verplichte fix); audit N-2 regels 125-153 (datamodel — afgerond in BE-MIG-014) |
| Router / module | `src/core/api/v1/foundation/edu.py` (nieuw), `dependencies.py` (facade-uitbreiding), `src/core/services/edu_session_service.py` (nieuw) |
| Frontend endpoints | `POST /{tenantSlug}/foundation/edu/session`, `DELETE /{tenantSlug}/foundation/edu/session`, `GET /{tenantSlug}/foundation/edu/session`, `GET /{tenantSlug}/foundation/edu/content`, `GET /{tenantSlug}/foundation/edu/content/{content_id}` |
| Database tabellen | `educational_access` (lezen), `foundation_content` (lezen, filter visibility=edu); geen migratie |
| Versie | 1.0 |

## Doel en scope

### Doel

Afgeschermde educatieve sectie conform ADR-029: leerlingen/docenten krijgen toegang via een `edu_access_code` (8 tekens, alfanumeriek) zonder individuele accounts. `edu`-content is ALLEEN bereikbaar via `/edu/*` met geldige sessie en verschijnt nooit in het publieke archief.

### In scope

- **Sessie-uitgifte**: `POST /edu/session` — valideert code (SHA-256-hash-lookup op `code_hash`, `is_active`, `expires_at`, tenant), maakt server-side sessie aan, zet cookie.
- **Sessie-model (audit-fix, verplicht)**: ondoorzichtig willekeurig sessie-ID (256-bit, `secrets.token_urlsafe(32)`), server-side opgeslagen in **Redis met TTL = 4 uur** (14.400 s; "4 schooluren"). Het cookie bevat ALLEEN het ID. Bij ELK gebruik worden code-geldigheid én rol opnieuw tegen de database gevalideerd (`is_active`, `expires_at`, `role` uit DB — nooit uit sessie of cookie). NIET de plain-text `code:role`-cookie uit de gap-analyse overnemen.
- **Sessie-info**: `GET /edu/session` — geeft rol + verloopmoment na DB-hervalidatie; 401 bij ongeldige/verlopen sessie.
- **Sessie-verwijdering**: `DELETE /edu/session` — 204, sessie uit Redis verwijderd + cookie gewist.
- **Edu-contentlijst**: `GET /edu/content` — alleen `visibility == edu` EN `status == APPROVED`, tenant-scoped, paginatie (zelfde patroon als content.py), optionele filters `type` en `target_age_group`.
- **Edu-contentdetail**: `GET /edu/content/{content_id}` — zelfde filters; uniforme 404 bij niet-edu/niet-approved/vreemde tenant.
- Anonimiteitsmaskering (`apply_anonymity_mask`, BE-EP-038) geldt ook hier.
- Rate limiting op `POST /edu/session` met de strengste bestaande auth-limiter (brute-force op 8-teken-code).
- `public_registry.py`: alleen `POST .../edu/session` is publiek (code-invoer); alle andere `/edu/*` vereisen sessie.
- Unit-tests (offline) + integratietests (echte Postgres; Redis via fakeredis of testcontainer — hergebruik bestaande testinfrastructuur).
- Registratie in ID-REGISTRY.md.

### Out of scope

- Aanmaken/beheren van `edu_access_codes` door docenten (ADR-029 item 5, teacher-rol) — aparte feature.
- `StudyCollection` ↔ content-koppeling en leerling-overzicht — aparte feature (vereist eigen migratie).
- `metadata_` JSONB-validatie per content-type.
- Teacher-specifieke content binnen edu (MVP: rol bepaalt alleen UI-routing; content-toegang is gelijk).
- Switch van publieke endpoints van `privacy` naar `visibility`-filter (behalve waar nodig: zie O5).

## Ontwerpbeslissingen

| # | Beslissing | Reden |
|---|-----------|-------|
| O1 | Opaak sessie-ID in Redis (TTL 14.400 s), cookie bevat alleen het ID | Simpelste robuuste fix die de audit expliciet noemt (regels 265-268). Rate-limiter-infrastructuur gebruikt Redis al. Geen HMAC-signing nodig: er staat niets te vervalsen in een random ID. |
| O2 | Rol en geldigheid bij ELKE request opnieuw uit de DB | Audit-eis (regels 262-265). PK-lookup is goedkoop; sessie bevat alleen `access_id` + `tenant_id` als pointer. Deactiveren van een code werkt daardoor onmiddellijk, ook binnen de 4-uur-TTL. |
| O3 | Cookie: `edu_session`, httponly, secure, samesite=Strict, geen Domain, path=`/` | Minimaliseren van scope; geen tenant-prefix in path zodat de frontend niet per slug hoeft te koken. ID is ondoorzichtig dus geen info-lek. |
| O4 | Brute-force-bescherming via bestaande auth rate-limiter op POST /edu/session + uniforme foutmelding (401 "ongeldige code", geen onderscheid bestaat/inactief/verlopen) | 8 alfanumerieke tekens ≈ 2,8 biljoen combinaties; rate limiting volstaat. Uniforme melding voorkomt enumeratie. |
| O5 | Publieke content-endpoints (content.py) filteren vanaf nu OOK op `visibility == public/community` voor resp. anoniem/ingelogd, naast het bestaande `privacy`-filter | Zonder dit is de N-2-invariant ("edu nooit publiek") alleen mogelijk, niet afgedwongen (review BE-MIG-014, MEDIUM-bevinding). De backfill garandeert dat bestaande content identiek blijft filteren. Acceptatiecriterium + test verplicht. |
| O6 | Sessie-opslag als eigen service (`edu_session_service.py`) met kleine interface (create/get/delete); unit-tests tegen een in-memory fake, integratie tegen fakeredis/echte redis | Testbaarheid zonder Redis-afhankelijkheid offline; zelfde patroon als FoundationStorageService (local/azure). |
| O7 | Hergebruik ContentListItem/Detail-serializers incl. maskering | Consistentie met publieke API; geen parallel serializer-spoor (domeinvervuiling). |
| O8 | Nieuwe edu-dependencies (`require_edu_session`) via dependencies.py-facade + `__all__`-uitbreiding | ADR-033 Laag-2-facade; routers importeren nooit direct uit services. |

## Build summary

### Nieuw gebouwd

- `src/core/api/v1/foundation/edu.py` — 5 endpoints.
- `src/core/services/edu_session_service.py` — Redis sessie-opslag (create/get/delete, TTL 14.400 s, JSON-value `{access_id, tenant_id}`).
- Schemas: `EduSessionRequest` (code: str, exact 8 alfanumeriek, pydantic-pattern), `EduSessionResponse` (role, expires_at).
- Tests: unit (offline, in-memory fake store) + integratie (sessie-lifecycle end-to-end, edu-isolatie).

### Gewijzigd

- `src/core/api/v1/foundation/dependencies.py` — `require_edu_session` (+ evt. redis-client-dep hergebruiken), `__all__`.
- `src/core/api/v1/foundation/router.py` — edu-router mounten.
- `src/core/api/v1/foundation/content.py` — visibility-filter toevoegen (O5).
- `src/core/shared/public_registry.py` — alleen POST `/edu/session` publiek.
- `docs/backend/features/ID-REGISTRY.md`.

### Verwijderd

- Niets.

### Beïnvloede bestaande flows

- Publieke contentlijst/detail krijgt extra WHERE op `visibility`; backfill uit BE-MIG-014 garandeert identiek resultaat voor bestaande data. MISMATCH-test verplicht (rij met privacy=PUBLIC maar visibility=edu mag niet publiek zichtbaar zijn).

## API-flow

### POST `/{tenantSlug}/foundation/edu/session` (publiek, rate-limited)

1. Rate limiter (auth-niveau).
2. `public_tenant_scope(tenantSlug)` → tenant (404 bij onbekend).
3. Pydantic-validatie: code exact 8 alfanumeriek (case-normalisatie: gebruik dezelfde normalisatie als bij het AANMAKEN van codes — zoek in src/ hoe `code_hash` geschreven wordt; als er nog geen aanmaakcode is, definieer: sha256 over de code zoals ingevoerd, en documenteer).
4. Lookup `EducationalAccess` op (tenant_id, code_hash=sha256(code)). Checks: bestaat, `is_active`, `expires_at` niet verlopen (tz-aware vergelijking via de datetime-helper van het project, NOOIT datetime.now()).
5. Bij elke fout: uniforme 401, geen reden.
6. Bij succes: `session_id = secrets.token_urlsafe(32)`; Redis SET `edu_session:{id}` = `{"access_id": ..., "tenant_id": ...}` met EX=14400. Cookie zetten (O3).
7. Response 200: `{role, expires_at}` (role uit DB).

### GET/DELETE `.../edu/session`, GET `.../edu/content[/{id}]`

1. Cookie `edu_session` aanwezig → anders 401.
2. Redis GET → onbekend → 401 (cookie wissen).
3. DB-hervalidatie `EducationalAccess` (is_active, expires_at, tenant match) → faal → sessie verwijderen + 401.
4. Content-queries: `tenant_id == tenant.id AND visibility == Visibility.EDU AND status == APPROVED`; detail geeft uniforme 404 anders. Maskering toepassen.
5. DELETE: Redis DEL + cookie wissen → 204.

### Testplan

**Unit (offline, in-memory store):**
- Code-validatie (lengte, charset, uniforme 401).
- Sessie-issue: cookie-attributen, geen code/rol in cookie-waarde.
- Hervalidatie: gedeactiveerde/verlopen code → 401 ook met geldige sessie (audit-regressietest!).
- Content-filters: visibility=edu-gate, status-gate, tenant-gate, maskering.
- Publieke content.py: edu-rij onzichtbaar voor anoniem én voor JWT-gebruiker (O5).

**Integratie (echte Postgres + fakeredis/redis):**
- Volledige lifecycle: POST session → GET content 200 → code deactiveren → GET content 401 → DELETE → 401.
- TTL-configuratie 14400 s geverifieerd op de store.
- `edu_session`-pad in public_registry: POST session bereikbaar zonder JWT; GET content geeft 401 zonder cookie (niet 401 van TenantMiddleware op verkeerde grond — controleer dat het pad NIET publiek is).

## Open aannames

- Redis is in alle runtime-omgevingen beschikbaar (rate-limiter vereist het al). Zonder Redis faalt edu-sessie-uitgifte hard (503), niet stilletjes.
- Er bestaat nog geen endpoint dat codes aanmaakt; de hash-normalisatie wordt hier gedefinieerd en moet door de toekomstige aanmaak-feature exact gevolgd worden.

## Implementatie-notities (2026-09-10, bij oplevering)

- **Hash-normalisatie vastgelegd**: geverifieerd dat `code_hash` nergens in `src/` GESCHREVEN wordt (alleen model + migratie 20260909). Definitie: `hash_edu_code(code)` in `src/core/services/edu_session_service.py` = sha256-hexdigest over de code exact zoals ingevoerd (UTF-8), geen case-folding of trimming.
- **Afwijking public_registry (gemotiveerd)**: de registry matcht op PAD, niet op methode, en de TenantMiddleware 401't elk niet-publiek pad zonder JWT -- ook als er een geldige edu-sessie-cookie is. Omdat edu-authenticatie cookie-based is (geen JWT), passeren daarom ALLE `/foundation/edu/` paden de middleware; de sessie-eis wordt per endpoint afgedwongen door `require_edu_session` (uniforme 401 zonder geldige sessie). Alleen `POST /edu/session` werkt zonder sessie. Dit realiseert de spec-intentie ("alle andere /edu/* vereisen sessie") zonder wijziging aan `tenant_middleware.py` (buiten spec-scope).
- **Afwijking cookie `secure`-flag (gemotiveerd)**: O3 zegt `secure`; geimplementeerd als `secure = productie OF HTTPS-request`, hetzelfde patroon als de portal-login-cookies in `router_login.py`. Over plain HTTP (lokaal dev, tests) zou een Secure-cookie door de client geweigerd worden.
- **Testinfra**: `fakeredis` is geen dependency en er zijn geen testcontainers; bestaande integratie-infra gebruikt echte Redis opportunistisch. Integratietests draaien daarom standaard tegen `InMemoryEduSessionStore` via dezelfde `EduSessionStore`-interface (dependency override, O6); `TestSessionTtlRealRedis` verifieert de 14.400 s TTL tegen echte Redis als die bereikbaar is, en skipt anders.
- **Schema-uitbreiding**: de response-serializers (`FoundationContentListItem/Detail`, `CuratieQueueItem`) accepteerden maar 6 content-types; educatieve types (BE-MIG-014) lieten een geldige rij met een 500 falen. De gedeelde `ContentTypeValue`-Literal dekt nu alle 12 waarden (O7, hergebruik zonder parallel serializer-spoor). `FoundationContentCreateRequest` is bewust ongewijzigd (teacher-upload is out of scope).

## Definition of Done

- [x] Audit-regressietest aanwezig: cookie zelf zetten (`edu_session=WATDANOOK:teacher` of willekeurig ID) geeft NOOIT toegang
- [x] Rol/geldigheid wordt per request tegen DB gevalideerd (test met deactivatie mid-sessie)
- [x] N-2-invariant afgedwongen + getest: edu-content onzichtbaar via publieke endpoints
- [x] Unit + integratie groen; ruff/mypy groen op gewijzigde bestanden
- [x] Review APPROVED (incl. Devil's Advocate)
- [x] ID-REGISTRY.md bijgewerkt

---

## Trainingssamenvatting

- **Actor:** Leerling of docent in een onderwijsinstelling die met een toegangscode toegang wil tot educatief erfgoedmateriaal.
- **Voorwaarde:** Een geldige, actieve en niet-verlopen EducationalAccess toegangscode geregistreerd voor de betreffende tenant.
- **Actie:** POST /{tenantSlug}/foundation/edu/session met de 8-tekens toegangscode, gevolgd door GET /{tenantSlug}/foundation/edu/content met de ontvangen sessie-cookie.
- **Systeemverwerking:** Valideert de code-hash tegen PostgreSQL, creeert bij succes een cryptografisch willekeurige sessie-ID in Redis met een TTL van 14400 seconden, en stelt een HTTP-only cookie in. Bij daaropvolgende verzoeken valideert require_edu_session het cookie in Redis en controleert de actieve status in PostgreSQL. Content-queries filteren strikt op visibility = Visibility.EDU en status = APPROVED.
- **Succesrespons:** HTTP 200 OK bij sessie-aanmaak met rol en verloopdatum; HTTP 200 OK bij content-opvraging met educatieve verhalen en leermiddelen.
- **Foutrespons:** HTTP 401 bij ongeldige, verlopen of gedeactiveerde code (uniforme foutmelding); HTTP 401 bij ontbrekend of verlopen sessie-cookie; HTTP 404 bij onbekende tenant of niet-bestaand content-item.
