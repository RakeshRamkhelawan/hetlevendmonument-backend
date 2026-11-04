# Review BE-SEC-054: geen admin auto-promotie bij portal password-login

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; read-only gereviewd in worktree `hlm-wk1-admin-promotie`, branch `iter/wk1-admin-promotie`, commit `503a5a6a1`. Alle claims zelf met commando's geverifieerd, niet op aannames.
**Datum:** 2026-09-24
**Scope:** `git show 503a5a6a1`, huidige `src/core/api/v1/foundation/auth.py` (549 regels, volledig gelezen), `dependencies.py` (rolhandhaving), `scripts/seed_portal_users.py`, `scripts/create_admin_user.py`, quick-login guard uit `e395118f5` (via `git show`), `tests/unit/test_foundation_password_login.py`, `tests/architecture/test_no_token_endpoint_skips_the_password.py` (KNOWN_EXEMPT), spec `docs/backend/features/BE-SEC-054-portal-admin-auto-promotie.md`, repo-brede grep op `admin@levendmonument.nl`.

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS -- de twee aangemelde privilege-escalatie-deuren zijn objectief gedicht en de tests zijn echte gedragstests (de fake sessie evalueert de werkelijke gecompileerde WHERE-bind-parameters en de JWT-rol-claim wordt met de echte `jwt_handler` gedecodeerd). Geen HIGH-bevindingen. Wel twee MEDIUM-gaps die geen merge-blokker zijn maar een expliciete follow-up verdienen: (1) de KNOWN_EXEMPT-vrijstelling voor `auth.py` in de OP-61-guard is feitelijk onjuist en maskeert `quick_login` (tokenuitgifte zonder wachtwoord); (2) de quick-login productie-guard is een exacte string-match op `"production"` terwijl de repo-deployments ook `ENVIRONMENT=blue/green/staging` kennen -- fail-open bij elke afwijkende waarde.

## C. Samenvatting

Verificatie zelf gedraaid in de worktree met de project-venv:

- `pytest tests/unit/test_foundation_password_login.py`: **10/10 groen** (1.09s) -- zoals de commit claimt.
- Regressie `pytest tests/unit -k foundation`: **245 passed, 2 failed + 3 errors** -- alle vijf gereproduceerd en bevestigd pre-existing (`newsletter.py:183/315` datetime, `test_get_settings_not_found`, contact ImportError, donations ERROR); geen enkele raakt `auth.py`.
- `pytest tests/architecture/test_no_token_endpoint_skips_the_password.py`: 4 failures in de standaard-shell bleken **omgevingsartefact** (`GIT_CONFIG_VALUE_0` leeg -> git rc=128); met schone env **6/6 groen** -- precies zoals de spec onder "Rood->groen bewijs" beschrijft.
- `ruff check` op beide gewijzigde bestanden: **schoon**. ASCII-only geverifieerd (0 non-ASCII tekens); geen `datetime.now()`/`utcnow()` in de gewijzigde bestanden.
- Cruciale architectuur-constatering: autorisatie beslist op de **DB-rol** (`require_admin`/`require_curator` lezen `user.role` uit een vers geladen `PortalUser`, `dependencies.py:335-355`), niet op de JWT-claim. Daarmee is de fix op provisioning-niveau daadwerkelijk effectief: een token met een admin-claim zonder admin-rij in de DB geeft geen rechten.

Adversarial checklist (opdracht a-f):

- **(a) Restpaden naar admin:** alle provisioning in `auth.py` gelezen. `request_magic_link` en `verify_magic_link` provisioneren niet (alleen bestaande users, rol uit DB). `login_with_password` provisioneert VISITOR. `quick_login` kan bij eerste aanmaak nog een ADMIN-account maken, maar alleen buiten productie en nooit overschrijvend. Repo-breed (`grep PortalUser(` over `src/`) bestaan er geen andere aanmaak-paden. Geen resterend onbevoegd admin-pad gevonden.
- **(b) Default-rol VISITOR:** klopt. `PortalRole` kent ADMIN/CURATOR/TEACHER/STUDENT/VISITOR; TEACHER/STUDENT zijn edu-rollen via `EducationalAccess`, geen portal-rollen. VISITOR is de laagste. De flow breekt niet: de JWT-scope `portal_uploader` wordt rol-onafhankelijk gegeven en `upload.py:106` gebruikt `require_portal_user` (elke niet-geblokkeerde rol mag uploaden). Een verse staff-login wordt VISITOR en kan curatie-endpoints niet bereiken (403 via `require_curator`) -- dat is het beoogde effect.
- **(c) Verwijderde fallback:** repo-brede grep toont drie restanten: `src/core/api/auth/router_login.py:196-199` (de CORE OAuth2-login heeft nog steeds exact hetzelfde `"admin" -> admin@levendmonument.nl`-patroon, plus mapping van elke string zonder `@` naar `<naam>@levendmonument.nl`), `portal/src/pages/Login.tsx:268` (dev-placeholder; door de spec bewust als frontend-taak uit-scope gezet) en `scripts/create_admin_user.py:39,69-72` (seedt een core user met letterlijk email `"admin"` + portal-user `"admin"`/ADMIN). Zie issue-register MEDIUM-3/LOW.
- **(d) Quick-login:** de rol-overschrijving is verwijderd (diff-regels: geen else-tak meer; `sec_level` volgt nu de opgeslagen rol). De productie-guard uit `e395118f5` is geverifieerd ongemoeid (`git show e395118f5 -- auth.py`). Maar de guard faalt open bij `ENVIRONMENT != "production"` -- zie MEDIUM-2.
- **(e) Tests:** echt. `TestNoHardcodedAdminFallback` inspecteert de gecompileerde bind-params van het echte statement (een terugkeer van de IN-lijst wordt rood); `_decode_role` decodeert het echte JWT met de echte handler en assert de `role`-claim; quick-login-tests asserten zowel DB-staat als token. Rood-fase op HEAD door de schrijver gedocumenteerd; de teststructuren zijn zodanig dat ze op HEAD inderdaad falen (IN-lijst-match, ADMIN-provisioning).
- **(f) KNOWN_EXEMPT:** de claim "heel auth.py is uitsluitend magic-link-endpoints ... geen enkele functie erin gebruikt of behoort een wachtwoord te gebruiken" (`test_no_token_endpoint_skips_the_password.py:90-105`) is **onjuist** -- het bestand bevat `login_with_password` (wachtwoord) en `quick_login` (token ZONDER wachtwoord). Dat was al zo sinds `e395118f5`; deze commit maakt het niet erger, maar bevestigt dat de vrijstelling precies het endpoint maskeert dat deze sprint onder vuur lag. De spec benoemt dit eerlijk als out-of-scope; er ontbreekt alleen een follow-up-ID.

## D. Bevindingen per categorie (samengevat)

1. **Security** -- Kernfix correct en compleet binnen scope: exacte email-match, VISITOR-provisioning, geen rol-overschrijving in quick-login, uniforme 401 (geen enumeratie), rate limit ongemoeid, autorisatie op DB-rol. Restrisico's: quick-login guard fail-open (MEDIUM-2), hetzelfde fallback-patroon leeft voort in de core-login `router_login.py` (MEDIUM-3), seed-script met bare-`"admin"`-account en hardcoded wachtwoord `Tester01` (LOW), geen `is_blocked`-check in `login_with_password` (LOW, afgedekt door dependency-laag).
2. **Correctheid** -- `sec_level`-afleiding is nu consistent over alle drie de flows (magic-link, password, quick-login: identieke mapping). `PortalUser`-lookup gebruikt de canonieke `core_user.email` i.p.v. ruwe invoer -- goed. Geen case-folding: fail-closed, bewust gedocumenteerd in spec-10.
3. **Architectuur** -- Wijziging blijft binnen het bestand; geen nieuwe imports, geen facade-schending. De duplicate `sec_level`-formule staat nu drie keer in het bestand (regels 301, 412, 515) -- geen blokkade, maar een kandidaat-helper.
4. **Tests** -- 10 betekenisvolle offline tests met rood->groen-bewijs; fake-sessie-aanpak is sterk omdat hij de echte SQLAlchemy-bind-parameters evalueert in plaats van gemockte returns te asserten. Gaten: geen test dat `is_blocked` op password-login afgedwongen wordt (die check ontbreekt ook in de code); geen integratietest tegen echte DB (in deze omgeving niet beschikbaar -- spec is hier eerlijk over).
5. **Regels** -- ASCII-only geverifieerd (0 non-ASCII in beide bestanden), `utc_now()` uit `datetime_utils` i.p.v. `datetime.now()`, ruff schoon, audit via `best_effort` ongemoeid. Commit-message en spec zijn ongewoon eerlijk over de grenzen van de fix.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `tests/architecture/test_no_token_endpoint_skips_the_password.py:90-106` | KNOWN_EXEMPT vrijstelt heel `auth.py` met de motivering "uitsluitend magic-link-endpoints, geen wachtwoord". Feitelijk onjuist sinds `e395118f5`: `quick_login` geeft een token uit zonder wachtwoord en wordt door deze vrijstelling verborgen voor de OP-61-guard. Geverifieerd: met schone env is de guard 6/6 groen terwijl `quick_login` token-uitgifte zonder wachtwoord bevat -- de guard kijkt er dus niet naar. Spec erkent het maar zonder follow-up-ID. | Verfijn de vrijstelling naar functieniveau (magic-link endpoints + `login_with_password` dat `verify_password` aanroept mogen; `quick_login` expliciet als afwijkende, environment-gated uitzondering benoemen), of voeg `quick_login` toe als bewuste exempt met eigen motivering. Maak een follow-up-ID aan in de registry. Niet blokkerend: pre-existing, eerlijk gedocumenteerd. |
| MEDIUM | `auth.py:467-472` (`quick_login`) | Productie-guard is `if settings.environment == "production"` -- een exacte match op een waarde die fail-open is. De repo-deployments zetten ook `ENVIRONMENT=blue`, `=green` (deployment/blue_green) en `=staging` (cd-staging.yml): in al die omgevingen staat een endpoint open dat zonder wachtwoord een 24-uurs ADMIN-token uitgeeft bij eerste aanmaak. Pre-existing (e395118f5), maar deze commit raakt `quick_login` en claimt "productie-guard ongemoeid" -- dat is accuraat, maar de guard zelf is zwak. | Fail-closed maken: quick-login alleen toestaan bij een expliciete allowlist (`environment in ("development", "dev", "local")`), zodat een typo of nieuwe omgeving hem dicht houdt. Eigen follow-up-taak; niet blokkerend voor deze fix omdat productie zelf wel `ENVIRONMENT=production` zet (cd-production.yml:452,551,620 geverifieerd). |
| MEDIUM | `src/core/api/auth/router_login.py:196-199` | Het exacte patron dat deze fix uit het portal verwijdert, leeft onveranderd voort in de CORE OAuth2-login: `"admin"` mapt op `admin@levendmonument.nl` en elke string zonder `@` op `<naam>@levendmonument.nl`. Geen privilege-escalatie (wachtwoord blijft vereist en rollen komen uit RBAC), maar wel een hardcoded productie-identiteit in een inlogpad -- spec-regel R3 ("geen hardcoded productie-email meer als identiteitsfallback") geldt daarmee alleen voor het portal. | Follow-up-taak: dezelfde exacte-email-match in `router_login.py` doorvoeren, met frontend-afstemming. Buiten de scope van BE-SEC-054, maar moet als bevinding vastliggen omdat de markt-review-rij het patroon als categorie noemt. |
| LOW | `scripts/create_admin_user.py:39,69-72` | Seedt een core user met letterlijk email `"admin"` EN een portal-user `"admin"` met rol ADMIN, achter wachtwoord `Tester01` in de broncode. Effect: op elke database waar dit script draaide werkt username `admin` nog steeds als portal-admin-login -- de "exacte email-match" van de fix is dan een lege huls. DATABASE_URL is hardcoded localhost, dus de blast radius is dev-only, maar het script ondermijnt de nieuwe invariant zodra iemand het ergens anders richt. | Verwijder de `"admin"`-rij uit beide lijsten (alleen `admin@levendmonument.nl` seeden) en verplaats het wachtwoord naar een verplichte env-var. Spec noemt de flow al ("Beinvloede bestaande flows") -- maak de aanbeveling er expliciet bij. |
| LOW | `auth.py:393-405` (`login_with_password`) | Geen `is_blocked`-check op de gevonden/aangemaakte `PortalUser`; de magic-link flow heeft die wel (`auth.py:268-292`, met audit-event). Een geblokkeerde portal-user met een geldig core-wachtwoord krijgt hier wel een token. Onbruikbaar in de praktijk (`require_portal_user` weigert geblokkeerde users per request, `dependencies.py:244-248`), dus geen rechten-lek -- maar inconsistent, en het audit-spoor toont een "succesvolle" login voor een geblokkeerd account. | Voeg dezelfde blocked-check toe als in `verify_magic_link` (403 + audit-event), of leg bewust vast dat de dependency-laag de enige handhaving is. |
| LOW | `portal/src/pages/Login.tsx:19-20,77` | Frontend prefillt op dev-hosts username `admin` / wachtwoord `Tester01` en redirect na password-login altijd naar `/beheer` -- een vers-geprovisioneerde VISITOR landt op een 403-pagina. Beide dev-only/UX, bewust out-of-scope in de spec, maar de redirect is ook voor productie-relevant gedrag (staff zonder portal-rol). | Frontend-follow-up: redirect afhankelijk van `res.user.role` (zoals quick-login dat op regel 121 al doet). |
| LOW | `auth.py:301,412,515` | De `sec_level`-mapping staat drie keer letterlijk in het bestand. Toekomstige rol (bijv. TEACHER) moet op drie plekken tegelijk; missen er een geeft een stille security_level/role-afwijking in het JWT. | Helper `_sec_level_for(role_val)` extraheren. |

## F. Ontbrekende items

- Follow-up-ID voor de KNOWN_EXEMPT-verfijning (nu alleen proza in "Out of scope" en "Open vragen").
- Follow-up-ID voor de fail-closed quick-login guard.
- Follow-up-ID voor het fallback-patroon in `router_login.py`.
- Test dat password-login voor een geblokkeerde PortalUser 403 geeft (afhankelijk van de LOW-fix hierboven).
- Integratietest van password-login tegen echte DB (door de spec eerlijk als niet-gedaan gemarkeerd; kan mee met de eerstvolgende integratie-window).

## G. Verbeterde codevoorstellen

`auth.py` (fail-closed quick-login guard):

```python
_QUICK_LOGIN_ALLOWED_ENVIRONMENTS = frozenset({"development", "dev", "local"})

settings = get_settings()
if settings.environment not in _QUICK_LOGIN_ALLOWED_ENVIRONMENTS:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quick login is disabled outside local development.",
    )
```

`auth.py` (blocked-check, gespiegeld aan de magic-link flow):

```python
if portal_user and portal_user.is_blocked:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User account is blocked",
    )
```

`auth.py` (gedeelde sec_level-helper):

```python
def _sec_level_for(role_val: str) -> str:
    if role_val == "admin":
        return "admin"
    if role_val == "curator":
        return "authorized"
    return "authenticated"
```

## H. Release-oordelen

- Bouw/implementatie: **ja** -- de fix doet exact wat hij claimt, objectief geverifieerd.
- QA/geautomatiseerd testen: **ja** -- echte gedragstests met rood->groen; regressie gereproduceerd met alleen pre-existing failures.
- LLM-training: **ja** -- spec 18/19 zijn accuraat over het nieuwe gedrag.
- Integratorhandleiding / spec: **ja** -- spec klopt met de code; de vervangende seed-route voor de eerste admin is volledig gedocumenteerd (sectie "Vervangende route voor de eerste admin"); open aannames en risico's zijn eerlijk.

## Wat wel klopt

- De twee gemelde escalerende deuren zijn dicht en dat is **in code geverifieerd**, niet alleen via testnamen: geen IN-lijst meer in de core-lookup (`User.email == raw_user`), provisioning met `PortalRole.VISITOR`, portal-lookup op canonieke `core_user.email`, quick-login else-tak volledig weg.
- De tests zijn geen schijnvertoning: de fake sessie evalueert de echte gecompileerde WHERE-bind-parameters (een terugkeer van de hardcoded fallback wordt rood), en `_decode_role` decodeert het echte JWT met de echte `jwt_handler` -- de rol-claim zelf wordt geverifieerd, niet alleen de response.
- Autorisatie-architectuur maakt de fix effectief: `require_admin`/`require_curator` lezen de rol uit de vers geladen DB-rij, niet uit het token. Een gestolen of verouderd admin-token zonder admin-rij in `portal_users` geeft geen rechten.
- Productie-guard uit `e395118f5` is ongemoeid (via `git show` bevestigd) en de productie-CD zet daadwerkelijk `ENVIRONMENT=production` (cd-production.yml, drie plekken geverifieerd).
- Regressie-bewijs klopt: `-k foundation` 245 passed met exact de vier gedocumenteerde pre-existing failures/errors (zelf gereproduceerd; de datetime-failure zit in `newsletter.py`, niet in deze wijziging). De architecture-guard-failures in de standaard-shell zijn een gedocumenteerd omgevingsartefact (`GIT_CONFIG_VALUE_0`), met schone env 6/6 groen.
- Uniforme 401 bij elke credential-mismatch (geen user-enumeratie), audit via `best_effort` ongemoeid, rate limit ongemoeid.
- ruff schoon, ASCII-only geverifieerd (0 non-ASCII), geen `datetime.now()` -- `utc_now()` uit `datetime_utils`.
- De spec is uitzonderlijk eerlijk: de KNOWN_EXEMPT-veroudering, de `"admin"`-seed-flow in `create_admin_user.py`, en het ontbreken van tenant-isolatie- en integratietests staan er allemaal expliciet in. Dat maakte deze review sneller en betrouwbaarder.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **De guard die dit had moeten vangen, kijkt bewust de andere kant op.** KNOWN_EXEMPT vrijstelt heel `auth.py` met een motivering die al twee commits onjuist is. De eerstvolgende developer die in `auth.py` een nieuw endpoint toevoegt dat "even snel" een token uitgeeft, wordt door de OP-61-guard niet gestopt -- het bestand is immers "magic-link only". Deze fix dicht de deur, maar laat het alarmsysteem uitgeschakeld voor precies de kamer waar de inbraak plaatsvond.
2. **Fail-open omgeving-detectie is een klassieke productie-boobytrap.** De quick-login guard staat of valt met de string `"production"`. De repo kent al `blue`, `green` en `staging` als ENVIRONMENT-waarden; de eerste blue/green-activatie of hernoemde omgeving (`"prod"`, `"Production"`) zet een wachtwoordloos admin-endpoint live. Niemand merkt dat, want er is geen test die de guard tegen de deployment-matrix toetst -- alleen tegen de letterlijke waarde "production".
3. **De seed-scripts zijn de nieuwe achterdeur.** `create_admin_user.py` maakt een account `"admin"` met wachtwoord `Tester01` aan -- in versiebeheer, voor eeuwig. De fix verplaatst de privilege-escalatie van runtime-code naar een operator-script, wat principieel beter is, maar het script zelf heeft geen enkele vorm van bevestiging, omgeving-check of wachtwoord-invoer. Zodra iemand het "even" tegen een gedeelde dev- of staging-database draait, staat er een raadbaar admin-account. De verantwoordelijkheid is verplaatst, niet verdwenen, en operator-scripts worden nooit gereviewd als security-code.
4. **Dezelfde codeerstijl leeft elders ongemoeid voort.** `router_login.py` heeft vandaag nog exact het patroon dat deze sprint als HIGH werd bestempeld. De volgende markt-review zal het vinden en terecht vragen waarom "de fix" alleen het portal raakte. Scope-discipline is goed, maar zonder follow-up-ID is "out of scope" synoniem met "verdwenen".
5. **VISITOR-by-default creert een stil promotie-kanaal via de database.** Wie nu admin wil worden, moet "even" een UPDATE op `portal_users.role` doen -- er is geen admin-endpoint, geen promotie-flow, geen audit-trail-eis voor rolwijzigingen. De eerste keer dat een medewerker "zichzelf even curator maakt" via een handquery, is er geen mechanisme dat dat opvalt. De fix sluit het geautomatiseerde pad; het handmatige pad is ongedocumenteerd en onbewaakt.

Punten 1-4 zijn met kleine, afgebakende follow-ups af te dekken (zie E en G); punt 5 hoort bij een grotere rolbeheer-taak. Geen van deze punten ondermijnt de correctheid van deze commit zelf.

---

*Review geschreven in de review-worktree `hlm-wk1-admin-promotie`; geen code gewijzigd.*
