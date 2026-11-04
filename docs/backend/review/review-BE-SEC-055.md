# Review BE-SEC-055: Security-residu's fail-closed (Brevo-webhook, stripe_handler, quick-login)

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen, Red Team). Code niet zelf geschreven; worktree read-only gereviewd. Elke claim uit commits en spec is zelf met commando's her-verifierd; niets op aannames overgenomen.
**Datum:** 2026-09-25
**Scope:** commits `555258052`, `c7e0d2a65`, `9817fd822`, `ab228a2ba`, `4eb57afdd` op branch `iter/wk1-security-residu` (diff t.o.v. `45f3f45fe`) -- `src/core/api/v1/foundation/webhooks.py`, `src/core/api/webhooks/stripe_handler.py`, `src/core/api/v1/foundation/auth.py`, vijf mee-gewijzigde testbestanden, twee nieuwe testbestanden, spec `docs/backend/features/BE-SEC-055-security-residu-fail-closed.md`. Context gelezen: `sms_webhooks.py`, `activepieces/dependencies.py`, `webhook_endpoints.py`, `telegram.py`, `edu.py`, `dependencies.py` (foundation), `router_login.py`, `router_token.py`, `config_validator.py`, `shared/config.py`, `unified_config.py`, `tests/conftest.py`, `FEATURE_DOC_WORKFLOW.md`, review-BE-SEC-058 als formatvoorbeeld.

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS -- alle drie de geclaimde fail-open residu's zijn aantoonbaar en correct fail-closed gemaakt; geen CRITICAL/HIGH-bevindingen. De fixes zijn op code-niveau gelezen (niet alleen test-namen): geen bypass gevonden voor None, lege string, case of whitespace in de omgevingsnaam; de quick-login-guard staat voor elke database-aanraking; de stripe-guard staat voor `construct_event` (mock-assertie bewijst dat die niet wordt aangeroepen). Eigen test-run reproduceert de claim exact: 36 passed over dezelfde suites. Twee MEDIUM-bevindingen: (1) de claim dat de livemode-guard op `stripe_handler.py` de enige resterende exact-`"production"`-plek is, is aantoonbaar onjuist -- `sms_webhooks.py` (MessageBird) is een fail-open webhook van exact dezelfde residu-klasse die deze iteratie miste, en cookie-hardening in `router_login.py`/`router_token.py`/`edu.py` degradeert in blue/green; (2) de deploy-checklist-eis uit de spec heeft geen runtime-alarm of startup-check, waardoor het nieuwe 503-gedrag een stille uitval wordt. Beiden blokkeren de merge niet maar vereisen een benoemde follow-up.

## C. Samenvatting

Verificatie met eigen runs vanuit de worktree (venv van de hoofdrepo):

- **36/36 tests groen**, exact de spec-claim, in drie eigen runs:
  - `test_brevo_webhook_fail_closed.py` + `tests/unit/api/test_webhook_handlers.py`: **13 passed** (12.52s).
  - `test_foundation_password_login.py` + `test_billing_idempotency.py` + `test_monetization_phase2_behavioral.py`: **19 passed** (27.42s) -- inclusief de bestaande BE-SEC-054 quick-login-tests (`test_quick_login_creates_visitor_in_development` e.a.), dus quick-login werkt aantoonbaar nog in development.
  - `tests/architecture/test_no_audit_write_without_hash_chain.py`: **4 passed** (5.96s).
- **Ruff schoon** (zelf gedraaid) op alle negen gewijzigde code/testbestanden: "All checks passed!".
- **ASCII byte-scan clean** (zelf gedraaid, byte-niveau) op alle zes door mij beoordeelde gewijzigde bestanden.
- **mypy niet zelf gereproduceerd**: mijn run op de drie bronbestanden overschreed de 240s-timeout (volledige importketen). De spec-meeting (16 errors, 0 in gewijzigde bestanden, identiek aan parent) is niet weerlegd maar ook niet door deze review bevestigd -- zie Ontbrekende items.
- **Blast-radius geverifieerd:** `_verify_webhook_secret` heeft precies een consumer (grep in `src/`: definitie + een `Depends`); `stripe_webhook` heeft geen aanroepers buiten tests; `quick_login`-guard zit inline. De claim uit spec-sectie B klopt.
- **Bestaande tests niet verzwakt:** de diff van de vijf mee-gewijzigde testbestanden bevat UITSLUITEND toegevoegde secret-patches (`patch.object(unified_config, "stripe_webhook_secret", ...)`), een autouse-fixture die een brevo test-secret zet, en `X-Webhook-Secret`-headers op twee bestaande posts. Nul verwijderde of afgezwakte asserties.
- **Fail-closed op code-niveau, geen bypass gevonden:**
  - brevo: `if not configured` dekt `None` EN `""`; daarna `secrets.compare_digest` (timing-safe). Whitespace-secret (`" "`) is truthy en eindigt in compare_digest -- geen fail-open, hooguit een zwak geconfigureerd secret (LOW-4).
  - stripe_handler: guard op `not webhook_secret` staat VOOR `construct_event`; de nieuwe test assert `construct_event.assert_not_called()` -- de volgorde is dus testgedekt, niet alleen leesbaar.
  - quick-login: `(settings.environment or "").strip().lower()` is None-safe, case-safe en whitespace-safe; `"Production"`, `" PRODUCTION "`, `"blue"`, `"green"`, `"staging"`, `""` vallen allemaal buiten de allowlist -> 403 voor elke DB-aanraking (de nieuwe parametrized test assert bovendien dat er geen PortalUser wordt aangemaakt).
- **`settings.environment` default is `"development"`** (`shared/config.py:27`, gelezen) -- lokale dev-flow werkt out-of-the-box; conftest zet `ENVIRONMENT=test` (`tests/conftest.py:84`) en `"test"` zit in de allowlist, dus de suite is niet afhankelijk van shell-environment.
- **Spec-pad-afwijking acceptabel:** `FEATURE_DOC_WORKFLOW.md` schrijft `docs/backend/features/<ID>-<naam>.md` voor; de brief vermeldde een `specs/`-pad dat niet bestaat. De iteratie volgde de workflow en documenteerde de afwijking in spec-sectie G. Correct afgehandeld.
- **Rood-bewijs niet herhaald** (worktree read-only), maar op code-niveau plausibel: tegen de oude code zou `test_missing_secret_returns_503` niet raisen (`return` zonder check -> DID NOT RAISE), zou de stripe-test doorlopen naar `construct_event` met `""` (response != 503) en zou de quick-login-test in blue/green/staging een token teruggeven (geen HTTPException). Consistent met de gerapporteerde rode runs.

## D. Bevindingen per categorie

1. **Security** -- De drie gefixte paden zijn echt fail-closed (zie C). Maar de zoektocht van de iteratie was te smal: de claim "livemode-guard is de enige resterende" houdt geen stand. `sms_webhooks.py::_validate_messagebird_signature` (r.253-271) is een webhook-verificatie die bij een ontbrekend `MESSAGEBIRD_WEBHOOK_SECRET` in elke omgeving buiten `{prod, production}` `return True` doet met alleen een warning -- exact de residu-klasse van (a) en (b), en in blue/green/staging dus fail-open voor inbound SMS. Daarnaast degraderen cookie-`secure`/`samesite` in `router_login.py:379`, `router_token.py:98,466` en `edu.py:84` bij elke ENVIRONMENT != "production" -- blue/green draaien productieverkeer met `samesite=lax`. En `config_validator.py:173` slaat de JWT_SECRET_KEY/SECRET_KEY-verplichting over buiten exact `"production"`. Geen van dit is door deze iteratie veroorzaakt of verergerd; het weerlegt wel de volledigheidsclaim (MEDIUM-1, MEDIUM-2).
2. **Correctheid** -- De nieuwe tests testen gedrag: echte functie-aanroepen, `pytest.raises` met statuscode-asserties, mock-assertie op niet-aanroepen van `construct_event`, PortalUser-aanmaak-guard. De brevo-legitieme-flow-test (`test_correct_secret_passes`) dekt de mutatie de andere kant op. Geen tautologie gevonden. De vijf mee-gewijzigde bestaande suites zijn alleen voorzien van de nieuwe precondition (secret gezet), niet afgezwakt.
3. **Architectuur** -- Geen nieuwe imports buiten bestaande lagen; geen ADR-033/034-raakvlak (geen router/domain-grenzen overschreden; wijzigingen zitten binnen de bestaande modules). Allowlist als module-constante is consistent met het dev-magic-link-patroon in dezelfde module (zij het met een grotere verzameling -- LOW-5).
4. **Tests** -- Dekking is betekenisvol: missing + empty secret, wrong + correct secret, 503-voor-construct_event, parametrized 403 voor blue/green/staging/"", geen-PortalUser-guard. Gaten: geen HTTP-niveau test van de brevo-503 via de echte route met dependency-injectie (de unit-test roept `_verify_webhook_secret` direct aan; de wiring dependency->route wordt alleen voor happy-path via de integratietest gedekt, en die is lokaal niet gedraaid). Zie Devil's Advocate 6.
5. **Regels** -- ASCII clean (byte-scan, zelf gedraaid), geen `datetime.now()`/`utcnow()` toegevoegd (diff bevat geen datetime-aanroepen), geen letterlijke echte secrets (wel het prefix-dragende test-secret, zie DA-5), ruff schoon (zelf gedraaid), mypy niet zelf geverifieerd (timeout -- zie F).

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `src/core/notifications/inbound/sms_webhooks.py:253-271` (PRE-EXISTING, gemist door de iteratie) | MessageBird-webhook-verificatie is fail-open bij ontbrekend secret: `if not signing_secret: ... return True` voor elke ENVIRONMENT buiten `{prod, production}`. In blue/green/staging accepteert het inbound-SMS-endpoint ongeverifieerde berichten. Dit is exact de residu-klasse die BE-SEC-055 voor brevo en stripe dichtt -- de claim "livemode-guard is de enige resterende" is hiermee weerlegd. | Sprint-dag-brief (conform NOOIT-lijst, geen registerrij): dezelfde fail-closed-guard als deze iteratie, of de blue/green/staging-namen opnemen in de productie-verzameling. Niet blokkerend voor deze merge. |
| MEDIUM | `router_login.py:379`, `router_token.py:98,466`, `edu.py:84`, `config_validator.py:173` (PRE-EXISTING, zelfde klasse als residu c) | Exact-`"production"`-match op security-hardening: cookie `secure`/`samesite=strict` en de JWT/SECRET_KEY-verplichtingscheck vallen weg in blue/green/staging. Blue/green draait productieverkeer met `samesite=lax` en zonder verplichte-secret-validatie bij boot. Residu c is voor quick-login gefixt; dezelfde denkfout zit nog in vier andere security-paden. | Sprint-dag-brief: canonical `is_production()`-beslissing (een functie, een waarheid) of dezelfde allowlist/denylist-aanpak als BE-SEC-055. Niet blokkerend voor deze merge. |
| LOW | `stripe_handler.py:66` livemode-guard | Exact-match `== "production"`: Stripe-test-events met valide signature worden in blue/green niet geweigerd. Door de fail-closed secret-guard is impact laag (valide signature met echt endpoint-secret vereist). Correct benoemd in de spec. | Meenemen in de MEDIUM-2-brief; zelfde beslissing. |
| LOW | `webhooks.py:69` + `stripe_handler.py:40` | Geen `.strip()` op het geconfigureerde secret: een whitespace-secret (`" "`) telt als geconfigureerd en eindigt als (extreem zwakke) HMAC/compare-sleutel. Geen bypass (aanvaller moet de waarde kennen), maar inconsistent met `sms_webhooks.py:262` die wel stript. | `configured = (settings.brevo_webhook_secret or "").strip()` bij een volgende aanraking; nu accepteren. |
| LOW | `auth.py:50-55` vs `auth.py:159` | Twee environment-verzamelingen in een module: quick-login allowlist `{development, dev, local, test, testing}` vs dev-magic-link `{development, dev, local}`. Bewust en gedocumenteerd, maar een derde guard zal opnieuw een eigen set verzinnen (zie DA-3). | Bij MEDIUM-2-brief een gedeelde helper overwegen. |
| LOW | Integratietests | `test_brevo_webhook.py` en `test_webhook_database_sync.py` vereisen PostgreSQL en zijn lokaal niet gedraaid; wijzigingen (autouse-secret-fixture, secret-patch) zijn identiek aan groen gedraaide unit-patronen maar pas in CI meetbaar. Spec benoemt dit eerlijk. | CI-run op `develop` na merge verifieert; geen actie in deze iteratie. |

## F. Ontbrekende items

- Sprint-dag-briefs voor MEDIUM-1 (sms_webhooks fail-open) en MEDIUM-2 (cookie/config-validator hardening in blue/green) -- conform de NOOIT-lijst geldt: geen nieuwe registerrij, wel direct een brief in `docs/agent-briefs/generated/`.
- **mypy-verificatie ontbreekt in deze review:** mijn run op de drie bronbestanden overschreed de 240s-timeout. De spec-claim (16 pre-existing errors, 0 in de gewijzigde bestanden, identiek aan parent) is onweerlegd maar door mij niet bevestigd. Verifieer met: `python scripts/run_mypy_audit.py` op de merge-branch. Gezien de diff-omvang (+49/-9 regels broncode, geen nieuwe types of imports) en de schone ruff-run is het risico klein, maar de poort eist een meting, geen redenering.
- HTTP-niveau 503-test voor brevo via de echte route (dependency-wiring), of een bewuste notitie dat de integratietest dit in CI dekt.
- De stash-proef (rood->groen) is door de schrijver gedocumenteerd maar door deze review niet herhaald (read-only worktree); op code-niveau plausibel bevonden voor alle drie de residu's.

## G. Verbeterde codevoorstellen

Follow-up sms_webhooks (zelfde guard als deze iteratie):

```python
if not signing_secret:
    logger.error("MESSAGEBIRD_WEBHOOK_SECRET missing; refusing webhook (fail-closed)")
    return False
```

Follow-up cookie-hardening (een waarheid voor "productie-achtig"):

```python
_PRODUCTION_LIKE = frozenset({"production", "prod", "blue", "green"})

def is_production_like() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() in _PRODUCTION_LIKE
```

## H. Release-oordelen

- Bouw/implementatie: **ja**.
- QA/geautomatiseerd testen: **ja** (36/36 zelf gedraaid; nieuwe tests testen gedrag inclusief legitieme-flow-mutatie; bestaande tests niet verzwakt -- diff bevat nul verwijderde asserties).
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja** -- de spec klopt met de code op alle door mij geverifieerde punten (testaantallen, codepaden, blast-radius, config-default `""` op `unified_config.py:278`, ENVIRONMENT-waarden van de deploys), behalve de volledigheidsclaim over resterende `== "production"`-plekken (MEDIUM-1/2). Deploy-risico is eerlijk benoemd in sectie G. Wel de twee MEDIUM-briefs uitschrijven voor merge naar `main`.

## Wat wel klopt

- Echt fail-closed op alle drie de paden, op code-niveau gelezen: geen bypass via `None`, `""`, case, whitespace in de omgevingsnaam, of een tweede aanroeper (grep: `_verify_webhook_secret` heeft exact een consumer; `stripe_webhook` heeft geen niet-test aanroepers).
- De stripe-guard staat aantoonbaar VOOR `construct_event` -- de test assert `construct_event.assert_not_called()`, dus de volgorde is gedekt en niet alleen leesbaar.
- De quick-login-403 staat voor elke database-aanraking; de parametrized test assert expliciet dat er geen PortalUser wordt aangemaakt. BE-SEC-054-gedrag (geen rol-promotie) ongemoeid; de bestaande quick-login-development-tests zijn groen in mijn eigen run.
- Bestaande fail-open-leunende tests zijn niet verzwakt: de diffs voegen uitsluitend de nieuwe precondition toe (secret-patches, headers, autouse-fixture met nette teardown) en raken geen enkele bestaande assertie.
- De integratie-fixture in `test_brevo_webhook.py` herstelt het originele secret in teardown -- geen test-pollutie.
- Timing-safe vergelijking behouden: `secrets.compare_digest` (brevo), SDK-HMAC (stripe). Geen nieuwe string-`==` op secrets.
- Eerlijke meetcultuur: de spec benoemt de pyright-baseline-kwestie, de niet-lokaal-gedraaide integratietests, het spec-pad-verschil met de brief, en de bewust niet-gefixte livemode-guard. De 36-passed-claim reproduceerde exact (13 + 19 + 4).
- Spec-pad `features/` i.p.v. het onbestaande `specs/` uit de brief is conform `FEATURE_DOC_WORKFLOW.md` -- de afwijking is correct en gedocumenteerd.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **De 503 is een stille uitval, nu op twee webhooks tegelijk.** Een omgeving zonder `BREVO_WEBHOOK_SECRET` of `STRIPE_WEBHOOK_SECRET` krijgt 503; bounces/unsubscribes en subscription-updates stoppen zonder alarm, en voor de stichting ziet dat er uit als "niemand schrijft zich meer uit" en "niemand betaalt meer". De spec eist een deploy-checklist, maar checklists worden gelezen door mensen op een deploy-dag; een startup-check ("webhook-route actief maar secret ontbreekt -> weiger te bootsen of alarm") ontbreekt. Dit is dezelfde gap die de BE-SEC-058-review al benoemde -- deze iteratie verdubbelt het aantal routes met dat risico zonder de gap te dichten.
2. **Het patroon is op drie plekken gedicht; de klasse leeft voort en de iteratie dacht van niet.** De spec claimt dat de livemode-guard de enige resterende is; gemeten klopt dat niet -- `sms_webhooks.py` is een fail-open webhook van exact dezelfde klasse (de ergste gemiste), en vier andere security-paden (cookies x3, config-validator) degraderen in blue/green. De zoektocht zocht op de drie benoemde residu's, niet op de kwetsbaarheidsklasse (`== "production"` als security-guard, `if not secret: ... return True/permit`). Zonder de twee MEDIUM-briefs is dit precies het "uitgestelde security-work dat verdwijnt" waar de BE-SEC-058-review voor waarschuwde -- die review noemde deze residu's bij naam, en een volgende review zal sms_webhooks bij naam noemen.
3. **ENVIRONMENT is een vrije string zonder canonieke interpretatie.** Deze codebase beantwoordt "is dit productie?" nu op minstens drie manieren: `== "production"`, `in {"prod", "production"}`, en de nieuwe allowlist `{development, dev, local, test, testing}`. Een deploy-typefout (`ENVIRONMENT=proudction`) maakt quick-login dicht (fail-closed, goed) maar alle `is_production`-hardening zacht (fail-open, slecht) -- en niemand merkt het, want de app boot gewoon. Deze iteratie voegt een vierde interpretatie toe in plaats van de canonieke functie; dat is verdedigbaar als scope-discipline maar vergroot het oppervlak voor de volgende inconsistente guard.
4. **De allowlist beschermt tegen bekende deploy-namen, niet tegen misconfiguratie richting test.** `test` en `testing` staan in de allowlist omdat conftest dat nodig heeft; een misgeconfigureerde container met `ENVIRONMENT=test` mint admin-tokens zonder authenticatie. De juiste langetermijnfix is quick-login achter een aparte, expliciete feature-flag (`ENABLE_QUICK_LOGIN=true`) die nooit in een deploy-manifest staat -- de environment-allowlist is een heuristiek, geen autorisatie.
5. **Het test-secret `whsec_test_secret` staat letterlijk in vier testbestanden.** BE-SEC-058 bouwde het test-secret bewust uit fragmenten om de secret-scanner niet te normaliseren; deze iteratie schrijft het prefix `whsec_` plat. Functioneel onschuldig (het is geen echte secret), maar het normaliseert het patroon "whsec_-string in de repo" -- de scanner-regel die BE-SEC-058 verdedigde ("geen letterlijke whsec_-strings") is hiermee feitelijk uitgehold, en een volgende echte secret in testcode valt niet meer op.
6. **De 503-tests bewijzen de functie, niet de wiring.** De brevo-tests roepen `_verify_webhook_secret` direct aan; geen enkele groen gedraaide test gaat via de echte HTTP-route met `Depends(_verify_webhook_secret)` zonder secret. Een toekomstige refactor die de dependency van de route loskoppelt (of de dependency-naam hernoemt) wordt door geen van de nieuwe tests gevangen -- de integratietest die de wiring wel dekt, is juist degene die lokaal niet gedraaid is.

Geen van deze punten blokkeert de merge: punten 1 en 2 vereisen benoemde follow-up-briefs (MEDIUM-1, MEDIUM-2), punt 6 een CI-verificatie van de integratietests, punten 3-5 zijn hygienerisico's. De kernfixes zelf zijn correct, gemeten, niet omzeilbaar binnen de geinspecteerde paden, en eerlijk gedocumenteerd.
