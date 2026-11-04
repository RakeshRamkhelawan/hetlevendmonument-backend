# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-054
- Feature naam: Portal admin auto-promotie bij password-login verwijderd
- Status: Gebouwd, rood->groen bewezen, review pending
- Auteur: Sprint "Week 1 markt-blokkers" -- implementatie-agent Taak C (worktree hlm-wk1-admin-promotie, branch iter/wk1-admin-promotie)
- Reviewer: (nog in te plannen -- Gate 2)
- Datum: 2026-09-24
- Gerelateerde user story / ticket: markt-review 2026-09-24, `docs/reports/market-review-2026-09-24/security.md` rij 28 (HIGH)
- Gerelateerde router / module: `src/core/api/v1/foundation/auth.py`
- Gerelateerde frontend endpoints: portal `Login.tsx` (wachtwoord-tab), portal dev quick-login knoppen
- Gerelateerde database tabellen: `users` (RBAC core), `portal_users`
- Versie: 1.0

---

## Doel en scope

### Doel

Twee privilege-escalatie-deuren in het Foundation Portal password-loginpad dichten:

1. Bij de eerste password-login van een core `User` zonder `PortalUser`-record werd
   automatisch een `PortalUser` aangemaakt met `role=PortalRole.ADMIN`. Elke
   core-gebruiker die op het portal inlogde werd daarmee portal-admin.
2. Een hardcoded identiteitsfallback mapt username `"admin"` of elke string zonder
   `"@"` op `admin@levendmonument.nl`, waardoor het inlogscherm een vaste,
   raadbare admin-identiteit had.

Dit is een directe schending van OWASP Authorization Cheat Sheet, "Enforce Least
Privileges" ("assigning users only the minimum privileges necessary to complete
their job", CWE-272) en "Deny by Default" ("the application should be configured
to deny access by default ... one should be able to explicitly justify why a
specific permission was granted"). Bron: OWASP Cheat Sheet Series, Authorization
Cheat Sheet, opgehaald 2026-09-24,
https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
(de Access Control Cheat Sheet is deprecated en verwijst door naar dit document).

### In scope

- `login_with_password` (POST `/{tenantSlug}/foundation/auth/login`):
  hardcoded fallback verwijderd; lookup is nu exacte email-match; auto-provisioning
  van `PortalUser` met laagste rol (`PortalRole.VISITOR`).
- `quick_login` (POST `/{tenantSlug}/foundation/auth/quick-login`): de else-tak
  die de rol van een BESTAANDE `PortalUser` overschreef met de gevraagde rol
  (default admin) is verwijderd; `security_level` in het JWT wordt nu altijd
  afgeleid van de opgeslagen rol, niet van de gevraagde rol.
- Nieuwe offline unit-tests: `tests/unit/test_foundation_password_login.py`.

### Out of scope

- hcaptcha en per-account throttling op `/auth/login` (aparte aanbeveling in de
  markt-review; eigen taak).
- Frontend-teksten in `portal/src/pages/Login.tsx` die nog het dev-hintje
  "admin of admin@levendmonument.nl" tonen (frontend-taak; het placeholder-hintje
  is dev-only via `isDevHost`).
- De `KNOWN_EXEMPT`-rij voor `auth.py` in
  `tests/architecture/test_no_token_endpoint_skips_the_password.py`. Die tekst
  ("heel auth.py is uitsluitend magic-link-endpoints") is sinds commit e395118f5
  feitelijk verouderd (het bestand bevat nu ook password-login en quick-login) en
  maskeert daardoor ook `quick_login` voor die guard. Bewust NIET aangeraakt: de
  guard zou anders rood gaan op quick-login, dat per ontwerp (e395118f5) geen
  wachtwoord kent. Verdient een eigen vervolgtaak.
- Aanpassen van `scripts/create_admin_user.py` / `scripts/seed_portal_users.py`
  (blijven de expliciete seed-route, zie hieronder).

---

## Build summary

- Nieuw gebouwd: `tests/unit/test_foundation_password_login.py` (10 offline tests).
- Gewijzigd: `src/core/api/v1/foundation/auth.py` (`login_with_password`, `quick_login`).
- Verwijderd: hardcoded fallback `"admin@levendmonument.nl"` in password-login;
  admin-default bij auto-provisioning; rol-overschrijving in quick-login.
- Beinvloede bestaande flows:
  - Password-login: inloggen met kale username `"admin"` werkt alleen nog als er
    een core `User` met letterlijk email `"admin"` bestaat (de dev-seed
    `scripts/create_admin_user.py` maakt die aan -- die flow blijft werken).
  - Quick-login: een bestaand dev-account behoudt zijn opgeslagen rol, ook als de
    knop een andere rol vraagt.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-054 | Geen admin auto-promotie bij password-login | Security fix (endpoint-gedrag) | `src/core/api/v1/foundation/auth.py::login_with_password` | Wijziging | BE-FLW (portal login) |
| BE-SEC-054 | Quick-login overschrijft nooit bestaande rol | Security fix (endpoint-gedrag) | `src/core/api/v1/foundation/auth.py::quick_login` | Wijziging | BE-FLW (dev quick-login) |
| BE-SEC-054 | Offline bewijstests rode->groene invarianten | Test | `tests/unit/test_foundation_password_login.py` | Nieuw | -- |

---

## Detaildocumentatie per artefact

## [BE-SEC-054] login_with_password -- geen auto-promotie, geen fallback

### 1. Type

- Security fix op een bestaand endpoint (BE-EP, password-login voor portal).

### 2. Locatie

- Bestandspad: `src/core/api/v1/foundation/auth.py`
- Functie: `login_with_password`

### 3. Gerelateerde flow

- Portal password-login (staff/beheer), naast de magic-link flow (BE-EP-023).

### 4. Doel

- Core-gebruikers (medewerkers met een `users`-record en wachtwoord) laten
  inloggen op het portal ZONDER hen daarbij portal-rechten toe te kennen die ze
  niet hebben.

### 5. Functionele beschrijving

- De beheerder of medewerker logt in met zijn emailadres en wachtwoord.
- Heeft die persoon al een portal-account, dan geldt de rol die daar staat
  (bijvoorbeeld admin via de seed).
- Heeft die persoon nog geen portal-account, dan wordt er een aangemaakt met de
  rol "bezoeker" (de laagste rol). Verhoging naar curator of admin gebeurt alleen
  via expliciete seeding of de curator-flow, nooit als bijwerking van inloggen.

### 6. Technische beschrijving

- Lookup core user: `select(User).where(User.tenant_id == tenant.id,
  User.email == raw_user)` -- exacte match op de ingevoerde username, geen
  IN-lijst meer met een hardcoded tweede email.
- Wachtwoordverificatie: `jwt_handler.verify_password` (onveranderd); bij
  ongeldige combinatie uniforme 401 ("Ongeldige gebruikersnaam of wachtwoord."),
  geen enumeratie.
- Portal-lookup: `PortalUser.email == core_user.email` (canonieke email uit de
  core-tabel, niet de ruwe invoer).
- Auto-provisioning bij ontbrekend PortalUser: `role=PortalRole.VISITOR`
  (model-default en laagste rol; er is geen aparte "uploader"-rol -- de JWT-scope
  `portal_uploader` dekt de upload-capability, de rol blijft visitor).
- JWT: `role`-claim en `security_level` worden afgeleid van de opgeslagen/
  aangemaakte `PortalUser.role` (onveranderd mechaniek).

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: geen (dit IS het inlogendpoint); rate limit
  `require_portal_auth_rate_limit` blijft van kracht.
- Vereiste rol / scope: n.v.t.
- Tenant-isolatie: lookup strikt binnen `public_tenant_scope(tenantSlug)`.
- Feature flag: geen.

### 8. Request-specificatie

- Methode: POST
- Route: `/{tenantSlug}/foundation/auth/login`
- Request body: `PasswordLoginRequest` (`username` 1-255, `password` 1-128)

### 9. Response-specificatie

- Successtatus: 200, `TokenResponse` (access_token, token_type, user{email, role})
- Foutstatussen: 401 (onbekende user / inactief / fout wachtwoord), 429 (rate limit)

### 10. Validaties en constraints

- Pydantic lengte-validatie op username/password (onveranderd).
- Username wordt alleen `.strip()`-genormaliseerd; er is geen case-folding of
  domein-aanvulling meer.

### 11. Business rules

- R1: een login-side-effect mag nooit een hogere rol toekennen dan VISITOR.
- R2: admin/curator portal-rollen ontstaan uitsluitend via
  `scripts/seed_portal_users.py` (expliciet, door een operator gedraaid) of via
  de curator-flow; NIET via inloggen.
- R3: geen hardcoded productie-email meer in de codebase als identiteitsfallback.

### 12. Afhankelijkheden

- `public_tenant_scope`, `jwt_handler`, `AuditService` (best_effort audit),
  `PortalUser`/`PortalRole`, RBAC `User`.

### 13. Foutafhandeling

- 401: onbekende gebruikersnaam, inactieve core user, of fout wachtwoord --
  bewust identieke melding (geen enumeratie).
- 429: rate limit (5/min/IP, onveranderd).

### 14. Transacties en data-integriteit

- Provisioning + JWT-uitgifte in dezelfde sessie/transactie als voorheen
  (`session.add` + `flush`).

### 15. Telemetry / logging / tracing

- Bestaand best_effort audit-event `portal_password_login` blijft; er is geen
  apart "provisioning"-audit-event toegevoegd (open punt, laag risico omdat de
  aangemaakte rol nu altijd VISITOR is).

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- AC1: eerste password-login van een core User zonder PortalUser maakt een
  PortalUser met rol VISITOR aan (gemeten: test
  `test_first_login_provisions_visitor_not_admin`).
- AC2: de lookup-query bevat nooit `admin@levendmonument.nl` tenzij de
  aanroeper dat letterlijk invoert (test
  `test_lookup_query_contains_no_hardcoded_admin_email`).
- AC3: username `admin` (zonder core user met email `admin`) geeft 401, ook als
  `admin@levendmonument.nl` wel bestaat (test
  `test_bare_admin_username_does_not_resolve_to_fallback_email`).
- AC4: een via seed aangemaakte portal-admin logt gewoon in en krijgt rol
  "admin" in token en response (test `test_seeded_admin_logs_in_as_admin`).
- AC5: quick-login in productie geeft 403 (test
  `test_quick_login_forbidden_in_production`).
- AC6: quick-login overschrijft de rol van een bestaande PortalUser nooit
  (test `test_quick_login_does_not_promote_existing_user_to_admin`).

### 18. Integratoruitleg

- Log in met het volledige emailadres van je core-account; kale aliassen zoals
  "admin" werken alleen als zo'n account letterlijk zo heet.
- Een eerste login maakt hooguit een bezoekers-account aan; admin-rechten krijg
  je alleen via de beheerder (seed/curator-flow).
- De dev-knoppen op de loginpagina (quick-login) werken alleen buiten productie
  en veranderen nooit de rol van een bestaand account.

### 19. Trainingssamenvatting

- Actor: medewerker met core-account.
- Voorwaarde: actieve core `User` met geldig wachtwoord, binnen tenant-scope.
- Actie (request): POST `/foundation/auth/login` met email + wachtwoord.
- Systeemverwerking: exacte email-lookup, wachtwoordverificatie, portal-account
  laden of provisioneren met laagste rol, JWT met opgeslagen rol.
- Succesrespons: 200 + bearer-token met rol uit de portal_users-tabel.
- Foutrespons: 401 uniform bij elke credential-mismatch; 429 bij rate limit.
- Uitzonderingen: quick-login-endpoint alleen buiten productie; overschrijft
  bestaande rollen nooit.

---

## Vervangende route voor de eerste admin (seed, geen login-side-effect)

De eerste portal-admin ontstaat NIET meer via inloggen. Expliciete routes:

1. `python scripts/seed_portal_users.py` -- maakt `admin@levendmonument.nl`
   (ADMIN), `curator@levendmonument.nl` (CURATOR) en `bezoeker@levendmonument.nl`
   (VISITOR) aan in `portal_users` plus een 7-dagen magic link per account.
2. `python scripts/create_admin_user.py` -- maakt de core `User` met wachtwoord
   aan (voor password-login) EN de bijbehorende portal_users-rij met ADMIN-rol.

Beide zijn operator-acties met de rol expliciet in het script/config, conform
OWASP "explicitly justify why a specific permission was granted".

---

## Rood->groen bewijs (gemeten)

Omgeving: project-venv `het-levend-monument/.venv`, pytest met schone
GIT_CONFIG-env (de shell zet GIT_CONFIG_VALUE_0 leeg wat git-subprocessen in
tests breekt; los van deze fix).

Voor de fix (rode fase, commit-staat HEAD 560d21f5c):

```text
6 failed, 4 passed in 2.42s
FAILED test_first_login_provisions_visitor_not_admin        (rol was admin)
FAILED test_first_login_never_provisions_curator_or_admin   (rol was admin)
FAILED test_lookup_query_contains_no_hardcoded_admin_email  (fallback in IN-lijst)
FAILED test_bare_admin_username_does_not_resolve_to_fallback_email (login slaagde)
FAILED test_username_without_at_sign_has_no_fallback        (login slaagde)
FAILED test_quick_login_does_not_promote_existing_user_to_admin (rol overschreven)
```

Na de fix (groene fase):

```text
10 passed in 3.59s
```

Regressie (met fix actief):

- `pytest tests/unit/ -k foundation`: 245 passed, 3 skipped, 2 failed + 2 errors --
  alle vier aangetoond pre-existing op HEAD (contact ImportError, donations ERROR,
  settings test_get_settings_not_found, datetime_conformance newsletter.py:183/315).
- `pytest tests/architecture/` (in twee batches): 995 passed, 20 failed --
  exact dezelfde 20 IDs falen op HEAD zonder de fix (0 nieuwe).
- ruff: `All checks passed!` op beide gewijzigde bestanden.
- mypy: 6 errors voor en na de fix, identiek; allemaal "untyped decorator"-
  artifacten van `--follow-imports=skip` op FastAPI-decorators, geen nieuwe.
- ASCII-only op beide bestanden geverifieerd; geen `datetime.now()`/ `utcnow()`
  in auth.py (gebruikt `utc_now()` uit `datetime_utils`).

---

## Open aannames

- "Laagste rol" is `PortalRole.VISITOR`: de enum kent ADMIN/CURATOR/TEACHER/
  STUDENT/VISITOR; er bestaat geen "uploader"-rol (de JWT-scope heet
  `portal_uploader`, dat is een scope, geen rol).
- Quick-login mag buiten productie nog steeds een Nieuw dev-account met de
  gevraagde rol aanmaken (inclusief admin) -- dat is de bewuste dev-flow uit
  commit e395118f5 en geldt niet als "promotie" omdat er geen bestaand account
  wordt verhoogd. Als de review ook eerste-aanmaak via quick-login wil dichten,
  is dat een kleine vervolgwijziging met frontend-impact (dev-knop
  "Administrator").

## Open vragen

- Moet de frontend dev-placeholder "admin of admin@levendmonument.nl" in
  `Login.tsx` worden aangepast? (Frontend-taak; backend accepteert nu alleen
  exacte emails.)
- Moet de `KNOWN_EXEMPT`-tekst voor auth.py in de OP-61-guard worden
  geactualiseerd/verfijnd (zie Out of scope)?

## Risico's

- Laag: bestaande core-gebruikers zonder PortalUser die eerder "gratis" admin
  werden, krijgen nu VISITOR-rechten. Dat is het beoogde effect, maar wie daar
  stil op vertrouwde moet eenmalig via de seed worden gepromoveerd.
- De portal e2e/dev-workflow die quick-login('admin') gebruikt op een BESTAAND
  bezoekers-account krijgt nu de opgeslagen rol terug; in de praktijk gebruiken
  de dev-knoppen vaste accounts per rol, dus geen gedragsverandering daar.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path): seeded admin login, nieuwe user login
- [x] Alle foutstatus-codes getest: 401 (3 varianten), 403 (quick-login prod)
- [x] Auth en permissies getest: geen auto-admin, geen promotie via quick-login
- [ ] Tenant-isolatie getest: niet expliciet (lookup via public_tenant_scope,
  ongewijzigd mechaniek)
- [x] Validaties getest (ongeldige invoer): onbekende user 401
- [x] Edge cases getest: kale username, username zonder "@", bestaande vs nieuwe user
- [x] Data-integriteit en transacties getest: provisioning via add+flush, fake sessie
- [ ] Performance / load: n.v.t. (geen nieuwe queries; een IN-lijst minder)
- [ ] Caching: n.v.t.
- [x] Logging en tracing gecontroleerd: bestaand audit-pad ongemoeid

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar (en getest: rood->groen)
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd (offline; integratie-DB niet beschikbaar in deze omgeving)
- [ ] Review door reviewer-prompt: pending (Gate 2)

---

*ID-REGISTRY.md is bewust NIET bijgewerkt in deze branch (parallelle sprint-
worktrees); de registratie gebeurt bij de merge-coordinatie. BE-SEC-054 is op
2026-09-24 geverifieerd vrij in zowel ID-REGISTRY.md als de volledige docs-boom.*
