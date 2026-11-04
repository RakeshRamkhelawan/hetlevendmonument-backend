# Review BE-SEC-058: Stripe-webhook fail-closed + mock-checkout-fallback verwijderd

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen). Code niet zelf geschreven; worktree read-only gereviewd. Elke claim uit commit en spec is zelf met commando's her-verifierd; niets op aannames overgenomen.
**Datum:** 2026-09-24
**Scope:** commit `0d3751439f2de3a9c4da4eee89a377f2061a25b2` op branch `iter/wk1-stripe-fail-closed` -- `src/core/services/stripe_service.py`, `src/core/api/v1/foundation/donations.py`, `src/core/api/v1/foundation/dependencies.py`, `tests/unit/test_foundation_donations.py`, `tests/unit/test_foundation_contact.py`, spec `docs/backend/features/BE-SEC-058-stripe-webhook-fail-closed.md`. Context gelezen: `webhooks.py` (brevo-pad), `api/webhooks/stripe_handler.py`, `unified_config.py`, geinstalleerde stripe-SDK 7.0.0 (broncode), https://docs.stripe.com/webhooks/signature (gefetcht).

---

## B. Eindoordeel

APPROVED WITH MINOR GAPS -- alle vier de oorspronkelijke klachten zijn aantoonbaar en correct gefixt; geen HIGH-bevindingen. De webhook is echt fail-closed (codepad-gelezen, niet alleen test-naam-gelezen), de mock-fallback is volledig weg (grep: nul restanten, geen verborgen vlag), de zelf-getekende signature-test is byte-exact het officiële v1-scheme (geverifieerd tegen zowel de Stripe-docs als de broncode van de geinstalleerde SDK 7.0.0), en de ADR-033-schending in `donations.py` is weg (finder: 5 -> 4, donations afwezig). De minor gaps: (1) de nieuwe fail-closed-houding is niet doorgetrokken naar de twee andere webhook-ingangen -- `webhooks.py` (brevo) heeft nog een expliciete fail-open ("if no secret configured, permit request") en `stripe_handler.py` is met een lege secret forgeerbaar (HMAC met lege sleutel is publiek berekenbaar) -- beiden pre-existing en buiten scope, maar nu wel inconsistent beleid; (2) een handvol LOW's (bros exception-assertie, ontbrekende commit-guard in een test, status-code-orakel 503/400). Niets daarvan blokkeert de merge; het deploy-risico (503 zonder `STRIPE_WEBHOOK_SECRET`) is correct en eerlijk benoemd in de spec.

## C. Samenvatting

Verificatie met eigen runs vanuit de worktree (venv van de hoofdrepo):

- **24/24 tests groen** (`test_foundation_donations.py` + `test_foundation_contact.py` + `test_monetization_phase2_behavioral.py`, 2.24s) -- exact zoals de commit claimt.
- **Ruff schoon** op alle vijf gewijzigde code/testbestanden.
- **mypy: 16 errors, 0 in de gewijzigde bestanden** -- alle 16 zitten in `curatie.py` (1), `map.py` (4), `upload.py` (4), `foundation_storage.py` (7), allemaal onaangeraakt door deze commit. Commit-claim "0 nieuw" bevestigd.
- **ADR-033-finder: 4 violations**, donations.py niet meer in de lijst; parent-commit had de directe import op regel 30 (via `git show` bevestigd), dus 5 -> 4 klopt. De ceiling-test `test_dsm_api_violations.py` is rood (4 > ceiling 0) maar was dat op de parent ook (5 > 0): pre-existing rood, verbeterd, niet verergerd.
- **Relevante architectuurtests: 15/15 groen** (`test_no_non_ascii_in_core_zone`, `test_no_naive_datetime`, `test_no_dead_imports_in_touched_modules`, `test_api_layer`, `test_dsm018_api_deps_facade`).
- **Unit-subset `-k "foundation or stripe or webhook or billing"`: 290 passed, 2 failed + errors** -- de 2 failures zijn exact de in de commit genoemde pre-existing (`test_foundation_datetime_conformance`, `test_foundation_settings::test_get_settings_not_found`); de errors zitten alle in het eveneens genoemde collection-error-bestand `test_goedgekeurd_maar_niet_geland_valt_op.py` (xdist telt het 4x). 0 nieuw.
- **ASCII-scan op alle zes gewijzigde bestanden: clean** (byte-niveau, niet alleen grep). **Geen `datetime.now()`/`utcnow()`** in de gewijzigde bestanden. **Geen letterlijke `whsec_`-string** in `src/` of de tests -- het test-secret is uit fragmenten opgebouwd, zoals gedocumenteerd.
- **Facade:** import-test gedraaid -- geen circulaire import, `stripe_service` + beide exceptions in `__all__`, en `donations.stripe_service is dependencies.stripe_service` (dezelfde singleton).
- **Blast-radius-claim uit de spec geverifieerd:** `construct_webhook_event` en `create_donation_checkout_session` hebben elk precies een aanroeper (grep); `stripe_handler.py` en `billing_endpoints.py` gebruiken andere paden.

Niet herhaald: de rood->groen stash-proef (worktree is read-only; stashen zou de working tree muteren). In plaats daarvan is de plausibiliteit op code-niveau bevestigd: tegen de oude code (`if not secret or not self.api_key: json.loads(...)`) zou de 503-webhook-test de payload geparsed hebben en doorgevallen naar een ongepatchte `public_tenant_scope` -- geen HTTPException 503, dus rood; de checkout-503-test zou een `mock_sess_`-response hebben gekregen in plaats van een raise -- rood. De claim "5 failed / 9 passed -> 24 passed" is consistent met de codepaden.

## D. Bevindingen per categorie (samengevat)

1. **Security** -- Kern is sterk en echt fail-closed. Alle drie de weiger-paden (geen secret, geen header, foute signature) staan in `construct_webhook_event` vóór elke parse, en in het endpoint vóór `public_tenant_scope` en elke query; er is geen pad dat zonder geldige signature state muteert. De timing-vergelijking is safe: SDK 7.0.0 gebruikt `util.secure_compare` = `hmac.compare_digest` (broncode gelezen), replay-tolerance default 300s (`Webhook.DEFAULT_TOLERANCE`, gelezen), tolerance-check aanwezig in `verify_header`. De api-key-eis terecht uit de webhook-conditie: Stripe-docs (gefetcht) bevestigen dat `construct_event(request_body, signature, endpoint_secret)` alleen het endpoint-secret nodig heeft. Checkout: `StripeNotConfiguredError` wordt gegooid vóór de INSERT; geen donatie-rij bij 503 (code-volgorde geverifieerd + test assert `not session.add.called`). Response-details leken geen Stripe-internals (statische strings; SDK-fouttekst gaat hooguit naar de log). Zwaktes: het brevo-webhook-pad blijft bewust fail-open en `stripe_handler.py` is bij lege secret forgeerbaar (MEDIUM-1, beide pre-existing); 503-vs-400 is een configureerbaarheids-orakel (LOW); geen rate-limit op het webhook-endpoint (LOW, afgedekt door `MaxRequestBodySizeMiddleware` -- bestaan geverifieerd -- en goedkope HMAC).
2. **Correctheid** -- De vijf fail-closed-guards testen gedrag, geen implementatie: echte endpoint-functies, echte `stripe.Webhook.construct_event` (niets gemockt in het verificatiepad), state-guards op `session.execute.await_count == 0` / `commit.await_count == 0`. De valide-signature-test laat de echte SDK het complete verificatiepad doorlopen (HMAC + scheme-filter + tolerance). Geen tautologie gevonden. Brossheid: exception-assertie op klasse-naam-string (LOW-2), ontbrekende commit-guard in een test (LOW-3).
3. **Architectuur** -- ADR-033-facade correct: `donations.py` importeert de service alleen nog via `dependencies.py`; `__all__` compleet; geen circulaire import (import-run geverifieerd); DSM-finder 5 -> 4 zonder nieuwe schendingen. `donations.py` importeert nog wel `config` direct, maar `unified_config` staat niet in de FORBIDDEN_MODULES van de finder -- geen gemeten schending, conform de bestaande conventie in buurbestanden.
4. **Tests** -- De twee eerder niet-collecterende bestanden collecteren en draaien (24 groen). Dekking is betekenisvol: 503 zonder keys (checkout EN webhook), 400 bij foute signature EN bij ontbrekende header, happy-path met echte signature, stats-masking, admin-lijst, registry-regels. Gaten zijn klein (zie E/F).
5. **Regels** -- ASCII clean (byte-scan), geen `datetime.now()` toegevoegd (tests gebruiken `time.time()` en tz-aware `datetime(...)`), geen letterlijke secrets, ruff schoon, mypy 0 nieuw.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| MEDIUM | `webhooks.py:65-67` + `api/webhooks/stripe_handler.py:39-41` (beide PRE-EXISTING, buiten scope) | De fail-closed-houding van BE-SEC-058 is niet doorgetrokken naar de andere twee webhook-ingangen. Brevo: expliciete fail-open -- "If no secret is configured (dev/test), permit request" -- dus een ongeconfigureerde omgeving accepteert ongeverifieerde bounce/unsubscribe-events die `NewsletterSubscription.status` muteren. Stripe subscription-handler: `construct_event(payload, sig, config.stripe_webhook_secret)` zonder empty-guard; bij een lege secret is de HMAC-sleutel "" en kan iedereen een geldige `v1`-signature berekenen -- verification passeert dan voor vervalste events. Impact lager dan donaties (geen geld-stroom, geen transparantiestatistieken), maar het beleid is nu intern inconsistent: de ene webhook faalt dicht, de andere open. | Follow-up-taak: dezelfde missing-secret-guard (`...SecretMissingError` -> 503) toepassen op `stripe_handler.py`, en voor brevo kiezen: fail-closed in productie (`ENVIRONMENT=production` -> 503 bij ontbrekende secret) met bewuste dev-uitzondering, gedocumenteerd. Niet blokkerend voor deze merge. |
| LOW | `donations.py:238-252` | Configureerbaarheids-orakel: 503 ("verification is not configured") vs 400 ("signature verification failed") vertelt een aanvaller of `STRIPE_WEBHOOK_SECRET` gezet is. Niet misbruikbaar voor vervalsing (de fix sluit juist dat pad), alleen informatief. | Accepteren en bewust documenteren, of detail uniformeren. Geen actie nodig. |
| LOW | `test_foundation_donations.py:440` | `test_webhook_service_never_parses_without_secret` assert op `exc_info.value.__class__.__name__ == "StripeWebhookSecretMissingError"` -- een string-vergelijking die een rename of een same-named decoy niet vangt. | Importeer de exception-klasse in de test en assert met `pytest.raises(StripeWebhookSecretMissingError)`. |
| LOW | `test_foundation_donations.py:369-387` | `test_webhook_without_signature_header_returns_400` assert alleen `session.execute.await_count == 0`, niet `commit.await_count == 0` (de andere twee faal-paden asserten beide). | Eén regel toevoegen; consistentie. |
| LOW | `donations.py` (webhook-endpoint) | Geen rate-limit-decorator op het webhook-endpoint (checkout heeft `portal_public_write_limit`). Pre-existing. Impact klein: body-lezing is gecapt door `MaxRequestBodySizeMiddleware` (bestaan geverifieerd in `middleware_config.py`) en HMAC-verificatie is goedkoop; wel kan een aanvaller bij ontbrekende secret ERROR-logregels genereren (log-spam). | Bewust laten (Stripe retries vereisen bereikbaarheid) of een ruime limiet toevoegen; minimaal benoemen in de spec onder Risico's. |
| LOW | `stripe_service.py:206` | `webhook_secret or getattr(config, ...)`: een aanroeper die expliciet een lege string meegeeft valt stil terug op de config-waarde. Verwarrend, geen security-issue (lege config leidt alsnog tot de missing-error). | `webhook_secret if webhook_secret is not None else ...` als de override-semantiek ooit uitgebreid wordt; nu accepteren. |

## F. Ontbrekende items

- Follow-up-ID voor de inconsistente webhook-beveiliging (MEDIUM-1): brevo fail-open + `stripe_handler.py` empty-secret-forgeability. Dit is de enige gap die expliciet een vervolgtaak verdient; nu staat hij nergens vast.
- De twee LOW-testaanscherpingen (exception-klasse i.p.v. naam-string; commit-guard in de missing-header-test).
- Optioneel: opname van "webhook-endpoint heeft geen rate-limit (bewust)" in de spec-Risico's.
- De stash-proef (rood->groen) is door de schrijver gedocumenteerd maar door deze review niet herhaald (read-only worktree); op code-niveau plausibel bevonden. Bij twijfel: eenmalig herhalen in een wegwerp-worktree.

## G. Verbeterde codevoorstellen

Test (sterkere assertie):

```python
from src.core.api.v1.foundation.dependencies import StripeWebhookSecretMissingError

with patch.object(config, "stripe_webhook_secret", ""):
    with pytest.raises(StripeWebhookSecretMissingError):
        stripe_service.construct_webhook_event(
            b'{"type": "checkout.session.completed"}',
            "t=1,v1=abc",
        )
```

Follow-up `stripe_handler.py` (zelfde guard als BE-SEC-058):

```python
secret = config.stripe_webhook_secret
if not secret:
    logger.error("Stripe subscription webhook refused: webhook secret not configured")
    raise HTTPException(status_code=503, detail="Webhook verification is not configured")
event = stripe.Webhook.construct_event(payload, stripe_signature, secret)
```

Follow-up brevo (`webhooks.py:_verify_webhook_secret`): in `ENVIRONMENT=production` ontbrekende `brevo_webhook_secret` behandelen als 503 i.p.v. permit; dev/test-behoud expliciet documenteren.

## H. Release-oordelen

- Bouw/implementatie: **ja**.
- QA/geautomatiseerd testen: **ja** (24/24 groen; guards testen gedrag met de echte SDK; twee LOW-aanscherpingen als opvolgpunt).
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja** -- spec klopt met de code (alle metingen uit sectie B/D/E door deze review bevestigd) en het deploy-risico (omgeving zonder `STRIPE_WEBHOOK_SECRET` krijgt 503; donaties blijven `pending` tot de secret gezet is) is correct benoemd inclusief deploy-checklist-eis. Wel het MEDIUM-1-follow-up expliciet in de tracker/registry vastleggen.

## Wat wel klopt

- Echt fail-closed op code-niveau: alle drie de weiger-paden staan vóór elke parse/query; geen enkel pad muteert state zonder geldige signature. De oude fail-open (`json.loads` bij lege secret OF ontbrekende api-key) is volledig verwijderd, niet omzeild.
- Mock-fallback volledig weg: grep op `mock_sess|mock_checkout|allow_unsigned|skip_verification|STRIPE_MOCK|MOCK_STRIPE` in `src/` levert nul hits; er is geen verborgen vlag of omgevingsdetectie.
- De zelf-getekende signature is het echte v1-scheme: `signed_payload = "{t}.{payload}"`, `v1 = HMAC-SHA256(secret, signed_payload)` -- byte-exact zoals de geinstalleerde SDK 7.0.0 het verifieert (`WebhookSignature.verify_header`, broncode gelezen) en zoals https://docs.stripe.com/webhooks/signature het beschrijft (`construct_event(request_body, signature, endpoint_secret)`, header `t=...,v1=...`). De valide-signature-test mockt niets in het verificatiepad.
- Timing-safe: `secure_compare` is `hmac.compare_digest` (SDK-broncode); replay-tolerance 300s default actief.
- De api-key-eis terecht uit de webhook-conditie: Stripe-documentatie bevestigt dat alleen het endpoint-secret nodig is; de oude koppeling was een tweede stille fail-open route (lege api-key -> ongeverifieerde parse) die nu ook dicht is.
- 503-plaatsing checkout: de raise staat vóór de INSERT; test bewijst `not session.add.called` en `commit.await_count == 0`. Geen nep-donatie kan meer ontstaan.
- Blast-radius-discipline: precies een aanroeper per gewijzigde methode (grep-geverifieerd); subscription-flows ongemoeid; spec benoemt dit eerlijk.
- ADR-033: facade-re-exports correct in `__all__`, geen circulaire import (import-run), zelfde singleton-object; finder 5 -> 4 zonder nieuwe schendingen; ceiling-test was al rood en is niet verergerd.
- Eerlijke meetcultuur in commit en spec: pre-existing failures worden met naam genoemd (datetime-conformance, settings-not-found, collection-error) en door deze review exact zo aangetroffen; de webhooks.py-nuancering in spec-sectie B (connectors niet in FORBIDDEN_MODULES, bewust ongemoeid) klopt met de finder-output.
- Dev-flow-vervanging is reeel en gedocumenteerd: `stripe listen` + testmode-keys is Stripe's eigen ondersteunde pad; de spec legt uit waarom een mock die echte tabellen schrijft per definitie fraude-vervaling is.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **De fix lost het patroon op, niet de klasse.** BE-SEC-058 dichtt het donatie-webhook-pad, maar hetzelfde beveiligingsgat bestaat nog twee keer: brevo accepteert ongeverifieerde events als de secret ontbreekt (bewust, in een commentaarregel verankerd -- dat is het gevaarlijkste soort fail-open, want het leest als feature), en `stripe_handler.py` is bij een lege secret forgeerbaar omdat HMAC met een lege sleutel publiek berekenbaar is. Zonder follow-up-ID met eigenaar is dit precies het type "uitgestelde security-work" dat verdwijnt -- tot de eerste vervalste unsubscribe-golf of subscription-event.
2. **De 503 wordt een stille donatie-stop.** De spec noemt het deploy-risico, maar er is geen runtime-alarm: als staging/productie de secret niet zet, falen webhooks met 503 en blijven donaties eeuwig op `pending` -- voor de stichting ziet dat er uit als "niemand doneert meer". Een startup-check ("STRIPE_WEBHOOK_SECRET ontbreekt terwijl STRIPE_API_KEY gezet is -> weiger te bootsen of alarm") ontbreekt; de eerste signalering is een boze curator, niet een monitor.
3. **De guards bewaken de aanroeper, niet de dienst.** Alle fail-closed-tests gaan via `donations.py`. Een toekomstige tweede aanroeper van `construct_webhook_event` (of een refactor die de endpoint-try/except versmalt) erft de service-guard wel, maar de HTTP-vertaling (503 vs 400 vs 500) niet noodzakelijk -- de vertaallaag zit in het endpoint, niet in de service. Een endpoint-niveau contracttest per toekomstige aanroeper is niet afgedwongen.
4. **Het test-secret-fragment-patroon is een uitnodiging tot copy-paste.** `TEST_WEBHOOK_SECRET = "whsec" + ...` omzeilt de secret-scanner legitiem, maar normaliseert een truc die een volgende developer ook voor een echte secret kan gebruiken. De scanner blijft dan groen terwijl er een echte `whsec_` in de repo staat. De scanner-regel ("geen letterlijke whsec_-strings") is zo effectief uitgehold zonder dat iemand het doorheeft.
5. **Pre-existing rood wordt dragelijk.** Deze commit laat bewust 65 falende architecture-nodeids, 4 ADR-033-violations boven een ceiling van 0, en 2 falende unit-tests staan. Elke individuele keuze is verdedigbaar (buiten scope, gemeten, benoemd), maar het cumulative effect is dat "rood" de normale achtergrondkleur wordt -- en in een rode achtergrond valt de volgende ECHTE regressie niet meer op. De junit-diff-discipline van deze commit is het juiste middel; het moet wel een blokkerende CI-stap worden, niet een handmatige gewoonte.

Geen van deze punten blokkeert deze merge: punt 1 vereist een benoemde follow-up, punt 2 een monitoring-/startup-check, punt 3-5 zijn proces- en hygienerisico's. De kernfix zelf is correct, gemeten en eerlijk gedocumenteerd.
