# Backend Feature Specification

## Metadata

- Feature ID: BE-QA-architectuur-groen
- Feature naam: Architecture-suite groen (markt-blokker 6: handhaving architectuurgrenzen)
- Status: gebouwd, gericht getest; eindmeting in dezelfde commit gedocumenteerd
- Auteur: iteratie-agent E2 (iter/wk1-architectuur-groen)
- Reviewer: n.v.t. (QA-herstel, geen nieuwe feature; regressiebewaking via de guards zelf)
- Datum: 2026-09-24
- Gerelateerde user story / ticket: BE-QA (week 1, architecture-suite rood: 39 failed / 911 passed in QA-meting)
- Gerelateerde router / module: src/core/api/v1/foundation/*, src/core/shared/public_registry.py, src/alembic/versions/20260909_adr029_edu_alignment.py
- Gerelateerde frontend endpoints: foundationClient.getSettings (verwacht 404 bij ontbrekende settings)
- Gerelateerde database tabellen: educational_access, study_collections (alleen migratie-internals)
- Versie: 1.0

---

## Doel en scope

### Doel

De `tests/architecture/`-suite was rood. Deze taak maakt hem groen met echte fixes waar
dat moet (ADR-033-grensschendingen, white-label branding-lek, substring-matcher,
migratie-guard) en met gedocumenteerde, gemeten herkalibraties waar de werkelijkheid
terecht is gegroeid (fan-out budget, publieke API-oppervlakte).

### In scope

- 4 ADR-033 boundary-schendingen hersteld via de Laag-2-facade (`*.dependencies`)
- newsletter.py op de project-helper `utc_now()` gezet
- settings.py: hardcoded "Het Levend Monument"-branding verwijderd; 404-contract hersteld
- public_registry.py: foundation-subpadchecks segment-geankerd + nieuwe guard-test
- Migratie 20260909_adr029_edu_alignment: `sa.inspect(op.get_bind())` vervangen door
  information_schema-query
- Compose-guard: dummy-env voor alle `${VAR:?}`-verplichtingen, ook voor de dev-stack
- Fan-out budget core_api: 572 -> 585 (gedocumenteerde herkalibratie, exact gemeten)
- API-surface nulmeting: 161 -> 186 (gedocumenteerd, per nieuw endpoint geverifieerd)

### Out of scope

- Dichtzetten van verdachte publieke endpoints (geen gevonden; zie escalaties)
- Bestaande upsert-defaults in settings.py PUT ("Levend Monument" als fallback-naam) --
  alleen zichtbaar voor de eigen tenant, geen drift met de test; apart te overwegen
- Reductie van core_api fan-out onder de gemeten waarde (refactor, eigen taak)

---

## Build summary

- Nieuw gebouwd: twee guard-tests in tests/architecture/test_public_registry_prefixes_are_anchored.py
  (test_foundation_subpaths_are_segment_anchored, test_foundation_public_subpaths_stay_public)
- Gewijzigd: 7 src-bestanden, 4 testbestanden (zie Backend inventory)
- Verwijderd: niets
- Beinvloede bestaande flows: publieke foundation-portal middleware-classificatie
  (is_public), offline SQL-generatie van migratie 20260909_adr029_edu_alignment,
  publieke settings-response bij ontbrekende settings-rij (nu 404 i.p.v. HLM-defaults)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-DEP-facade | Foundation facade uitgebreid | Dependency | src/core/api/v1/foundation/dependencies.py | Wijziging | ADR-033 Laag 2 |
| BE-RTR-upload | upload.py via facade | Router | src/core/api/v1/foundation/upload.py | Wijziging | media upload/stream |
| BE-RTR-newsletter | newsletter.py via facade + utc_now | Router | src/core/api/v1/foundation/newsletter.py | Wijziging | double opt-in |
| BE-RTR-curatie | admin/curatie.py via facade | Router | src/core/api/v1/foundation/admin/curatie.py | Wijziging | curatie |
| BE-EP-settings | get_settings 404-contract | Endpoint | src/core/api/v1/foundation/settings.py | Wijziging | white-label branding |
| BE-MID-registry | is_public segment-ankering | Middleware-registry | src/core/shared/public_registry.py | Wijziging | TenantMiddleware/SecurityMiddleware |
| BE-MIG-edu | _kolommen zonder sa.inspect | Migratie | src/alembic/versions/20260909_adr029_edu_alignment.py | Wijziging | alembic upgrade --sql |
| BE-QA-fanout | fan-out budget 572 -> 585 | Guard | tests/architecture/test_dsm_grade_a_plus.py | Wijziging | DSM-gate |
| BE-QA-surface | nulmeting 161 -> 186 | Guard | tests/architecture/test_the_api_surface_is_a_measurement.py | Wijziging | OP-62-gate |
| BE-QA-compose | dummy-env dev+prod | Guard | tests/architecture/test_portal_compose_traefik_routing.py | Wijziging | compose-validatie |
| BE-QA-anchor | substring-guard tests | Guard | tests/architecture/test_public_registry_prefixes_are_anchored.py | Nieuw | registry-bewaking |

---

## Detaildocumentatie per artefact

## [BE-RTR-*] ADR-033 facade-herstel (4 schendingen)

### 4. Doel

De ADR-033 router-laag mag database/governance/services niet direct importeren; dat loopt
via de domein-facade `dependencies.py` (Laag 2). Vier directe imports waren teruggekeerd
en maakten test_dsm002_dag6_zero_violations en test_dsm_api_violations rood.

### 6. Technische beschrijving

- dependencies.py: `_MIME_TO_EXT` en `secure_filename` toegevoegd aan de bestaande
  foundation_storage re-export (en `__all__`); AuditService en brevo_email_service werden
  al ge-exporteerd.
- newsletter.py: `from src.core.governance.services.audit_service import AuditService`
  vervangen door import via `.dependencies`.
- admin/curatie.py: directe imports van audit_service en brevo_email_service vervangen
  door de facade.
- upload.py: `from src.core.services.foundation_storage import _MIME_TO_EXT,
  secure_filename` vervangen door de facade.

Gemeten effect: core_api fan-out daalde 588 -> 585 (facade-consolidatie minus de
nieuwe, voorgeschreven utc_now-import in newsletter.py); beide DSM-violation-guards groen.

## [BE-RTR-newsletter] utc_now()

### 6. Technische beschrijving

Regels 183 en 315 gebruikten `datetime.now(timezone.utc)` -- al timezone-aware (geen
NOOIT-lijst-schending), maar inconsistent met de project-helper. Nu `utc_now()` uit
src.core.shared.datetime_utils, zoals curatie.py en upload.py al deden. Gedrag identiek.

## [BE-EP-settings] 404-contract hersteld

### 4. Doel

White-label: een tenant zonder settings-rij mag NOOIT de branding van een andere tenant
("Het Levend Monument") terugkrijgen. Commit e395118f5 had de oorspronkelijke 404
(commit 2b3591d56) vervangen door hardcoded HLM-defaults; dat brak
tests/unit/test_foundation_settings.py::test_get_settings_not_found en lekte branding.

### 11. Business rules

- GET /{tenantSlug}/foundation/settings zonder settings-rij -> 404 "Portal settings
  not found". De frontend-contracttest (foundationClient.test.ts:155) verwacht die 404.
- PUT upsert-defaults ("Levend Monument"-naamfallback) zijn ongemoeid gelaten: alleen
  zichtbaar voor de eigen tenant en niet onder de failing test. Zie Open aannames.

## [BE-MID-registry] Segment-geankerde foundation-subpaden

### 4. Doel

OP-202 ankerte de routevorm en PUBLIC_PREFIXES, maar de sub-padchecks in het
foundation-blok bleven substrings: `"/foundation/edu/session" in path`. Daardoor waren
`/{slug}/foundation/edu/sessions` (meervoud) en `/{slug}/foundation/edu/contentevil`
(verzonnen) ten onrechte publiek -- gemeten, niet verondersteld: de nieuwe guard-test was
ROOD op de ongewijzigde code voor alle vier de probes.

### 6. Technische beschrijving

is_public() splitst het pad nu na het "foundation"-segment en toetst elk publiek subpad
via `_matches_prefix` (exact of `/`-grens). De admin-uitsluiting is segment-geankerd
(`"admin" in segments`) met hetzelfde bereik als de oude `"/admin/" in path`-toets --
die pariteitsregressie (slug "admin") is gevangen door
tests/unit/test_public_endpoint_registry.py::test_admin_is_not_public en hersteld.
BE-SEC-057-versmalling (edu/codes NIET publiek) blijft intact.

### 17. Acceptatiecriteria

- /acme/foundation/edu/sessions en /acme/foundation/edu/contentevil NIET publiek (beide
  routevormen) -- guard-test groen na fix, rood ervoor (mutatiebewijs in test-docstring).
- /acme/foundation/edu/session, /edu/content, /edu/content/12 en /settings blijven
  publiek (tegenrichting bewezen).
- Alle bestaande registry/middleware/foundation unit-tests groen (63 + 77 gericht).

## [BE-MIG-edu] information_schema i.p.v. sa.inspect

### 6. Technische beschrijving

_kolommen() gebruikte `sa.inspect(op.get_bind())` -- crasht op een offline dry-run en is
verboden (backend-patterns.md #9, guard test_no_sa_inspect_in_migrations). Nu een ruwe
information_schema.columns-query, hetzelfde catalogus-patroon als _constraint_bestaat /
_index_bestaat in hetzelfde bestand. Aanroepen blijven online-only (bestaande
_is_offline()-bakening ongewijzigd); tests/unit/test_be_mig_013_offline_sql.py groen.

## [BE-QA-compose] Dummy-env voor alle verplichte variabelen

### 6. Technische beschrijving

docker-compose.yml verplicht sinds 38c16e98f env vars via `${VAR:?}`. De guard gaf die
alleen mee aan de prod-run; de dev-run faalde. Nu een gedeelde dummy_env met alle 15
verplichte variabelen (gemeten via grep op `:?` in alle drie de compose-files).

## [BE-QA-fanout] en [BE-QA-surface] Gedocumenteerde herkalibraties

Beide guards pinnen een exact gemeten waarde met de conventie "verlagen mag altijd,
verhogen vraagt een gedateerde, gemeten toelichting". Die zit in de testbestanden zelf
(in-line comments met diff-meting tegen de pin-commits 5b8a3503c resp. 7a0fe78c6, dezelfde
scanner op beide kanten). Kern:

- Fan-out 572 -> 585: +9 shared.time (negen portalbestanden gebruiken de VOORGESCHREVEN
  utc_now-helper; de negende is newsletter.py uit deze sessie), +2 integrations (connectors.brevo helpers), +4 infra / +2 auth
  (portal + BE-LLM-003 facades), -4 agent_runtime (facade-consolidatie). Geen nieuwe
  ADR-033-schending in de delta.
- API-surface 161 -> 186: -2 edu/codes (BE-SEC-057, gewenste krimp), +17 dual-mount van
  al-geaccepteerde publieke paden onder /api/v1/{tenantSlug}/..., +10 nieuw en stuk voor
  stuk geverifieerd in de router-code (quick-login is production-gated 403; contact en
  donations/checkout hcaptcha; donations/webhook Stripe-signatuur; newsletter confirm/
  unsubscribe token-gehashed; media/stream privacy-gated; robots.txt statisch; settings
  404 zonder rij). Geen per ongeluk publiek endpoint gevonden.

---

## Integratorhandleiding

- GET /{tenantSlug}/foundation/settings geeft 404 als de tenant nog geen branding heeft
  geconfigureerd; een curator maakt die aan via PUT /admin/settings.
- Publieke foundation-paden worden door de middleware op segmentgrenzen herkend; een route
  die alleen op een publieke naam "lijkt" (meervoud, verlengde naam) valt VOORTAAN buiten
  de publieke set en vereist een eigen bewuste registratie.

---

## Open aannames

- De 17 dual-mount paden zijn niet elk afzonderlijk herlezen in de router-code; ze zijn de
 zelfde handlers als de niet-geprefixte vormen uit de 161-nulmeting (gemeten: zelfde
  route-objecten via create_test_app, gedeeld handler-endpoint). Markeer voor review.
- PUT /admin/settings behoudt "Levend Monument" als naamfallback bij upsert zonder naam;
  alleen zichtbaar binnen de eigen tenant, maar strikt genomen nog steeds een HLM-default.

## Open vragen

- Moet quick-login (production-gated) op termijn achter een feature flag i.p.v. alleen
  ENVIRONMENT? Buiten scope; endpoint is fail-closed in productie.

## Risico's

- Fan-out en surface-budgetten staan nu exact op de gemeten waarde zonder marge
  (conventie van deze guards); elke nieuwe publieke route of koppeling maakt de gate rood
  en dwingt opnieuw een bewuste stap af. Dat is het beoogde gedrag.

---

## QA-checks

- [x] Gerichte tests groen per gewijzigd cluster (zie metingen in testbestanden)
- [x] Guard-test mutatiebewijs in beide richtingen (substring-guard: rood voor, groen na)
- [x] Offline-SQL migratietest groen
- [x] Registry unit- en middleware-tests groen (geen pariteitsregressie)
- [x] Settings unit-tests groen (13/13)

## Definition of Done

- [x] Fixes gebouwd en gericht getest
- [x] Nieuwe guard-test met gedocumenteerd mutatiebewijs
- [x] Herkalibraties gedateerd en gemeten gedocumenteerd
- [x] Open aannames benoemd

## Trainingssamenvatting

- **Actor:** Een ontwikkelaar die een nieuwe publieke route toevoegt, een domain-import direct in een router trekt (ADR-033), of een migratie schrijft die `sa.inspect(op.get_bind())` gebruikt.
- **Voorwaarde:** De architectuur-suite (`tests/architecture`) draait blokkerend in de poort; de nulmetingen (API-surface 186, fan-out 585, import-linter contracten) zijn gedateerd en exact gemeten met pin-commit-diffs in de test-comments.
- **Actie:** De ontwikkelaar draait `python -m pytest tests/architecture -n 4 --timeout=60` (lokaal of via CI) na zijn wijziging.
- **Systeemverwerking:** De suite meet de werkelijke API-surface, import-grafiek en fan-out tegen de vastgelegde nulmetingen; de publieke-registry-guard test segment-ankering (`/edu/sessions` en `/edu/contentevil` vallen buiten de publieke set); de compose-guard vereist een dummy-env voor alle `${VAR:?}`-verplichtingen.
- **Succesrespons:** 1017 passed, 0 failed -- elke bewuste nieuwe publieke route is vooraf in de router-code geverifieerd en in de nulmeting gedocumenteerd.
- **Foutrespons:** Een falende guard met een exacte diff (welke paden/imports afwijken); een onbewust publiek endpoint of een nieuwe ADR-033-schending is direct zichtbaar en blokkeert de poort.
