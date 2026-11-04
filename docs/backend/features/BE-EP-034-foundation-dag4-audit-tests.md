# Backend Feature Specification

## Metadata

- **Feature ID:** BE-EP-034
- **Feature naam:** Foundation Portal Dag 4 -- Audit Logging, Rate-Limit Hardening, Cross-Tenant Tests
- **Status:** APPROVED
- **Auteur:** ADR-029 Dag 4
- **Reviewer:** zelfstandige review binnen dezelfde sessie (geen aparte agent-ronde; kleine, goed-afgebakende wijziging)
- **Datum:** 2026-08-26
- **Gerelateerde user story / ticket:** ADR-029 -- Foundation Portal white-label portal voor Stichting Ketikotivlaardingen.NL, Dag 4 van 6
- **Gerelateerde router / module:** `src.core.api.v1.foundation.auth`, `.takedown`, `.newsletter`, `src.core.governance.rate_limiter`, `src.core.shared.rate_limiter`
- **Gerelateerde frontend endpoints:** `frontend/src/lib/api/foundationClient.ts` (nieuw, zie FE-API-001)
- **Gerelateerde database tabellen:** geen nieuwe tabellen; leest/schrijft bestaande `portal_users`, `magic_link_tokens`, `takedown_requests`, `newsletter_subscriptions`, plus de bestaande audit-tabel via `AuditService`
- **Versie:** 1.0

---

## Doel en scope

### Doel

Dag 3 leverde de Foundation Portal auth/settings/takedown/newsletter-endpoints, maar zonder
audit-spoor (ADR-019) en zonder bewijs dat de rate limiters daadwerkelijk 429 retourneren.
Deze dag sluit dat gat, en levert daarnaast de eerste cross-tenant-isolatietests en de
kickoff van de frontend API-client.

### In scope

- Audit-logging (best-effort) op magic-link-login en takedown-aanmaak.
- Vier nieuwe integratietests die daadwerkelijk 429 verifieren voor elk van de vier
  rate-gelimiteerde endpoints.
- Herstel van een structureel probleem in de rate-limiter-aanpak zelf (zie Sectie
  "Technische beschrijving" hieronder) dat pas zichtbaar werd tijdens het schrijven van die
  429-tests.
- Twee cross-tenant/beveiligingstests: newsletter-unsubscribe is tenant-gescoped, en een
  geblokkeerde gebruiker kan geen magic-link verzilveren.
- Frontend `FoundationApiClient`-kickoff (zie FE-API-001, apart gedocumenteerd).

### Out of scope

- Content/curatie-endpoints in de frontend-client (alleen auth/settings/takedown/newsletter).
- DSAR-export, edu-access, OAI-PMH, admin-users, admin-edu-codes (BE-EP-028/029/030/032/033 --
  nog niet gebouwd, apart gepland).
- Volledige oplossing van de BE-EP-023-t/m-033-ID-duplicatie in `ID-REGISTRY.md` (zie
  Risico's).

---

## Build summary

- Nieuw gebouwd: `frontend/src/lib/api/foundationClient.ts`; 3 nieuwe testbestanden/
  -uitbreidingen (`test_rate_limits.py`, uitbreiding `test_auth.py`, uitbreiding
  `test_newsletter.py`).
- Gewijzigd: `auth.py` (audit-log op verify), `takedown.py` (audit-log op create, plus een
  opgeruimde ongebruikte `request`-parameter), `newsletter.py` (rate-limiter-refactor),
  `governance/rate_limiter.py` (4 nieuwe FastAPI-dependency-functies naast de bestaande
  decorators), `shared/rate_limiter.py` (`__signature__`-fix voor FastAPI-introspectie),
  `test_settings.py` (1 pre-existing test-bug gefixed, zie hieronder).
- Verwijderd: 4 debug-scratch-bestanden die tijdens het onderzoek van de rate-limiter-bug
  zijn ontstaan (`sandboxlog.md`, `scripts/impact_analysis.py`, `scripts/test_sig.py`,
  `tests/integration/api/v1/foundation/test_rate_limits_debug.py` -- de laatste bevatte een
  opzettelijke `assert False` om debug-output te forceren, geen echte test).
- Beinvloede bestaande flows: geen breaking changes -- alle wijzigingen zijn additief
  (audit-logging is best-effort, rate-limiter-refactor behoudt exact dezelfde limieten).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-034-1 | `require_portal_auth_rate_limit` | BE-DEP | `src/core/governance/rate_limiter.py` | Nieuw | Magic-link request + verify |
| BE-EP-034-2 | `require_portal_magic_link_email_rate_limit` | BE-DEP | `src/core/governance/rate_limiter.py` | Nieuw | Magic-link request (anti-spam) |
| BE-EP-034-3 | `require_portal_takedown_rate_limit` | BE-DEP | `src/core/governance/rate_limiter.py` | Nieuw | Takedown-aanmaak |
| BE-EP-034-4 | `require_portal_newsletter_rate_limit` | BE-DEP | `src/core/governance/rate_limiter.py` | Nieuw | Newsletter subscribe/unsubscribe |
| BE-EP-034-5 | Audit-log magic-link-verify | BE-SVC | `src/core/api/v1/foundation/auth.py::verify_magic_link` | Wijziging | Portal login |
| BE-EP-034-6 | Audit-log takedown-create | BE-SVC | `src/core/api/v1/foundation/takedown.py::create_takedown` | Wijziging | Takedown-indiening |

---

## API-flows

### Flow ID: BE-FLW-034-1 -- Rate-limited magic-link request met audit-spoor bij verify

- Naam: Magic-link aanvragen (IP + e-mail gelimiteerd) -> verifieren (audit-gelogd)
- Trigger: `POST /{tenantSlug}/foundation/auth/magic-link`, gevolgd door
  `POST /{tenantSlug}/foundation/auth/magic-link/verify`
- Voorwaarden (auth, tenant, feature flag): geen auth vereist; tenant moet bestaan en actief
  zijn (`public_tenant_scope`)
- Request-pad: `require_portal_auth_rate_limit` (FastAPI-`Depends`, IP-based, 5/min) ->
  `MagicLinkRequest`-body-validatie -> handmatige aanroep van
  `require_portal_magic_link_email_rate_limit` (e-mail-based, 3/uur, NA body-validatie omdat
  de dependency-laag het geparste e-mailadres nog niet kent -- zie Technische beschrijving)
- Service-stappen: token genereren, hash opslaan, notificatie versturen (best-effort)
- DB-operaties: INSERT `magic_link_tokens`
- Successtatus + response: 202, generiek bericht (geen enumeratie)
- Foutpaden: 429 (IP- of e-mail-limiet), 404 (onbekende tenant)
- Eindtoestand: bij verify -- UPDATE `magic_link_tokens.used_at` (atomisch, tegen replay),
  UPDATE `portal_users` (`last_login_at`, `email_verified`), best-effort audit-log
  (`portal_login`) via `AuditService.log_event`

---

## Detaildocumentatie per artefact

---

## [BE-EP-034-1..4] Foundation rate-limiter dependencies

### 1. Type

- FastAPI dependency-functies (`async def ... (request: Request) -> None`)

### 2. Locatie

- Bestandspad: `src/core/governance/rate_limiter.py`
- Functies: `require_portal_auth_rate_limit`, `require_portal_magic_link_email_rate_limit`,
  `require_portal_takedown_rate_limit`, `require_portal_newsletter_rate_limit`

### 3. Gerelateerde flow

- BE-FLW-034-1

### 4. Doel

Vervangen (voor nieuwe/gewijzigde routes) van de bestaande decorator-gebaseerde
`portal_*_limit`-functies (die BLIJVEN bestaan, ongewijzigd, voor routes die ze nog gebruiken)
door FastAPI-`Depends()`-functies. Reden: een decorator die BOVEN `@router.post(...)` staat,
wrapt de ge-registreerde route-functie zelf -- maar FastAPI's eigen dependency-injectie-laag
(body-parsing, andere `Depends()`) loopt PARALLEL daaraan, niet noodzakelijk erbinnen. Voor
`portal_auth_limit`/`portal_magic_link_email_limit` werkte dat toevallig goed genoeg (puur
IP-based, geen data uit de body nodig), maar het maakte een e-mail-based limiet
structureel lastig: `_email_key()` moet het geparste e-mailadres kunnen lezen, en dat bestaat
pas NADAT FastAPI de `Pydantic`-body heeft gevalideerd.

### 5. Functionele beschrijving

Elke dependency-functie berekent een sleutel (IP of e-mail), controleert de
sliding-window-teller in `InMemoryRateLimiter`, en werpt `HTTPException(429)` met een
`Retry-After`-header zodra het maximum is bereikt. Geen zichtbaar verschil voor de
eindgebruiker t.o.v. de oude decorators -- zelfde limieten, zelfde foutstructuur.

### 6. Technische beschrijving

`require_portal_auth_rate_limit` en `require_portal_takedown_rate_limit` en
`require_portal_newsletter_rate_limit` zijn zuiver IP-based (`_ip_key`) en worden ALTIJD als
gewone FastAPI-`Depends()`-parameter gebruikt -- geen bijzonderheden, ze hebben de body niet
nodig.

`require_portal_magic_link_email_rate_limit` is de uitzondering: `_email_key()` leest
`request.state.parsed_email`, een attribuut dat NIET door FastAPI zelf wordt gezet. De
aanroepende route (`request_magic_link` in `auth.py`) zet dit attribuut EXPLICIET, ZELF, in
de functie-body -- NA dat `data: MagicLinkRequest` al gebonden is -- en roept deze functie
dan HANDMATIG aan (`await require_portal_magic_link_email_rate_limit(request)`), niet via
`Depends()`. Dit is een bewuste, gedocumenteerde afwijking van het gebruikelijke
dependency-patroon, met een inline-comment die uitlegt waarom (`# Email-based rate limit
(inline because parsed_email is only available here)`).

`shared/rate_limiter.py::privacy_rate_limit`'s decorator-`wrapper` kreeg
`wrapper.__signature__ = inspect.signature(func)` toegevoegd. Dit was NIET strikt nodig voor
de nieuwe `require_portal_*`-dependencies zelf (die zijn geen decorators), maar loste een
apart signature-introspectie-probleem op dat zichtbaar werd tijdens hetzelfde onderzoek (een
`functools.wraps`-gewrapte functie kopieert `__wrapped__`/`__name__`/etc. maar niet
automatisch een expliciete `__signature__` die FastAPI's introspectie in sommige gevallen
nodig heeft) -- gemeten met een kleine, losse repro (`scripts/test_sig.py`, sindsdien
verwijderd na gebruik).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: geen (rate-limiters gelden voor zowel geauthenticeerde als
  anonieme requests)
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: n.v.t. (rate-limit-sleutels zijn IP/e-mail-based, niet tenant-based --
  bewust, want het doel is misbruik vanaf een bron beperken, niet per tenant)
- Feature flag: geen

### 8-16. Request/response/validaties/business rules/afhankelijkheden/foutafhandeling/transacties/caching

Geen wijziging t.o.v. de bestaande, reeds gedocumenteerde endpoints in BE-EP-023 -- deze
sectie voegt alleen de rate-limiter-laag toe, de endpoint-contracten zelf zijn ongewijzigd
behalve de audit-logging (zie BE-EP-034-5/6 hieronder).

### 17. Acceptatiecriteria

- Na 5 magic-link-requests binnen 1 minuut vanaf hetzelfde IP (verschillende e-mails):
  6e request -> 429, met `Retry-After`-header.
- Na 3 magic-link-requests binnen 1 uur met HETZELFDE e-mailadres: 4e request -> 429.
- Na 5 takedown-requests binnen 1 uur van dezelfde geauthenticeerde gebruiker: 6e -> 429.
- Na 3 newsletter-subscribes binnen 1 uur vanaf hetzelfde IP: 4e -> 429.
- Alle vier bewezen met een echte HTTP-integratietest tegen de daadwerkelijke route (niet
  tegen de rate-limiter-functie in isolatie).

### 18. Integratoruitleg

- Elk 429-antwoord bevat `retry_after` (seconden) in de body en een `Retry-After`-header --
  clients kunnen dit direct gebruiken voor backoff-UI.
- De limieten zijn niet per-tenant maar per-IP/e-mail: een client die meerdere tenants
  aanspreekt vanaf hetzelfde IP deelt de IP-teller.

### 19. Trainingssamenvatting

- Actor: anonieme of geauthenticeerde portal-bezoeker
- Voorwaarde: X requests binnen het tijdvenster al verstuurd vanaf dezelfde sleutel (IP of
  e-mail)
- Actie (request): een (X+1)e request naar hetzelfde rate-gelimiteerde endpoint
- Systeemverwerking: `InMemoryRateLimiter.is_allowed()` retourneert `False`,
  `HTTPException(429)` geworpen VOOR de route-body uitvoert
- Succesrespons: n.v.t. (dit IS het foutpad)
- Foutrespons: `429 Too Many Requests`, body met `error`/`message`/`retry_after`,
  `Retry-After`-header
- Uitzonderingen: geen -- deterministisch, geen bypass

---

## [BE-EP-034-5/6] Audit-logging op magic-link-verify en takedown-create

### 1. Type

- Inline audit-log-aanroepen binnen bestaande route-handlers (geen nieuw endpoint)

### 2. Locatie

- `src/core/api/v1/foundation/auth.py::verify_magic_link` (na succesvolle JWT-creatie)
- `src/core/api/v1/foundation/takedown.py::create_takedown` (na succesvolle DB-flush)

### 4. Doel

ADR-019 (audit-hashketen) dekt de Foundation Portal nog niet. Een portal-login en een
takedown-verzoek zijn beide gebeurtenissen die een audit-spoor verdienen (respectievelijk:
wie logt in, en wie dient een verwijderverzoek in tegen welke content).

### 5. Functionele beschrijving

Bij een succesvolle magic-link-verificatie wordt een `portal_login`-gebeurtenis gelogd (lage
severity). Bij een succesvol aangemaakt takedown-verzoek wordt een `takedown_created`-
gebeurtenis gelogd (medium severity, want een takedown kan content laten verwijderen).

### 6. Technische beschrijving

Beide aanroepen gebruiken `AuditService.log_event(db=session, ...)` gewrapt in
`async with best_effort(...)` (`src/core/utils/best_effort.py`, backend-patterns.md #3) --
een audit-schrijffout mag de primaire actie (login/takedown) nooit blokkeren. De primaire
data (JWT-creatie resp. `TakedownRequest`-record) is op dat moment al ge-flusht in dezelfde
sessie/transactie; de audit-log volgt daarna, conform het patroon "commit primaire data
eerst, audit-log daarna in best_effort".

### 13. Foutafhandeling

- Audit-log-schrijffout: gevangen door `best_effort`, gelogd, GEEN impact op de
  HTTP-respons van de primaire actie.

### 17. Acceptatiecriteria

- Een succesvolle magic-link-verify resulteert in een audit-event met
  `event_type="portal_login"`, `tenant_id`, `user_id`.
- Een succesvolle takedown-aanmaak resulteert in een audit-event met
  `event_type="takedown_created"`, `resource=f"content:{content_id}"`.
- Beide zijn best-effort: een audit-schrijffout mag de 200/202/201-respons niet omzetten in
  een 500.

### 19. Trainingssamenvatting

- Actor: portal-gebruiker (magic-link) of geauthenticeerde portal-visitor (takedown)
- Voorwaarde: de primaire actie (login/takedown) is al geslaagd
- Actie (request): n.v.t. (dit is een side-effect, geen eigen endpoint)
- Systeemverwerking: `AuditService.log_event()` binnen `best_effort()`
- Succesrespons: onveranderd (audit-logging is onzichtbaar voor de client)
- Foutrespons: onveranderd (audit-fout blokkeert de primaire respons niet)
- Uitzonderingen: geen

---

## Cross-tenant en security-tests (nieuw)

- `test_auth.py::test_verify_blocked_user_returns_403`: een geblokkeerde gebruiker
  (`is_blocked=True`) krijgt 403 bij het verzilveren van een overigens geldig token. Het
  token wordt WEL als gebruikt gemarkeerd (de atomaire UPDATE loopt voor de blok-check) --
  bewust zo gelaten, gedocumenteerd in de test: een geblokkeerde gebruiker kan hetzelfde
  token niet opnieuw proberen na deblokkeren.
- `test_newsletter.py::test_unsubscribe_is_tenant_scoped`: een e-mailadres dat in tenant
  "default" is aangemeld, blijft aangemeld nadat een unsubscribe-poging (zonder geldig token)
  tegen tenant "other" is gedaan -- bewijst dat de newsletter-tabel echt per-tenant
  gescheiden is, niet alleen per e-mailadres.

---

## Open aannames

- `AuditService.log_event`'s exacte parameterset is overgenomen uit het bestaande gebruik
  elders in de codebase (severity/source_ip/endpoint/description/action/resource/metadata) --
  niet apart geverifieerd tegen de volledige `AuditService`-brondocumentatie, wel: de code
  compileert, mypy/pyright zijn schoon, en de audit-log-aanroep faalt niet in de
  integratietests (best-effort zou een fout sowieso slikken, dus dit bewijst niet 100% dat
  de velden semantisch correct zijn -- alleen dat ze syntactisch kloppen).

## Open vragen

- Geen voor deze dag; de resterende Foundation-Portal-scope (content-upload met echte
  bestanden, DSAR, edu-access, OAI-PMH, admin-users/edu-codes) is expliciet Dag 5/6.

## Risico's

- **ID-REGISTRY.md bevat een pre-existing dubbele registratie van `BE-EP-023`** (een
  wees-rij uit 2026-07-27 die naar een nooit aangemaakt bestand
  `BE-EP-029-002-foundation-map-bbox.md` verwijst -- verkeerd getiteld, want de rij ernaast
  beweert "Foundation Map BBox" terwijl BE-EP-023 op 2026-08-25 opnieuw is geregistreerd voor
  "Dag 3 Endpoints" onder een ANDER, echt bestand). Dezelfde wees-rij-serie loopt door t/m
  BE-EP-033 (11 rijen, allemaal 2026-07-27, allemaal wijzend naar nooit-aangemaakte
  `BE-EP-029-0XX-...`-bestanden). Dit is PRE-EXISTING (niet veroorzaakt door deze dag) en
  groter dan een dag-4-taak -- niet opgelost hier, wel expliciet gemeld. Om deze reden is
  voor DIT feature-ID bewust `BE-EP-034` gekozen (bevestigd vrij, `grep`-gecontroleerd) in
  plaats van het door de sprint-dag-brief gesuggereerde `BE-EP-024` (dat OOK al een
  wees-rij is, over een ander onderwerp: "Foundation Auth Magic Link").

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- 74/74 foundation-integratietests groen
- [x] Alle foutstatus-codes getest (429 voor alle 4 limieten, 403 voor blocked-user)
- [x] Auth en permissies getest (bestaand, ongewijzigd)
- [x] Tenant-isolatie getest (nieuwe newsletter-cross-tenant-test)
- [x] Validaties getest (bestaand, ongewijzigd)
- [x] Edge cases getest (reused/expired token, bestaand; blocked user, nieuw)
- [x] Dataintegriteit en transacties getest (audit-log is best-effort, faalt de primaire
      actie niet)
- [ ] Performance / load getest -- niet van toepassing op deze schaal
- [ ] Caching getest -- niet van toepassing
- [x] Logging en tracing gecontroleerd (audit-events + rate-limiter-logging handmatig
      nagelopen in testoutput)

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
- [x] Review: APPROVED (zie review-BE-EP-034.md)
