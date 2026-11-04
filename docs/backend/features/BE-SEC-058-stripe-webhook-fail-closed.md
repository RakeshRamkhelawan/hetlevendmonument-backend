# BE-SEC-058 -- Stripe-webhook fail-closed + mock-checkout-fallback verwijderd

**Status:** geimplementeerd, wacht op merge-GO van Rakesh
**Sprint:** Week 1 markt-blokkers (markt-review 2026-09-24)
**Branch:** `iter/wk1-stripe-fail-closed`
**Datum:** 2026-09-24
**Gerelateerde spec:** BE-EP-046 (foundation donations) -- diens "resilient mock checkout URL"-gedrag
wordt door deze spec ingetrokken en vervangen door fail-closed gedrag.

---

## A. Build Summary

Drie beveiligingsgebreken in het donatie-betaalpad zijn gesloten:

1. **Fail-open webhook-verificatie.** `StripeService.construct_webhook_event()` parseerde de
   webhook-payload ZONDER signature-verificatie zodra `stripe_webhook_secret` leeg was (de default).
   Een aanvaller kon zo een vervalste `checkout.session.completed` posten; de donatie ging dan op
   `status="completed"` en telde mee in de publieke transparantiestatistieken
   (`/donations/stats`, `donations.py`). Nu: ontbrekende secret = harde fout
   (`StripeWebhookSecretMissingError` -> HTTP 503), de payload wordt NOOIT geparsed zonder
   verificatie. Conform Stripe's eigen richtlijn: zonder endpoint-secret (`whsec_...`) mag een
   event-body niet vertrouwd of geparsed worden; verificatie loopt via
   `stripe.Webhook.construct_event(payload, sig_header, secret)` -- HMAC-SHA256 over
   `"{t}.{payload}"`, `v1`-scheme, default replay-tolerance 300 seconden.
   Bronnen: https://docs.stripe.com/webhooks ("Verify events are sent from Stripe"),
   https://docs.stripe.com/webhooks/signature (construct_event, `t=...,v1=...` headerformaat).
2. **Mock-checkout-fallback verwijderd.** Zonder Stripe API key genereerde
   `create_donation_checkout_session()` een nep-sessie (`mock_sess_...`) die als echte
   `pending`-donatie werd gepersisteerd. Verwijderd (niet achter een vlag): zonder API key gooit
   de service `StripeNotConfiguredError` en het endpoint antwoordt 503 voordat er een
   database-rij ontstaat.
3. **Donatie- en contact-tests collecteerden niet.** `tests/unit/test_foundation_donations.py`
   importeerde het wegge-refactorde `_get_tenant_donations`; `tests/unit/test_foundation_contact.py`
   importeerde `_TENANT_CONTACT_SUBMISSIONS`. Beiden herschreven tegen de huidige DB-backed
   implementatie; de donatie-flow heeft weer draaiende tests.

Daarnaast is de ADR-033-schending in `donations.py` gerepareerd: `stripe_service` wordt nu via de
`dependencies.py`-facade geimporteerd. Gemeten via `scripts/dsm_api_violation_finder.py`:
5 -> 4 violations.

---

## B. De gemeten uitgangssituatie (her-verificatie van de markt-review)

Gemeten op branch `iter/wk1-stripe-fail-closed` @ `560d21f5`, niet overgenomen uit de review:

| Bevinding review | Her-verificatie | Uitkomst |
| --- | --- | --- |
| Fail-open parse bij lege secret, `stripe_service.py` ~r.182-193 | code gelezen | BEVESTIGD (conditie `if not secret or not self.api_key:` -> `json.loads`) |
| Mock-checkout-fallback ~r.124-129 | code gelezen | BEVESTIGD (`mock_sess_...` + return als echte sessie) |
| `test_foundation_donations.py` collecteert niet | `--collect-only` gedraaid | BEVESTIGD (ImportError `_get_tenant_donations`) |
| `test_foundation_contact.py` zelfde patroon | `--collect-only` gedraaid | BEVESTIGD (ImportError `_TENANT_CONTACT_SUBMISSIONS`) |
| 5 ADR-033-schendingen, o.a. donations.py/webhooks.py | finder gedraaid | DEELS: 5 violations, maar in mijn bestanden alleen `donations.py:30`. `webhooks.py` importeert `src.core.connectors.brevo.mask_email` -- `connectors` staat NIET in `FORBIDDEN_MODULES` van de finder, dus geen gemeten schending. Bewust ongemoeid gelaten. |

Blast-radius gemeten vooraf: `construct_webhook_event` heeft precies een aanroeper
(`donations.py:stripe_donations_webhook`); `create_donation_checkout_session` idem
(`donations.py:create_donation_checkout`). De subscription-flows (`billing_endpoints.py`,
`api/webhooks/stripe_handler.py`) gebruiken andere methoden van de service en zijn ongemoeid.
`stripe_handler.py` verifieert al zelf via `stripe.Webhook.construct_event` met de geconfigureerde
secret (geen fail-open pad).

---

## C. De implementatie

### `src/core/services/stripe_service.py`

- Nieuw: `StripeNotConfiguredError(RuntimeError)` en `StripeWebhookSecretMissingError(RuntimeError)`.
- `create_donation_checkout_session()`: mock-blok verwijderd; bij ontbrekende API key
  `raise StripeNotConfiguredError`. Retourneert verder `(checkout_url, session_id)` zoals voorheen.
- `construct_webhook_event()`: fail-closed herschreven.
  - Geen secret -> `StripeWebhookSecretMissingError`, payload wordt niet geparsed.
  - Geen `Stripe-Signature`-header -> `ValueError`.
  - Ongeldige signature -> `ValueError` (wrapt `stripe.error.SignatureVerificationError`; het
    Stripe-foutbericht zelf wordt niet verder gelekt dan de log).
  - De API-key-eis (`not self.api_key`) is uit de webhook-conditie verwijderd: signature-verificatie
    heeft volgens Stripe alleen het endpoint-secret nodig. De oude koppeling maakte de webhook
    fail-open zodra alleen de API key ontbrak -- een tweede, stille fail-open route.

### `src/core/api/v1/foundation/donations.py`

- `stripe_service` + beide exceptions nu via `dependencies.py` (ADR-033-facade; de gemeten
  schending op regel 30 is weg).
- Checkout-endpoint: `StripeNotConfiguredError` -> HTTP 503
  ("Betalingen zijn tijdelijk niet beschikbaar."), VOOR de INSERT. Geen donatie-rij bij 503.
- Webhook-endpoint: `StripeWebhookSecretMissingError` -> HTTP 503; overige verificatiefouten ->
  HTTP 400. Beide paden raken de database niet (verificatie staat voor elke query).
- Stripe-fouten van de SDK zelf (netwerk/API) blijven HTTP 500, zoals voorheen.

### `src/core/api/v1/foundation/dependencies.py`

- Re-exports toegevoegd: `stripe_service`, `StripeService`, `StripeNotConfiguredError`,
  `StripeWebhookSecretMissingError` (in `__all__`).

### Bewuste niet-productie-guard voor de verwijderde dev-flow

Er is geen legitieme dev-flow meer die nep-donaties persisteert. Wie lokaal donaties wil testen
gebruikt Stripe's eigen pad: `stripe listen` levert een echte `whsec_...` test-secret en
testmode-API-keys (`sk_test_...`) waarmee checkout en webhook volledig echt draaien
(https://docs.stripe.com/webhooks, "Test locally without a registered URL"). Dat is de enige
ondersteunde route; een mock die dezelfde database-rijen schrijft als echte betalingen is per
definitie niet te onderscheiden van fraude in de transparantiestatistieken.

---

## D. Rode -> groene bewijzen (gemeten, niet beschreven)

Rode run (nieuwe tests tegen de ONGEWIJZIGDE broncode, via `git stash push -- src/`):
`5 failed, 9 passed` in `test_foundation_donations.py` -- precies de vijf nieuwe guards rood:

- `test_create_donation_checkout_without_stripe_keys_returns_503`
- `test_webhook_without_secret_returns_503_and_no_state_change`
- `test_webhook_with_wrong_signature_returns_400_and_no_state_change`
- `test_webhook_without_signature_header_returns_400`
- `test_webhook_service_never_parses_without_secret`

Groene run na implementatie: `24 passed` over `test_foundation_donations.py` +
`test_foundation_contact.py` + `test_monetization_phase2_behavioral.py`.

De valide-signature-test tekent zelf per het v1-scheme
(`t=<unix>,v1=HMAC-SHA256(secret, "{t}.{payload}")`) en laat `stripe.Webhook.construct_event` het
echte verificatiepad inclusief timestamp-tolerance doorlopen -- geen gemockte verificatie.
Het test-secret is uit fragmenten opgebouwd (scan-secrets-hook) en is een test-only waarde.

State-wijzigings-guards: op elk foutpad is `session.execute.await_count == 0` en
`session.commit.await_count == 0` (geen enkele query, dus geen state-wijziging mogelijk).

---

## E. Regressiemetingen

| Meting | Voor | Na |
| --- | --- | --- |
| ADR-033 violations (`dsm_api_violation_finder.py`) | 5 | 4 |
| core_api fan-out (unieke paren, budget 572) | 589 (rood, pre-existing) | 588 (rood, pre-existing, -1) |
| `tests/architecture` volledige suite | 65 falende nodeids | 65 falende nodeids -- IDENTIEKE set (junit-xml diff: 0 nieuw, 0 opgelost) |
| Unit-subset `-k "foundation or stripe or webhook or billing"` | 2 failed + 1 error (pre-existing, stash-bewezen) | idem + mijn 24 groen |
| ruff op de 5 gewijzigde bestanden | -- | schoon |
| mypy op de 3 gewijzigde bronbestanden | 16 errors (pre-existing, alle in niet-door-mij-gewijzigde bestanden) | 16 errors -- identiek, 0 nieuw |
| ASCII-scan op de 5 gewijzigde bestanden | -- | clean |
| `datetime.now()/utcnow()` | -- | niet toegevoegd (tests gebruiken `time.time()` en tz-aware `datetime(...)`) |

Pre-existing, NIET door deze taak veroorzaakt en bewust niet gefixt (buiten scope):
`test_foundation_datetime_conformance` (datetime.now in `newsletter.py:183,315`),
`test_foundation_settings.py::test_get_settings_not_found`,
`tests/unit/scripts/test_goedgekeurd_maar_niet_geland_valt_op.py` (collection error),
de resterende 4 ADR-033-violations in `curatie.py`, `newsletter.py`, `upload.py`.

---

## F. Acceptatiecriteria

- [x] Webhook zonder geconfigureerde secret -> 503, payload nooit geparsed, geen state-wijziging
- [x] Webhook met verkeerde/ontbrekende signature -> 400, geen state-wijziging
- [x] Webhook met correcte signature -> verwerkt, donatie `pending` -> `completed`
- [x] Checkout zonder Stripe-keys -> 503, geen mock-sessie, geen donatie-rij
- [x] Donatie- en contact-testbestanden collecteren en draaien groen
- [x] ADR-033-schendingen in eigen bestanden gedicht (5 -> 4 gemeten)
- [x] Geen nieuwe architecture-failures; geen nieuwe mypy-errors; ruff schoon

## Open aannames

- Geen. De markt-review-bevindingen zijn allemaal her-verifierd tegen de code (sectie B).

## Open vragen

- Moet de resterende ADR-033-violatie-set (`curatie.py`, `newsletter.py`, `upload.py`) in een
  eigen taak? Die bestanden vallen buiten Taak B.

## Risico's

- Omgevingen zonder `STRIPE_WEBHOOK_SECRET` krijgen nu 503 op de webhook in plaats van stil
  vervalste donaties te accepteren. Dat is het beoogde gedrag, maar vereist dat staging/productie
  de secret daadwerkelijk zetten -- anders blijven donaties op `pending` staan. Dit moet in de
  deploy-checklist.
- `BE-EP-046`-spec en `review-BE-EP-046.md` beschrijven het mock-fallback-gedrag nog als feature;
  die documenten zijn met deze spec achterhaald op dat punt.

---

## Trainingssamenvatting

- **Actor:** Stripe (betaalprovider) die een webhook-event POST naar het endpoint, of een aanvaller die een vervalst event POST.
- **Voorwaarde:** De omgeving heeft STRIPE_WEBHOOK_SECRET gezet; zonder secret weigert het endpoint met 503 voordat de payload wordt gelezen.
- **Actie:** POST van een webhook-payload met Stripe-Signature-header naar het donatie-webhook-endpoint.
- **Systeemverwerking:** De service verifieert de signature per het Stripe v1-scheme (HMAC-SHA256 over "t.payload", timing-safe vergelijking, tolerance-venster) via de officiële SDK; pas bij een geldige signature wordt het event geparsed en de donatie-status gemuteerd.
- **Succesrespons:** HTTP 200 en de donatie-transitie wordt precies een keer vastgelegd; zonder secret, zonder header of met een foute signature: 503/400 en nul database-mutaties.
- **Foutrespons:** 503 bij ontbrekende configuratie (fail-closed), 400 bij ontbrekende of ongeldige signature; geen enkel pad accepteert een ongeverifieerde payload meer.
