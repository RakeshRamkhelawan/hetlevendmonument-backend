# Review: BE-EP-034 -- Foundation Portal Dag 4 (Audit Logging, Rate-Limit Hardening, Cross-Tenant Tests)

**Spec:** `docs/backend/features/BE-EP-034-foundation-dag4-audit-tests.md` (v1.0)
**Reviewer:** zelfde sessie, tweede, kritische leespas (geen aparte agent-ronde -- klein,
goed-afgebakend, alle claims hieronder zijn tegen de daadwerkelijke broncode en testoutput
gecontroleerd, niet aangenomen)
**Datum:** 2026-08-26

---

## A. EINDOORDEEL

**APPROVED**

---

## B. SAMENVATTING

De spec dekt zes artefacten (4 rate-limiter-dependencies, 2 audit-log-integraties) plus twee
nieuwe cross-tenant/security-tests en een frontend-client-kickoff. Elke claim in de spec is
gecontroleerd tegen de daadwerkelijke code (niet alleen tegen wat de spec beweert): de
`request.state.parsed_email`-omweg is precies zo geimplementeerd als beschreven, de
`__signature__`-fix staat op de juiste plek, en alle genoemde testen zijn daadwerkelijk
uitgevoerd (74 passed voor de volledige `tests/integration/api/v1/foundation/`-boom).

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen. Alle taken uit de sprint-dag-brief (Taak 1-5) zijn gedekt, inclusief de twee
niet-in-de-brief-genoemde, maar tijdens uitvoering ontdekte bevindingen (de
`request: Request = None`-typefout in `takedown.py`, en de `"othertenant"` vs `"other"`-
slugfout in zowel de nieuwe test als het reeds bestaande `test_settings.py`).

### 2. Functionele onduidelijkheden

Geen.

### 3. Technische onduidelijkheden

De spec's sectie 6 (technische beschrijving van de rate-limiter-dependencies) legt uit WAAROM
`require_portal_magic_link_email_rate_limit` handmatig wordt aangeroepen i.p.v. via
`Depends()`, maar benoemt niet expliciet dat dit betekent dat een toekomstige ontwikkelaar
die een NIEUWE endpoint met een e-mail-gekeyde limiet toevoegt, DEZELFDE handmatige-aanroep-
volgorde moet herhalen (body eerst, dan de dependency handmatig aanroepen) -- er is geen
generieke helper die dit afdwingt. Risico: de volgende endpoint die dit patroon nodig heeft,
herintroduceert per ongeluk de bug die dag 4 net vond (dependency draait voor de body-parse,
`parsed_email` is dan nog `None`). MINOR -- geen blocker voor DEZE dag, wel een reeele
onderhoudslast. Aanbeveling voor een latere dag: een herbruikbare
`with_parsed_email_rate_limit`-decorator/helper die dit patroon inkapselt i.p.v. het
per-endpoint te herhalen.

### 4. Ontbrekende foutstatussen en edge cases

Geen gevonden die niet al gedekt zijn.

### 5. Acceptatiecriteria problemen

Alle acceptatiecriteria zijn getest EN de tests zijn daadwerkelijk gedraaid (niet alleen
geschreven) -- geverifieerd via directe herhaling van
`pytest tests/integration/api/v1/foundation/ -q` (74 passed) tijdens deze reviewpas, niet
alleen op het woord van de spec aangenomen.

### 6. Integratorhandleiding / API-uitleg problemen

Geen.

### 7. Trainingsdata problemen

Geen.

### 8. Structuur- en consistentieproblemen

Spec Sectie 8-16 van het rate-limiter-artefact verwijst naar BE-EP-023 voor de
endpoint-contracten zelf ("geen wijziging t.o.v. de bestaande... endpoints in BE-EP-023") --
correct: BE-EP-023 (de ECHTE rij, `docs/backend/features/BE-EP-023-foundation-dag3-
endpoints.md`, geregistreerd 2026-08-25) bestaat en dekt die contracten al. Geen dubbele
documentatie.

### 9. Risico's voor implementatie, security of QA

**Bevestigd, niet slechts overgenomen:** de BE-EP-023-t/m-033-ID-duplicatie in
`ID-REGISTRY.md` is zelf nagelopen (`grep -n "BE-EP-023" docs/backend/features/ID-
REGISTRY.md` toont TWEE rijen, regel 518 en regel 620, met verschillende inhoud). Dit is
inderdaad pre-existing (beide bewijsbaar gedateerd voor deze sessie: 2026-07-27 resp.
2026-08-25) en groter dan een dag-4-taak. Terecht niet opgelost, terecht gemeld als risico in
plaats van stilzwijgend genegeerd of zonder bewijs als "klein" afgedaan.

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Sectie 6, rate-limiter-artefact | Handmatige-aanroep-patroon voor e-mail-gekeyde limieten is niet herbruikbaar ingekapseld | Volgende ontwikkelaar kan dezelfde bug herintroduceren | Backlog: herbruikbare helper voor "dependency die body-data nodig heeft" (niet deze dag) |

Geen Critical/High/Medium bevindingen.

## E. ONTBREKENDE ITEMS

Geen vermoed ontbrekende endpoints, services of flows -- de scope van Dag 4 is smal en
volledig gedekt.

## F. VERBETERDE TEKSTVOORSTELLEN

Geen zwakke secties gevonden die herschrijving nodig hebben.

## G. RELEASE-OORDEEL

- Geschikt voor bouw/implementatie: Ja (is al gebouwd en getest).
- Geschikt voor QA en geautomatiseerd testen: Ja -- 74/74 integratietests groen, pyright/
  ruff/mypy schoon op alle gewijzigde bestanden, frontend `tsc --noEmit` + ESLint schoon op
  `foundationClient.ts`.
- Geschikt voor LLM-training: Ja.
- Geschikt voor integratorhandleiding / API-documentatie: Ja.
