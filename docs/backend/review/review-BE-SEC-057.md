# Review BE-SEC-057: Edu-codes autorisatie (curator/admin JWT op /edu/codes)

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; geen voorkennis van de implementatie; alles zelf geverifieerd met commando's in de worktree (read-only), niet op aannames. Red Team Mandaat toegepast: uitgegaan van technische schuld tot het tegendeel bewezen was.
**Datum:** 2026-09-24
**Scope:** branch `iter/wk1-edu-codes-auth`, commit `d6f0425ab`, worktree `hlm-wk1-edu-codes-auth` — `src/core/api/v1/foundation/edu.py`, `src/core/shared/public_registry.py`, `tests/integration/api/v1/foundation/test_edu.py`, `tests/unit/test_foundation_edu_session.py`, spec `docs/backend/features/BE-SEC-057-edu-codes-autorisatie.md`. Referentie gelezen: `dependencies.py` (require_curator/require_portal_user), `router.py`, `admin/curatie.py`, `tenant_middleware.py`, ADR-029 r.191-201 en r.230-235, model `EducationalAccess`, `auth.py` (quick-login).

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS — geen HIGH- of MEDIUM-bevindingen. De fix doet precies wat de klacht vereist: alle drie de `/edu/codes`-endpoints vereisen nu een cryptografisch gevalideerd portal-JWT met rol curator/admin, gebonden aan de pad-tenant, en de TenantMiddleware laat `/edu/codes*` niet meer tokenloos door (fail-closed geverifieerd met eigen matcher-run). Tests zijn echte gedragstests door de volledige middleware-stack tegen echte Postgres, rood-voor-fix logisch bewezen uit de pre-fix code in de diff zelf. Drie LOW's: (1) de registry-matcher is substring-gebaseerd en niet segment-geankerd, waardoor toekomstige `/edu/sessionsX`- of `/edu/contentY`-routes stilletjes publiek worden; (2) twee non-ASCII-tekens in de nieuwe spec; (3) de spec-aanname over de curator-UI is onbewezen — er is in deze repo helemaal geen caller van `/edu/codes` gevonden.

## C. Samenvatting

Verificatie, alles zelf gedraaid vanuit de worktree met de hoofd-repo venv (import-pad geverifieerd: `src` resolveert naar de worktree):

- **Integratie: 33/33 groen** (`tests/integration/api/v1/foundation/test_edu.py`, 49.2s, echte Postgres op 127.0.0.1:5455 via verplichte `SANSKRITISETU_TEST_DATABASE_URL`, volledige middleware-stack actief in de test-app — TenantMiddleware zichtbaar in de startup-logs). Exact de commit-claim (26 baseline + 7 nieuw).
- **Unit: 28/28 groen** (`test_foundation_edu_session.py` + `test_public_endpoint_registry.py`, 2.7s).
- **Gerichte regressie: 75 passed, 14 skipped** (foundation sitemap/oai-pmh registry-tests, drie tenant-middleware-testbestanden, twee architectuurtests incl. `test_public_registry_prefixes_are_anchored` en `test_dsm016_no_tenancy_auth_circular`).
- **Ruff schoon** op alle vier de gewijzigde bestanden.
- **Mypy: 0 errors in de gewijzigde bestanden**; 16 errors in 4 onaangeroerde modules (o.a. `curatie.py:823`), conform de pre-existing-claim in het commitbericht.
- **Pre-existing collection-errors bevestigd** in `test_foundation_contact.py` en `test_foundation_donations.py`: `ImportError: cannot import name '_get_tenant_donations'` — ongerelateerd aan deze diff (raakt die modules niet).
- **Eigen matcher-run** op `PublicEndpointRegistry.is_public` met 13 concrete paden: alle security-relevante gevallen correct (zie D.3).
- Import-linter niet kunnen draaien (`lint_imports` ontbreekt in de venv); ADR-033 handmatig geverifieerd (zie D.5).

De rood-voor-fix-claim (1 unit + 5 integratie rood) heb ik niet uitgevoerd — dat vereist code-wijziging en de worktree is read-only — maar hij is **logisch bewezen uit de diff zelf**: pre-fix hadden de drie handlers geen enkele auth-dependency en de registry liet elk `/foundation/edu/`-pad tokenloos door; een anonieme POST zou dus 201 hebben gegeven waar de tests 401 eisen.

## D. Bevindingen per categorie (samengevat)

1. **Security** — Kern is sluitend. (a) Alle drie de endpoints afgeschermd: `@router.post/get/delete` op `/edu/codes` resp. `/edu/codes/{id}` hebben alle drie `Depends(require_curator)`; grep op alle routes in `edu.py` toont exact 8 edu-routes (3x session, 2x content, 3x codes) — geen vierde verborgen route; repo-brede grep op `edu/codes` toont geen tweede router. (b) Tenant-isolatie is driedubbel: JWT-tenant wordt door de middleware in de ContextVar gezet (fail-secure auto-filter als achtervang), `require_portal_user` laadt de PortalUser alleen als `id + token-tenant` matchen, en de endpoint-check `current_user.tenant_id != tenant.id -> 403` is de harde grens — beide richtingen integratie-getest (curator t2 op slug t1 én curator t1 op slug t2, alle drie de methoden). (c) Registry-versmalling klopt: `/edu/session` en `/edu/content*` blijven publiek (code-invoer leerlingen en cookie-flow werken), `/edu/codes*` valt fail-closed buiten de publieke set. (f) Foutcodes uniform zonder enumeratie van betekenis: anoniem/ongeldig token/alleen-edu-cookie -> 401; visitor-rol/cross-tenant -> 403; onbekende slug -> 404. Slug-existence is al publiek via de openbare content-endpoints, dus het 404/403-onderscheid lekt niets nieuws.
2. **Correctheid** — Dependency-volgorde in de handlers is consistent met het `curatie.py`-patroon (11 endpoints, zelfde vorm). De tenant-check staat als eerste statement binnen `public_tenant_scope`, vóór elke query — geen oracle op code-IDs voor cross-tenant callers (403 komt vóór de 404-lookup bij DELETE). De edu-cookie-test bewijst dat een geldige teacher-sessie-cookie géén toegang geeft tot code-beheer (401) — de twee auth-werelden (cookie vs JWT) zijn correct gescheiden.
3. **Matcher-semantiek (eigen run)** — `/ketikoti/foundation/edu/codes`, `/edu/codes/12`, `/edu/codes/` (trailing slash), `/api/v1/ketikoti/foundation/edu/codes`, `/ketikoti/foundation/EDU/codes`, `/ketikoti/foundation/edu` en `/edu/` -> allemaal niet publiek (fail-closed); `/edu/session`, `/edu/content`, `/edu/content/42` -> publiek zoals bedoeld; reserved-slug `/static/foundation/edu/session` -> niet publiek (OP-202-botsing intact). **Artefact:** `/edu/sessions` (meervoud) en `/edu/contentevil` matchen ook -> True. Vandaag ongevaarlijk (geen zulke routes), maar het is substring-matching zonder segmentgrens — terwijl hetzelfde bestand voor `PUBLIC_PREFIXES` wél `_matches_prefix` met segmentanker heeft (ADR-036 OP-202). LOW, zie E.
4. **Tests** — Echte gedragstests, geen tautologieën: echte JWT's via `jwt_handler.create_access_token`, echte Postgres, volledige middleware-stack, asserts op statuscodes én op gedrag (mint -> 201 met 8-karakter code, list bevat id, revoke -> 204, id verdwenen uit actieve lijst). De twee cross-tenant-tests dekken beide richtingen; de cookie-test dekt de auth-wereld-scheiding. De unit-registry-test assert expliciet dat `/api/v1/{slug}/...edu/codes` óók dicht valt. Geen gemis gevonden dat een HIGH zou hebben gevangen.
5. **Architectuur (ADR-033)** — Handmatig geverifieerd (import-linter niet in venv): `edu.py` importeert `require_curator` via de `dependencies.py`-facade en voegt alleen `PortalUser` uit `src.core.models.foundation_content` toe als directe import — identiek aan `curatie.py:19` (dat PortalUser al direct importeert). Geen nieuwe directe service-/governance-imports in de router-laag. Geen contract-schending.
6. **Regels** — Geen `datetime.now()`/`utcnow()` in de diff (gescand). ASCII-scan op alle toegevoegde regels: 2x `ó` ("vóór"), beide in de spec-md, niet in code/comments/logs — de NOOIT-regel dekt docs formeel niet, maar de repo-conventie is streng; LOW. Commitbericht is eerlijk over pre-existing failures en die claim bleek bij verificatie accuraat.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| LOW | `public_registry.py:160-163` | De foundation-tak van `is_public` matcht op kale substring (`"/foundation/edu/session" in path`), niet op segmentgrens — terwijl `PUBLIC_PREFIXES` in hetzelfde bestand wél segment-geankerd is (`_matches_prefix`, ADR-036 OP-202). Elke toekomstige route onder `/edu/session*` of `/edu/content*` (bijv. `/edu/content-upload`, `/edu/sessions`) wordt bij toevoeging stilletjes publiek, zonder dat een test rood wordt. Dit is precies het mechanisme dat het oorspronkelijke gat (`/foundation/edu/` dektte alles) mogelijk maakte; de fix versmalt de set maar laat het risico-mechanisme staan. | Hergebruik het segment-anker: match op `path == anchor or path.startswith(anchor + "/")` met anchors `/foundation/edu/session` en `/foundation/edu/content`, en voeg een architectuurtest toe die faalt zodra een nieuwe edu-route publiek matcht zonder expliciete registratie. |
| LOW | `docs/backend/features/BE-SEC-057-edu-codes-autorisatie.md` ("In scope") | 2x non-ASCII teken `ó` ("vóór") in de nieuwe spec. Niet in code/comments/logs, dus formeel buiten de NOOIT-regel, maar het breekt de ASCII-conventie van nieuwe docs en kan repo-scanners triggeren. | Vervang door "voordat" / "eerder". |
| LOW | Spec, sectie "Open aannames" | De aanname "de curator-UI stuurt al een Authorization-header mee" is onbewezen en sterker geformuleerd dan het bewijs: repo-grep op `edu/codes` in `frontend/src` levert **nul** callers op — er is in deze repo helemaal geen frontend-aanroep van deze endpoints. De kans dat een legitieme caller breekt is daarmee klein, maar als de portal-curator-UI elders leeft en anoniem aanroept, breekt die bij deploy. | Herformuleer tot: "geen enkele caller van /edu/codes gevonden in deze repo (grep frontend/src = 0 hits); externe portal-UI verifiëren vóór merge naar main." |

## F. Ontbrekende items

- Segment-geankerde edu-matcher + architectuurtest (dekkingsgat voor toekomstige routes; zie E-LOW-1).
- Import-linter-run kon lokaal niet (module `lint_imports` ontbreekt in de hoofd-repo venv); de ADR-033-conformatie is handmatig geverifieerd. Aanbeveling: Contract 1-3 draaien in CI op deze branch vóór merge, zoals de pipeline dat al doet.
- Audit-spoor op code-beheer: mint/list/revoke schrijven geen `AuditService`-event. Pre-existing (niet door deze fix veroorzaakt of verergerd), maar nu de PII-lijst achter een rol zit is "welke curator keek wanneer naar docent-e-mails" een logische AVG-vervolgvraag. Als follow-up benoemen, niet als blokker.

## G. Verbeterde codevoorstellen

`public_registry.py` (segment-anker voor de edu-regels, hergebruik van het bestaande patroon):

```python
# In plaats van twee kale substring-checks:
_edu_public_anchors = ("/foundation/edu/session", "/foundation/edu/content")
for anchor in _edu_public_anchors:
    idx = path.find(anchor)
    if idx != -1:
        end = idx + len(anchor)
        if len(path) == end or path[end] == "/":
            return True
```

Plus een architectuurtest die alle `@router.*`-routes in `edu.py` uitleest en assert dat elke niet-`session`/`content`-route niet publiek is — dan kan een toekomstige route nooit ongemerkt in de publieke set vallen.

## H. Release-oordelen

- Bouw/implementatie: **ja** — chirurgisch, patroon-conform (`curatie.py`), driedubbele tenant-isolatie, fail-closed registry.
- QA/geautomatiseerd testen: **ja** — 33 integratie + 28 unit + 75 regressie groen, zelf gedraaid; rood-voor-fix logisch bewezen uit de pre-fix code; pre-existing failures correct als zodanig benoemd en geverifieerd.
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja, na twee kleine correcties** (ASCII-tekens; scherpere formulering van de frontend-aanname). De scope-beperking (geen docent-self-service) is verdedigbaar en correct gemotiveerd: `EducationalAccess` heeft inderdaad geen creator-FK (kolommen zelf gelezen: id, tenant_id, code_hash, email, role, is_active, expires_at, created_at), en geen enkele auth-flow geeft een teacher-JWT uit (`PortalRole.TEACHER` bestaat in de enum, maar magic-link en quick-login kennen alleen visitor/curator/admin; quick-login is bovendien disabled in productie). ADR-029 r.230-235 beschrijft een concept dat in de code niet bestaat; een security-hotfix mag geen schema-migratie + loginflow smokkelen.

## Wat wél klopt

- Alle drie de endpoints hebben `Depends(require_curator)` + expliciete tenant-binding, als eerste statement vóór elke query; exact het `curatie.py`-patroon dat 11 admin-endpoints al gebruiken.
- De registry-versmalling is chirurgisch en fail-closed: cookie-flow (`/edu/session`, `/edu/content*`) blijft werken, `/edu/codes*` vereist een token al in de middleware; eigen matcher-run met 13 paden bevestigt elk security-relevant geval, inclusief trailing-slash, `/api/v1`-variant, hoofdletters en de reserved-slug-botsing.
- Tenant-isolatie is driedubbel (middleware-ContextVar met fail-secure auto-filter, `require_portal_user` DB-binding op token-tenant, expliciete endpoint-check) en integratie-getest in beide richtingen op alle drie de methoden.
- De twee auth-werelden zijn bewezen gescheiden: een geldige edu-sessie-cookie van een teacher geeft 401 op code-beheer (`test_edu_session_cookie_grants_no_codes_access`, groen gedraaid).
- Foutcodes zijn uniform en lekken niets: 401 voor afwezig/ongeldig token, 403 voor rol of vreemde tenant, 404 alleen voor onbekende slug/code-id; geen existence-oracle van betekenis.
- Tests zijn echte gedragstests door de volledige middleware-stack tegen echte Postgres (33/33 zelf gedraaid), met gedrags-asserts (code-lengte, lijst-inhoud, revoke-effect) en niet alleen statuscodes.
- Ruff schoon; mypy 0 nieuwe errors (16 pre-existing elders, claim geverifieerd); geen `datetime.now()`; de pre-existing collection-errors en falende `test_content.py`-tests uit het commitbericht zijn echt pre-existing (ImportError op `_get_tenant_donations`, ongeraakt door deze diff).
- Het commitbericht en de spec zijn ongewoon eerlijk over wat niet is gedaan (docent-self-service, frontend-aanname, pre-existing failures) — dat maakte deze review sneller, en geen van die open deuren bleek bij controle een verborgen defect.

## Devil's Advocate — waarom faalt deze oplossing in de toekomst?

1. **De substring-matcher is het originele gat in verkleinde vorm.** Het beveiligingsincident ontstond doordat `"/foundation/edu/" in path` elke nieuwe edu-route automatisch publiek maakte. De fix vervangt dat door twee smallere substrings — maar het mechanisme "nieuwe route erft stilletjes publiciteit" blijft bestaan. De eerste PR die `/edu/content-upload` of `/edu/sessions` toevoegt opent die route zonder JWT, en geen enkele test wordt rood, want de nieuwe unit-test assert alleen `codes`-paden. Het anker uit `_matches_prefix` ligt letterlijk 50 regels hoger in hetzelfde bestand; dat het hier niet is toegepast is een gemiste kans om de oorzaak (niet alleen het symptoom) te dichten.
2. **De auth leeft op twee lagen die onafhankelijk kunnen verspringen.** Middleware (registry) en endpoint (`Depends`) moeten allebei kloppen. Vandaag bewaken de integratietests het koppelvlak via de echte stack — maar zodra iemand de integratietests "versnelt" met een gemockte middleware of de dependency inline uitbreidt, is er geen vangnet meer dat de combinatie bewaakt. De huidige dekking is goed maar breekbaar door ogenschijnlijk onschuldige test-refactors.
3. **Het uitgestelde docent-self-service creëert precies de druk die deze fix moet voorkomen.** ADR-029 belooft docenten eigen codes; tot die feature er is, mint een curator namens elke docent. De operationele shortcut die dan ontstaat — een gedeeld curator-account, of quick-login in staging "even" aan — ondermijnt de rolscheiding die nu net is dichtgetimmerd. Erger: `PortalRole.TEACHER` bestaat al in de enum. De eerste developer die teacher-registratie bouwt en "docenten moeten hun eigen codes beheren" implementeert door `TEACHER` aan `require_curator` toe te voegen — zonder creator-binding — geeft elke docent van de tenant de volledige PII-lijst van alle collega-docenten plus revoke-rechten. Dat is een groter lek dan het anonieme gat dat hier is gedicht, en het ligt op de loer omdat de scope-beperking (terecht) geen creator-FK heeft toegevoegd. De follow-up-feature moet de creator-FK als acceptatiecriterium krijgen, niet als optionele verdieping.
4. **Er is geen audit-spoor op het nieuwe privilege.** Mint, list en revoke schrijven geen audit-event. Bij het eerste AVG-verzoek van een docent ("wie heeft mijn e-mailadres opgevraagd?") is het antwoord: onbekend. De middleware logt AUTH FAIL, maar succesvolle PII-reads door legitieme curatoren zijn onzichtbaar. Zodra de eerste tenant met meerdere curatoren live is, is dat een compliance-gat dat niemand meer kan dichten — de historische data bestaat dan gewoon niet.
5. **De "geen caller gevonden"-constatering is ook een waarschuwing.** Er is in deze repo geen enkele frontend-aanroep van `/edu/codes`. Dat betekent dat deze endpoints mogelijk alleen door toekomstige of externe UI worden gebruikt — code zonder in-repo-consument is code zonder regressie-signaal. Als de echte curator-UI elders leeft en deze routes anoniem aanriep (het werkte immers), dan breekt die bij deploy en is de "fix" voor die gebruiker een outage. De spec benoemt het als open aanname; voor merge naar `main` moet die aanname een bewijs zijn.

Geen van deze punten blokkeert de merge: de acute deur is dicht, bewezen dicht, en de rest is geplande vervolgarbeid. Maar punt 1 en 3 verdienen een eigen plek in de sprint-tracker voordat dit inproductie-hard wordt.


---

<!-- MERGE-NOTE (sync 2026): de ID BE-SEC-057 bestaat in beide forks met VERSCHILLENDE inhoud. Boven: onze review (edu-codes autorisatie, 2026-09-24). Onder: upstream review (/refresh-cookie, 2026-10-05). Bij toekomstige opruiming een van beide hernummeren. -->

# Review BE-SEC-057

STATUS: APPROVED

Reviewers (subagents, 2026-10-05): code-reviewer GO, security-reviewer GO.

- Geen verruiming: de route had de cookie-terugval al; rate limit blijft; het tokensoort wordt
  nog gecontroleerd in `oauth2_service.refresh_access_token`.
- Geen nieuw orakel: ontbrekend en ongeldig token geven allebei 401.
- LOW (niet door deze wijziging): cross-site POST naar `/refresh` gebruikt het cookie; SameSite
  houdt dat tegen, het antwoord is cross-origin niet leesbaar.
