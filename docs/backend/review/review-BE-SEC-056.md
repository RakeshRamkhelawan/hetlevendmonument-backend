# Review BE-SEC-056: Cross-tenant tenant-match op admin donations/contact + whitespace-secret fail-closed + quick-login default visitor

STATUS: APPROVED WITH MINOR GAPS

**Reviewer:** onafhankelijke Gate 2-review-agent (code-reviewer + quality-reviewer ineen, Red Team). Code niet zelf geschreven. Elke claim uit commit en spec is zelf met commando's her-verifierd op branch `develop` bij commit `ed2c99f21`; het rood-bewijs is niet overgenomen maar zelf gereproduceerd tegen de pre-fix code.
**Datum:** 2026-09-25
**Scope:** commit `ed2c99f21` op `develop` (11 bestanden) + spec `docs/backend/features/BE-SEC-056-cross-tenant-tenant-match.md`. Context gelezen: alle `require_curator`/`require_admin`/`require_portal_user`-usages in `src/core/api/v1/foundation/` (eigen grep), `settings.py` volledig, `stripe_service.py:188-215`, `unified_config.py:278`, `shared/config.py:172`, `foundation_tenant_resolver.py:320-343` (`public_tenant_scope`), `schemas.py:350-353` (`QuickLoginRequest`), `portal/src/api/client.ts:436-448` + `portal/src/pages/Login.tsx:115` (quick-login callers), `tests/unit/test_foundation_password_login.py` (quick-login tests).

---

## B. Eindoordeel

**Ronde 2 (2026-09-25, commit `32343cc54`): de HIGH-1-bevinding uit ronde 1 is volledig en correct gerepareerd.** Eindoordeel: APPROVED WITH MINOR GAPS -- niets blokkeert meer; de minor gaps zijn de niet-blokkerende Devil's Advocate-punten (geen architecture-guard op het kopieer-plak-tenant-match-patroon, geen wiring-tests, gedupliceerde whitespace-guards, quick-login-allowlist als heuristiek) plus de uit de spec benoemde pre-existing restpunten B3/B4.

Verificatie van de reparatie (zelf gedraaid):

- **Diff `32343cc54` gelezen:** `schemas.py` schema-default `"admin"` -> `"bezoeker"` (exact de voorgestelde een-regel-fix); nieuwe regressietest `test_quick_login_without_role_defaults_to_visitor` assert de default op TWEE niveaus -- `QuickLoginRequest().role == "bezoeker"` (schema-niveau) EN `quick_login(data=QuickLoginRequest())` -> `response["user"]["role"] == "visitor"`, JWT-rol `"visitor"`, aangemaakte `PortalUser.role == PortalRole.VISITOR` (endpoint-niveau). De spec (eerder untracked, LOW) is meegecommit.
- **Eigen test-run:** `test_foundation_password_login.py` -- **15 passed in 5.03s** (exact de verwachte 15; voorheen 14 + 1 nieuwe).
- **Rood-bewijs van de nieuwe test zelf gereproduceerd:** `git show 32343cc54^:schemas.py` tijdelijk teruggezet -> `test_quick_login_without_role_defaults_to_visitor` FAILED (`1 failed in 3.92s`); daarna hersteld en working tree schoon geverifieerd. De test bewaakt dus echt de schema-default, niet alleen de auth.py-laag.
- **Ruff schoon** op `schemas.py` + `test_foundation_password_login.py` ("All checks passed!").
- **Geen caller leunt op de oude admin-default:** eigen grep `QuickLoginRequest(` over `src/` toont alleen de schema-definitie zelf; de enige frontend-caller (`portal/src/api/client.ts:436`) vereist een expliciete `role` in het TypeScript-type en `Login.tsx:115` geeft die altijd mee; alle bestaande backend-tests geven een expliciete rol. De default-wijziging breekt dus geen enkele dev-flow -- en is nu, anders dan in ronde 1, ook daadwerkelijk effectief op de HTTP-route.

**Ronde 1 (hieronder, ongewijzigd als dossier):** CHANGES REQUESTED was het oordeel op `ed2c99f21` -- de hoofdclaim (B1, de BLOCKER) was volledig waar en bewezen (cross-tenant tenant-match correct, rood-bewijs zelf gereproduceerd `2 failed`, volledigheidsclaim van de require_curator-inventarisatie met eigen grep bevestigd, whitespace-guards None-safe, 53/53 groen), maar claim 3 (B6, quick-login default admin -> visitor) was op het echte HTTP-oppervlak onwaar: het Pydantic-schema `QuickLoginRequest.role` had nog default `"admin"` (`schemas.py:353`), waardoor een rol-loze POST via `Body(...)` nog steeds een admin-token mintte en `data.role or "visitor"` in `auth.py` via HTTP dode code was. Dat is precies de "lege default-fix" die een review moet vangen. De in ronde 1 voorgeschreven reparatie (schema-default + test) is in `32343cc54` exact zo uitgevoerd.

## C. Samenvatting

Verificatie met eigen runs vanuit de repo-root (venv van de repo):

- **53/53 tests groen**, exact de spec-claim: `test_foundation_donations.py` + `test_foundation_contact.py` + `test_brevo_webhook_fail_closed.py` + `tests/unit/api/test_webhook_handlers.py` + `test_foundation_password_login.py` -- `53 passed in 19.39s` (spec claimt 53 passed in 11.85s; aantal klopt exact).
- **Rood-bewijs zelf gereproduceerd (niet overgenomen):** `git show ed2c99f21^:donations.py/contact.py` tijdelijk teruggezet, de twee nieuwe cross-tenant tests gedraaid: `2 failed in 5.66s` -- daarna `git checkout --` hersteld en working tree schoon geverifieerd. De stash-proef uit de spec is hiermee onafhankelijk bevestigd.
- **Ruff schoon** (zelf gedraaid) op alle 10 gewijzigde Python-bestanden: "All checks passed!". (De `.ps1` geeft 239 ruff-"errors" maar dat zijn parse-artefacten -- ruff lint geen PowerShell; irrelevant.)
- **Volledigheidsclaim require_curator geverifieerd met eigen grep** (`require_curator|require_admin|require_portal_user` in heel `src/`): in `foundation/` zijn de require_curator-endpoints: curatie.py (11), edu.py (3), settings.py PUT (1), donations.py (1), contact.py (1) -- elk heeft nu een `current_user.tenant_id != tenant.id`-check (eigen grep op dat patroon: 11+3+1+1+1 treffers, per regelnummer gematched aan de endpoint-lijst). De require_portal_user-endpoints (content.py x3, takedown.py, upload.py) hadden de check al (r.128/201/236/308/370, r.61, r.122/408/450). `Depends(require_admin)` komt in foundation NIET voor (lege grep). De admin/routers daarbuiten (`api/v1/admin/`, user_management, hr, scheduling) gebruiken `require_admin_role`/`require_admin` met tenant uit de JWT-claim (ADR-003) -- dat is een ander tenant-model zonder pad-tenant en valt buiten deze kwetsbaarheidsklasse. De claim "curatie/edu/settings waren de enige andere" klopt dus.
- **settings.py PUT is gedekt** (r.89); de GET op `/settings` is bewust publiek (white-label branding, docstring r.36-39, `portal_public_read_limit`) en heeft terecht geen check.
- **403 vs 404 verdedigbaar:** `public_tenant_scope` resolved de tenant op slug en een onbekende slug faalt al eerder (resolver); tenant-existence is bovendien al publiek zichtbaar via de publieke portal-routes per slug. Een 404 bij tenant-mismatch zou dus niets verbergen dat niet al publiek is; 403 is consistent met de 15 bestaande matches in curatie/edu/settings/upload/takedown/content. Geen enumeratie-risico toegevoegd.
- **Bestaande tests niet verzwakt** (`git show ed2c99f21 -- tests/` gelezen): 102 insertions, 1 deletion. De enige deletion is `_create_mock_curator()` -> `_create_mock_curator(tenant_id=99)` in `test_list_admin_donations_endpoint` -- een aangescherpte precondition (mock-user hoort nu bij zijn mock-tenant), geen verwijderde of afgezwakte assertie. `_create_mock_curator` kreeg `tenant_id: int = 1` als parameter; de bestaande contact-test kreeg `curator.tenant_id = mock_tenant.id`. Nul asserties verwijderd.
- **Whitespace-guards None-safe (d):** `brevo_webhook_secret: str | None` (`shared/config.py:172`) -- `not configured or` short-circuit voorkomt AttributeError op None. `stripe_webhook_secret: str = Field(default="")` (`unified_config.py:278`) -- altijd str. `stripe_service.construct_webhook_event(payload, sig_header, webhook_secret: str | None = None)` (r.188-192) -- `not secret or` dekt None. Geen AttributeError-risico binnen de gedeclareerde types.
- **Quick-login callers (e):** de enige frontend-caller (`portal/src/api/client.ts:436`) vereist een expliciete `role: 'admin' | 'curator' | 'bezoeker'` en `Login.tsx:115` geeft die altijd mee; alle backend-tests geven een expliciete rol. Geen caller leunt op de Python-default -- de default-wijziging breekt dus niets, maar bereikt via HTTP ook niets (zie HIGH-1).
- **`run_ci_act.ps1`-commentaar (B5):** correctie klopt (geen eslint in portal-job); comment-only, geen gedrag.

## D. Bevindingen per categorie

1. **Security** -- B1 is echt gedicht en bewezen (zie C). De check staat binnen `public_tenant_scope` maar VOOR elke `session.execute`; de nieuwe tests asserten `session.execute.assert_not_called()`, dus de volgorde is testgedekt. B2: whitespace telt nu overal als niet-geconfigureerd; geen bypass gevonden via None/""/"   ". B6: NIET effectief op het HTTP-oppervlak -- zie HIGH-1.
2. **Correctheid** -- De twee cross-tenant tests testen gedrag (echte functie-aanroep, `pytest.raises` + statuscode + no-execute-assertie) en heb ik rood zien falen tegen pre-fix code. De whitespace-tests dekken de legitieme kant via de bestaande happy-path tests in dezelfde suites (groen in eigen run). De quick-login-default-wijziging heeft GEEN test: geen enkele test roept `quick_login` aan met `role=None` of assert de nieuwe visitor-default -- de wijziging is bovendien via HTTP onbereikbaar (HIGH-1).
3. **Architectuur** -- Geen nieuwe imports buiten bestaande lagen; de tenant-match kopieert exact het bestaande curatie/edu/settings-patroon (bewuste consistentie, geen nieuwe abstractie). Geen ADR-raakvlakken.
4. **Tests** -- Dekking voor B1 en B2 is betekenisvol en rood-bewezen. Gaten: geen test voor de quick-login-default (de claim van B6), geen HTTP-niveau test van de 403 via de echte route (unit-tests roepen de functie direct aan met gemockte scope; de dependency-wiring `Depends(require_curator)` -> endpoint is niet mee-gedekt -- zie Devil's Advocate 3).
5. **Regels** -- ASCII clean in de diff (geen non-ASCII toegevoegd), geen `datetime.now()`/`utcnow()`, geen echte secrets, ruff schoon (zelf gedraaid). Pyright niet zelf gedraaid in deze review -- zie F.

## E. Issue register

| Severity | Locatie | Probleem | Correctie |
| --- | --- | --- | --- |
| ~~HIGH~~ OPGELOST in `32343cc54` | `src/core/api/v1/foundation/schemas.py:353` + `auth.py:484` | **B6-claim was op het HTTP-oppervlak onwaar** (ronde 1): schema-default `"admin"` maakte de auth.py-default dode code via HTTP. | Uitgevoerd zoals voorgeschreven: schema-default `"bezoeker"` + `test_quick_login_without_role_defaults_to_visitor` (schema- EN endpoint-niveau). Rood-bewijs door reviewer gereproduceerd (1 failed tegen pre-fix schema). 15/15 groen. |
| ~~LOW~~ OPGELOST in `32343cc54` | `docs/backend/features/BE-SEC-056-cross-tenant-tenant-match.md` | De spec stond als UNTRACKED bestand in de working tree (ronde 1). | Spec meegecommit in `32343cc54`. |
| ~~LOW~~ OPGELOST in `32343cc54` | `tests/unit/test_foundation_password_login.py` | Geen test dekte quick-login zonder rol; een regressie van de default was onzichtbaar. | `test_quick_login_without_role_defaults_to_visitor` dekt dit nu op beide niveaus. |
| LOW | `auth.py` else-tak | De `else: role_str = "visitor"`-fail-safe is via HTTP onbereikbaar (Literal-validatie). Als defensieve laag prima, maar hij doet alsof hij een HTTP-invoerfilter is; dat is hij niet. | Eventueel commentaar bijwerken bij een volgende aanraking; niet blokkerend. |

## F. Ontbrekende items

- ~~HIGH-1-fix + test~~ -- OPGELOST in `32343cc54` (zie B, ronde 2).
- ~~De untracked spec committen~~ -- OPGELOST in `32343cc54`.
- **Pyright/mypy niet zelf gereproduceerd in deze review** (volledige importketen overschreed de timeout in eerdere reviews op deze repo). De diffs van beide commits raken geen type-annotaties en voegen alleen bestaande patronen toe; risico klein, maar de poort eist een meting: verifieer met `python -m pyright` (geen args) op de merge-branch.
- De HTTP-wiring van de 403 (echte route met echte `Depends(require_curator)` JWT) is niet testgedekt; de unit-tests mocken `public_tenant_scope` en geven de user direct mee. Acceptabel voor deze fix (het gemockte pad is precies de regel die verandert), maar een toekomstige refactor van de dependency-keten wordt niet gevangen -- zie Devil's Advocate 3.

## G. Verbeterde codevoorstellen

HIGH-1-fix (een regel + test):

```python
# schemas.py
class QuickLoginRequest(BaseModel):
    """Development quick login request (bypasses email delivery)."""

    role: Literal["admin", "curator", "bezoeker", "visitor"] = "bezoeker"
```

```python
# tests/unit/test_foundation_password_login.py
async def test_quick_login_default_role_is_visitor(self) -> None:
    """BE-SEC-056: quick-login zonder rol mint een visitor-token (least privilege)."""
    # ... zelfde fixture-opzet als test_quick_login_creates_visitor_in_development,
    # maar met data=QuickLoginRequest() (geen role-argument) ...
    assert response["user"]["role"] == "visitor"  # of PortalRole.VISITOR-waarde
```

## H. Release-oordelen

- Bouw/implementatie: **ja** -- HIGH-1 is gerepareerd in `32343cc54` en de reparatie is door deze reviewer geverifieerd (diff gelezen, rood-bewijs van de nieuwe test zelf gereproduceerd, 15/15 groen, ruff schoon).
- QA/geautomatiseerd testen: **ja** -- 53/53 + 15/15 zelf gedraaid; rood-bewijs voor zowel de cross-tenant guards als de schema-default zelf gereproduceerd; bestaande tests niet verzwakt.
- LLM-training: **ja**.
- Integratorhandleiding / spec: **ja** -- de spec is nu gecommit en sectie C.3 beschrijft de Gate-2-vondst en de schema-fix eerlijk. Restpunten B3/B4 (pre-existing, benoemd) en de pyright/mypy-meting op de merge-branch blijven staan als verificatiepunten voor de eindmeting.

## Wat wel klopt

- B1 is volledig, correct en onafhankelijk bewezen: beide endpoints weigeren nu cross-tenant curators met 403 VOOR elke query; eigen rood-reproductie `2 failed` tegen pre-fix code; de volledigheidsclaim over de require_curator-inventarisatie heb ik met een eigen grep over heel `src/` bevestigd (inclusief dat `Depends(require_admin)` in foundation niet voorkomt en dat content/takedown/upload de check al hadden).
- De guard volgt exact het bestaande patroon (zelfde statuscode, zelfde detail-tekst, zelfde positie direct na `public_tenant_scope`) -- geen afwijkende derde variant.
- B2 is correct en None-safe op alle drie de plekken; de gedeclareerde types (`str | None`, `str`) maken `.strip()` veilig door de `not x or`-short-circuit.
- 403-vs-404 is doordacht verdedigbaar: tenant-existence per slug is al publiek (publieke portal-routes + resolver), dus 403 lekt niets extra's en blijft consistent met 15 bestaande matches.
- Eigen groen-bewijs: 53/53 (exact de spec-claim) en ruff schoon op alle gewijzigde Python-bestanden.
- Eerlijke meetcultuur in de spec: restpunten B3/B4 zijn benoemd, de testaantallen kloppen exact, en de rood-procedure is beschreven zoals ik hem heb gereproduceerd.
- Quick-login-callers geven overal een expliciete rol (portal `client.ts` vereist hem in het type); de Python-default-wijziging breekt geen bestaande dev-flow.

## Devil's Advocate -- waarom faalt deze oplossing in de toekomst?

1. **De tenant-match is een kopieer-plak-invariant, geen bewaakte invariant.** De check staat nu op 17 plekken letterlijk herhaald; het volgende nieuwe admin-endpoint in `foundation/` (nieuwsbrief-export, volunteer-lijst -- alles met PII) vergeet hem opnieuw, en niets faalt. Deze bug bestond alleen omdat het patroon per endpoint handmatig wordt bijgehouden in plaats van in `require_curator` zelf (die de pad-tenant niet kent -- dat is de architectuur-keuze, maar dan hoort er een architecture-guard te zijn: AST-scan dat elke `Depends(require_curator/require_portal_user)`-functie met `tenantSlug`-parameter een `tenant_id != tenant.id`-vergelijking bevat). Zonder die guard is BE-SEC-056 een momentopname, geen fix van de klasse -- precies het patroon dat de quality-gates bij guards eisen.
2. **De B6-fix laat zien hoe makkelijk een claim langs de echte route heen gaat -- en de testsuite hielp mee.** De wijziging in `auth.py` is correct Python maar dood via HTTP; geen enkele test merkte dat, omdat alle quick-login-tests de functie direct aanroepen met een zelf-gekozen `role` en geen enkele test `QuickLoginRequest()` zonder argumenten construeert. De fix keek naar de functie, niet naar het schema dat de functie voedt. Een volgende "default-hardening" op een ander endpoint zal dezelfde fout maken als de reviewer alleen de functie leest.
3. **De 403-tests bewijzen de functie, niet de wiring.** Beide cross-tenant tests mocken `public_tenant_scope` en geven een `MagicMock(spec=PortalUser)` direct mee; de echte keten JWT -> `require_portal_user` -> `PortalUser.tenant_id` uit de database -> endpoint is niet getest. Als `require_portal_user` ooit een stale of gepatchte `tenant_id` gaat leveren (denk aan het RBAC-cache-verhaal uit OP-254: een cache die in TESTING per constructie uit staat), blijven deze tests groen terwijl het lek terug is.
4. **`public_tenant_scope` zet de ContextVar op de PAD-tenant voordat de check draait.** De 403 gooit na `set_tenant_id(tenant.id)`; cleanup is gegarandeerd (try/finally, gelezen), dus geen lek naar de volgende request -- maar elke code die ooit VOOR de check in de scope iets logt of schrijft met de auto-tenant-filter (ADR-004) werkt dan onder de vreemde tenant. De volgorde "scope betreden, dan pas autorisatie checken" is inherent aan het patroon en wordt door geen test bewaakt.
5. **De whitespace-guard is nu op drie plekken handmatig gedupliceerd.** `sms_webhooks.py` (MessageBird) -- in de BE-SEC-055-review al als MEDIUM-1 benoemd -- heeft nog steeds zijn eigen variant; de vierde plek die een secret checkt zal opnieuw een eigen `if not secret` verzinnen. Een gedeelde `is_configured_secret(value)`-helper ontbreekt bewust (Simplicity First), maar de telling staat nu op minstens vier handmatige kopieen van dezelfde security-regel.
6. **Quick-login blijft een magic-endpoint met een brede allowlist.** Ook met visitor-default mint het endpoint zonder authenticatie geldige JWT's in elke omgeving die `development|dev|local|test|testing` heet -- inclusief een misgeconfigureerde container met `ENVIRONMENT=test`. De default naar visitor verkleint de opblaasstraal, maar de BE-SEC-055-review (DA-4) benoemde al dat de environment-allowlist een heuristiek is, geen autorisatie; deze iteratie verandert daaraan niets. (De zinsnede "de admin-token blijft bereikbaar zolang HIGH-1 openstaat" is met `32343cc54` komen te vervallen: zonder rol krijg je nu een bezoeker; expliciet `role: "admin"` blijft bewust mogelijk binnen de allowlist.)

Punt 1 is de structurele follow-up (guard op het patroon); punt 2 was de directe les van ronde 1 en is met `32343cc54` gerepareerd en bewezen. Punten 3-6 blokkeren de merge niet maar horen in een benoemde follow-up-brief.
