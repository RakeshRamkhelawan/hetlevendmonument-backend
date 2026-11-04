# BE-SEC-056 — Cross-tenant tenant-match op admin donations/contact + whitespace-secret fail-closed + quick-login default visitor

**Datum:** 2026-09-24
**Aanleiding:** verplichte onafhankelijke eindreview (final-approver-pijplijn) van de
Week-1 delta gaf NO-GO met één BLOCKER (B1) en vijf minors; B1, B2, B5, B6 zijn in deze
knip gerepareerd. B3 (timing-enumeratie password-login) en B4 (oude-positie-scenario
edu_alignment) blijven als benoemde restpunten.

## B. Gemeten uitgangssituatie (rood)

**B1 (BLOCKER) — cross-tenant PII-lek.** `require_curator` valideert de JWT (aud, scope,
tenant-claim) maar vergeleek de token-tenant nooit met de tenant uit het pad. Twee
admin-endpoints richtten daardoor hun query alleen op de pad-tenant:

- `src/core/api/v1/foundation/donations.py` `list_admin_donations` — geeft donor-e-mails,
  namen, bedragen en stripe_session_ids terug.
- `src/core/api/v1/foundation/contact.py` `list_contact_submissions` — geeft namen,
  e-mails en vrije-tekst-berichten terug.

Gevolg: een curator van tenant A las met zijn eigen geldige JWT de PII van tenant B uit.
Het patroon `if current_user.tenant_id != tenant.id: raise 403` stond al op 11 plekken in
`admin/curatie.py`, 3 in `edu.py` (BE-SEC-057) en 1 in `settings.py` — donations en contact
waren de enige twee require_curator-endpoints zonder de check (inventarisatie via grep op
`Depends(require_curator)`).

**B2 — whitespace-secrets.** `webhooks.py` (`if not configured`), `stripe_handler.py`
(`if not webhook_secret`) en `stripe_service.py` (`if not secret`) lieten een secret van
alleen spaties door als "geconfigureerd" — truthy, dus de fail-closed guard (BE-SEC-058/055)
werd gepasseerd terwijl er feitelijk geen secret is.

**B6 — quick-login default.** `auth.py` mintte bij `role=None` een admin-account
(`data.role or "admin"`; else-tak dwong zelfs onbekende rollen naar admin). Alleen bereikbaar
binnen de dev/test-allowlist (BE-SEC-055c), maar de default was niet least-privilege.

**B5 — commentaar-drift.** `scripts/run_ci_act.ps1` noemde "eslint" in de portal-batch
terwijl de portal-job bewust geen lint-stap heeft (dode eslint-stub, zie bevindingen-brief
2026-09-24-bevinding-portal-lint-stub).

## C. Implementatie

1. `donations.py` / `contact.py`: direct na `public_tenant_scope` dezelfde tenant-match als
   curatie.py (`current_user.tenant_id != tenant.id` → HTTP 403 "User does not belong to
   this tenant"), voor elke query. `contact.py` kreeg `HTTPException` bij de fastapi-import.
2. Whitespace-guards: `if not configured or not configured.strip()` (brevo),
   `if not webhook_secret or not webhook_secret.strip()` (stripe_handler),
   `if not secret or not secret.strip()` (stripe_service).
3. `auth.py` quick-login: default `visitor`; expliciete `admin`/`curator` blijft werken
   binnen de allowlist; onbekende rolstrings vallen nu naar visitor (fail-safe) i.p.v. admin.
   Gate-2 vond dat dit op het HTTP-oppervlak dode code was:
   `QuickLoginRequest.role` had schema-default `"admin"` (schemas.py). Daarom ook:
   schema-default naar `"bezoeker"` + regressietest die `QuickLoginRequest()` zonder rol
   zowel op schema- als op endpoint-niveau visitor bewijst.
4. `run_ci_act.ps1`: commentaar gecorrigeerd (geen eslint in portal-job).

## D. Rood -> groen bewijzen

- Rood: met de twee src-fixes tijdelijk gestasht faalden
  `test_list_admin_donations_rejects_cross_tenant_curator` en
  `test_list_contact_submissions_rejects_cross_tenant_curator` (2 failed); met de fix
  teruggezet groen. Beide asserten 403 én `session.execute.assert_not_called()`
  (geen data-aanraking bij vreemde tenant).
- Whitespace: drie nieuwe tests (brevo 503, stripe_handler 503 + `construct_event`
  niet aangeroepen, stripe_service `StripeWebhookSecretMissingError`).
- Bestaande suites bijgewerkt waar ze op het oude gedrag leunden: mock-curators kregen een
  `tenant_id` dat bij hun mock-tenant hoort (geen asserties verwijderd).
- Eindmeting gericht: **53 passed** (donations, contact, brevo fail-closed, webhook
  handlers, password-login/quick-login) in 11.85s.
- `ruff check` op alle 11 gewijzigde bestanden: schoon.

## E. Restpunten (benoemd, niet meegenomen)

- **B3**: password-login geeft bij onbekende user 401 vóór bcrypt-verificatie
  (timing-enumeratie). Pre-existing patroon, niet verergerd; uniforme-timing-fix is een
  eigen beslissing (extra bcrypt-dummy-verify kost ~250 ms per mislukte login).
- **B4**: herschreven edu_alignment berust voor het "oude ketenpositie al toegepast"-
  scenario op een meting (staging had geen code_hash, productie niet ingericht), geen hard
  bewijs. Verse-DB-keten is integratiegetest; dat scenario niet.
- Gate-3: volledige poortrun op de commit van deze fix draait als eindmeting (zie
  final-approver brief 2026-09-24-final-approver-week1-blokkers.md).

## Trainingssamenvatting

- **Actor:** Een curator van tenant A met een geldige JWT die het admin-endpoint van
  tenant B aanroept; een operator die per ongeluk een whitespace-webhook-secret
  configureert; een developer die quick-login zonder rol aanroept.
- **Voorwaarde:** De curator-JWT is geldig (aud/scope/rol kloppen) maar hoort bij een
  andere tenant dan de tenantSlug in het pad.
- **Actie:** GET op `/{tenantSlug}/foundation/admin/donations` of
  `/admin/contact-submissions`; POST op een webhook met whitespace-secret-configuratie;
  POST quick-login zonder rol.
- **Systeemverwerking:** De endpoint vergelijkt `current_user.tenant_id` met de
  pad-tenant vóór elke database-aanraking; de webhook-guards behandelen whitespace als
  "niet geconfigureerd"; quick-login kiest bij ontbrekende rol de laagste rol.
- **Succesrespons:** Eigen-tenant curator krijgt zijn eigen data (200); webhook met echt
  secret werkt ongewijzigd; quick-login in development mint een visitor-token.
- **Foutrespons:** Cross-tenant curator: 403 zonder query-uitvoering; whitespace-secret:
  503 / `StripeWebhookSecretMissingError`; quick-login buiten allowlist: 403.
