# BE-SEC-055 -- Security-residu's fail-closed (Brevo-webhook, stripe_handler, quick-login)

**Status:** geimplementeerd, wacht op merge-GO van Rakesh
**Sprint:** Week 1 security-residu's (Gate-2 follow-ups van BE-SEC-057/053/054)
**Branch:** `iter/wk1-security-residu`
**Datum:** 2026-09-25
**Gerelateerde specs:** BE-SEC-058 (Stripe donatie-webhook fail-closed -- deze spec noemde
brevo-webhook en stripe_handler.py expliciet als MEDIUM follow-up), BE-SEC-054 (portal admin
auto-promotie -- diens review noemde de quick-login environment-guard als MEDIUM follow-up).

---

## A. Build Summary

Drie LOW/MEDIUM security-residu's uit eerdere Gate-2-reviews zijn fail-closed gemaakt:

1. **Brevo-webhook fail-open.** `_verify_webhook_secret()` in
   `src/core/api/v1/foundation/webhooks.py` stond bij een ontbrekend of leeg
   `brevo_webhook_secret` de request stilletjes TOE ("dev/test"-commentaar). Het endpoint
   `POST /{tenantSlug}/foundation/webhooks/brevo` was dan publiek vervalsbaar: iedereen kon
   bounce- en unsubscribe-events posten voor willekeurige e-mailadressen en daarmee de
   newsletter-status in de database wijzigen. Nu: geen/leeg secret -> HTTP 503 + error-log,
   nooit permit. Geconfigureerd secret behoudt het bestaande gedrag (401 bij foute of
   ontbrekende `X-Webhook-Secret`/`X-Brevo-Secret`/`token`).
2. **stripe_handler met publiek berekenbare HMAC.** De subscription-billing webhook
   (`src/core/api/webhooks/stripe_handler.py`, route `POST /webhooks/stripe`) riep
   `stripe.Webhook.construct_event(payload, signature, config.stripe_webhook_secret)` aan
   terwijl `stripe_webhook_secret` default `""` is (`unified_config.py:278`). HMAC-SHA256 met
   een lege sleutel is voor iedereen berekenbaar -- de signature-check was dan geen
   verificatie. Nu: leeg/ontbrekend secret -> HTTP 503 VOOR `construct_event` (die wordt dan
   nooit aangeroepen). NB: dit is een ANDERE route dan BE-SEC-058 (die ging over de
   donatie-webhook via `stripe_service.construct_webhook_event`); beide zijn nu fail-closed.
3. **Quick-login actief in blue/green/staging.** De guard in `quick_login`
   (`src/core/api/v1/foundation/auth.py`) matchte exact op `ENVIRONMENT == "production"`,
   maar de deploys zetten `ENVIRONMENT=blue` / `ENVIRONMENT=green`
   (`deployment/blue_green/docker-compose.blue.yml`, `.../green.yml`) en
   `ENVIRONMENT=staging` (`.github/workflows/cd-staging.yml`). In al die omgevingen was
   quick-login actief en minte het endpoint admin-tokens zonder enige authenticatie. Nu:
   expliciete allowlist `{development, dev, local, test, testing}` -- alles anders -> 403
   en er wordt geen PortalUser aangemaakt.

---

## B. De gemeten uitgangssituatie (her-verificatie van de residu's)

Gemeten op branch `iter/wk1-security-residu` @ `45f3f45fe` (startpunt), niet overgenomen uit
de reviews:

| Residu | Her-verificatie | Uitkomst |
| --- | --- | --- |
| Brevo fail-open, `webhooks.py` ~r.65-67 | code gelezen | BEVESTIGD (`if not configured: return` met comment "permit request") |
| stripe_handler lege HMAC-sleutel, ~r.39-41 | code gelezen + config-default | BEVESTIGD (`construct_event(..., config.stripe_webhook_secret)`, default `""` in `unified_config.py:278`) |
| quick-login exact-match "production", `auth.py` ~r.468 | code gelezen + deploy-configs gegrept | BEVESTIGD (`if settings.environment == "production"`; deploys zetten blue/green/staging) |
| BE-SEC-055 vrij in ID-REGISTRY | registry gelezen | BEVESTIGD (register loopt t/m BE-SEC-054; registry bewust niet aangeraakt) |

Blast-radius gemeten vooraf: `_verify_webhook_secret` is een FastAPI-dependency met precies
een consumer (`handle_brevo_webhook`). `quick_login`-guard zit inline in het endpoint.
`stripe_handler.py::stripe_webhook` heeft vijf test-suites als aanroepers (unit x4,
integratie x1) die de lege default-secret als impliciete precondition gebruikten -- die zijn
mee-gewijzigd (secret-patch toegevoegd), zie D.

---

## C. De implementatie

### `src/core/api/v1/foundation/webhooks.py` (residu a)

- `_verify_webhook_secret()`: de `if not configured: return`-tak is vervangen door
  `logger.error(...)` + `HTTPException 503` ("Webhook endpoint is not configured."). Een lege
  string telt niet als secret (`not configured` dekt `None` en `""`).
- Endpoint-docstring bijgewerkt: het secret is niet langer "optional".

### `src/core/api/webhooks/stripe_handler.py` (residu b)

- Voor `construct_event`: `webhook_secret = config.stripe_webhook_secret`; bij leeg/ontbrekend
  -> `logger.error(...)` + `HTTPException 503`. `construct_event` krijgt de lokale variabele,
  niet meer de config-attribuut inline. Bestaand gedrag (400 bij foute signature, 503 bij
  Redis-down, livemode-guard) is ongemoeid.

### `src/core/api/v1/foundation/auth.py` (residu c)

- Nieuw: module-constante `_QUICK_LOGIN_ALLOWED_ENVIRONMENTS = frozenset({"development",
  "dev", "local", "test", "testing"})`. De eerste drie waarden zijn identiek aan de
  dev-magic-link-guard in dezelfde module (regel ~152); `test`/`testing` dekken de
  pytest-omgeving (`tests/conftest.py` zet `ENVIRONMENT=test`).
- `quick_login`: `environment = (settings.environment or "").strip().lower()`; niet in de
  allowlist -> 403 ("Quick login is only available in development/test environments.").
  De 403 staat VOOR elke database-aanraking, dus ook geen PortalUser-aanmaak.
- Productie-guard uit BE-SEC-054 (e395118f5) blijft functioneel: "production" zit niet in de
  allowlist.

### Tests

- Nieuw: `tests/unit/test_brevo_webhook_fail_closed.py` -- 4 tests: missing secret -> 503,
  empty secret -> 503, wrong secret -> 401 (ongewijzigd), correct secret -> passeert
  (legitieme-flow-mutatie).
- `tests/unit/api/test_webhook_handlers.py` -- 1 nieuwe test
  (`test_rejects_when_webhook_secret_not_configured`: 503 + `construct_event` nooit
  aangeroepen) + class-fixture configureert nu een test-secret via `patch.object` op de
  config-proxy (`_ConfigProxy`; setattr op de proxy shadowt de forwarding, teardown herstelt).
- `tests/unit/test_foundation_password_login.py` -- 1 nieuwe parametrized test
  (`test_quick_login_forbidden_outside_allowlist[blue|green|staging|'']`: 403 + geen
  PortalUser-aanmaak).
- Mee-gewijzigde bestaande tests (leunden op de fail-open default):
  `tests/unit/test_billing_idempotency.py` (2 with-blokken),
  `tests/unit/test_monetization_phase2_behavioral.py` (2 tests),
  `tests/integration/test_webhook_database_sync.py` (2 with-blokken),
  `tests/integration/api/v1/foundation/test_brevo_webhook.py` (autouse-fixture zet
  test-secret + `X-Webhook-Secret`-header op de twee bestaande posts).

---

## D. Rode -> groene bewijzen (gemeten, niet beschreven)

| Residu | Rode run (voor de fix) | Groene run (na de fix) |
| --- | --- | --- |
| a | `test_brevo_webhook_fail_closed.py`: 2 failed (`DID NOT RAISE HTTPException` bij missing/empty), 2 passed | 4 passed |
| b | `TestStripeWebhook::test_rejects_when_webhook_secret_not_configured` failed (handler ging door naar construct_event met lege sleutel; response != 503) | 14 passed over webhook_handlers + billing_idempotency + monetization_phase2 |
| c | `test_quick_login_forbidden_outside_allowlist[blue|green|staging|'']`: 4 failed (endpoint leverde tokens) | 14 passed in test_foundation_password_login.py |

Gecombineerde eindrun van alle geraakte suites (5 unit-bestanden +
`tests/architecture/test_no_audit_write_without_hash_chain.py`): **36 passed**.

---

## E. Regressiemetingen

| Meting | Voor | Na |
| --- | --- | --- |
| ruff op 9 gewijzigde bestanden | -- | schoon ("All checks passed!") |
| mypy op 3 gewijzigde bronbestanden | 16 errors, alle in niet-gewijzigde bestanden (curatie.py 1, map.py 4, upload.py 4, foundation_storage.py 7) -- zelfde 16 als gemeten in BE-SEC-058 | 16 errors, identieke bestandsverdeling, 0 in webhooks.py/stripe_handler.py/auth.py |
| pyright (`python -m pyright`, zonder args) | zie opmerking hieronder | 72 errors, waarvan 3 in auth.py; parent-vergelijking (`git show 204d28f1f^:.../auth.py` als los bestand geanalyseerd) toont DEZELFDE 3 errors op dezelfde code (regels 154/157/158 -> 162/165/166 door mijn +8 regels): pre-existing `reportPossiblyUnboundVariable` in `request_magic_link`, niet door mij geraakt. webhooks.py en stripe_handler.py: 0 errors. |
| ASCII-scan gewijzigde bestanden | -- | clean (alle nieuwe code/comments ASCII) |
| `datetime.now()/utcnow()` | -- | niet toegevoegd |

Opmerking pyright: de venv-pyright (v1.1.411) meldt `Config contains unrecognized setting
"baselineFile"` -- de baseline uit `pyright-baseline.json` wordt in deze omgeving NIET
toegepast, vandaar 72 zichtbare errors waar de project-baseline 0 claimt. Dat is een
pre-existing omgevingskwestie (geldt identiek voor de parent-commit); de eerlijke meting is
de parent-vergelijking hierboven: 0 nieuwe pyright-errors door deze taak.

Pre-existing, NIET door deze taak veroorzaakt en bewust niet gefixt (buiten scope):
dezelfde lijst als BE-SEC-058, plus `stripe_handler.py:54` (livemode-guard matcht nog exact
op `== "production"` -- zelfde patroon als residu c, maar onderdeel van een andere beslissing:
welke omgevingen Stripe-test-events accepteren; benoemd als follow-up, niet stilletjes
meegenomen).

---

## F. Acceptatiecriteria

- Brevo-webhook zonder geconfigureerd `brevo_webhook_secret` -> 503, geen state-mutatie,
  error-log aanwezig. [getest: unit, 2 tests]
- Brevo-webhook met geconfigureerd secret: foute/ontbrekende secret -> 401, correcte -> 200.
  [getest: unit + bestaande integratietest `test_webhook_secret_protection` ongewijzigd groen]
- Stripe-subscription-webhook met leeg/ontbrekend `stripe_webhook_secret` -> 503 en
  `stripe.Webhook.construct_event` wordt niet aangeroepen. [getest: unit, mock-assert]
- Quick-login in `blue`, `green`, `staging`, `""` -> 403, geen PortalUser-aanmaak.
  [getest: unit, parametrized]
- Quick-login in `development` blijft werken zoals in BE-SEC-054 (geen rol-promotie, dev-flow
  intact). [getest: bestaande tests ongewijzigd groen]

---

## G. Open aannames, risico's en ontbrekende informatie

- **Deploy-risico (beide webhooks):** een omgeving zonder `BREVO_WEBHOOK_SECRET` krijgt nu 503
  op `/webhooks/brevo` -- bounce/unsubscribe-verwerking stopt daar tot het secret is
  geconfigureerd. Hetzelfde geldt voor `STRIPE_WEBHOOK_SECRET` op de subscription-webhook
  (BE-SEC-058 benoemde dit al voor de donatie-webhook). Dit is het bedoelde fail-closed
  gedrag, maar het moet in de deploy-checklist: beide secrets zijn nu verplicht per omgeving
  waar de webhooks moeten werken.
- **Integratietests niet lokaal gedraaid:** `test_brevo_webhook.py` en
  `test_webhook_database_sync.py` vereisen PostgreSQL; de wijzigingen (secret-fixture/header,
  secret-patch) zijn identiek aan de groen gedraaide unit-testaanpassingen maar pas in CI
  metenbaar.
- **Follow-up benoemd, niet gefixt:** `stripe_handler.py` livemode-guard (r.54) gebruikt nog
  exact-match `== "production"`; in blue/green worden Stripe-test-events dus niet geweigerd.
  Impact: laag (verificatie is nu fail-closed; een test-event vereist alsnog een valide
  signature met het echte endpoint-secret). Hoort bij een aparte beslissing over de
  livemode-policy.
- De brief noemde als spec-pad `docs/backend/specs/spec-BE-SEC-055-...md`; die map bestaat
  niet. Conform `docs/backend/FEATURE_DOC_WORKFLOW.md` staat de spec in
  `docs/backend/features/BE-SEC-055-security-residu-fail-closed.md`. ID-REGISTRY is conform
  de brief niet aangeraakt.

## Trainingssamenvatting

- **Actor:** Brevo of Stripe (webhook-aanroepers), of een aanvaller die een vervalste webhook POST; een bezoeker die het quick-login-endpoint aanroept op een deploy met ENVIRONMENT=blue/green/staging.
- **Voorwaarde:** De omgeving heeft BREVO_WEBHOOK_SECRET respectievelijk STRIPE_WEBHOOK_SECRET gezet; quick-login is alleen bereikbaar in de allowlist-omgevingen (development, dev, local, test, testing).
- **Actie:** POST van een webhook-payload, of een POST op het quick-login-endpoint.
- **Systeemverwerking:** Zonder geconfigureerd secret weigert de webhook met 503 VOORDAT de payload wordt gelezen (brevo) of VOOR `construct_event` wordt aangeroepen (stripe); quick-login controleert de omgeving tegen de allowlist VOOR elke database-aanraking en weigert met 403.
- **Succesrespons:** Alleen een geverifieerde webhook (geldig secret + geldige signature) muteert state; quick-login mint alleen tokens in een allowlist-omgeving.
- **Foutrespons:** 503 bij ontbrekende/lege webhook-configuratie, 401 bij ongeldige signature, 403 voor quick-login buiten de allowlist; geen enkel pad accepteert meer een ongeverifieerde payload of een productie-quick-login.
