# Frontend Feature Specification

## Metadata

- Feature ID: FE-CI-001
- Feature naam: DepartmentCard nl-NL budget-locale fix + useApiDocumentation waitFor-race fix
- Status: ACTIEF
- Auteur: Claude (SP-CI-001 Dag 2)
- Reviewer: self-review (kleine wijziging, <10 regels productiecode, 1 test-matcher-patroon --
  CLAUDE.md Gate 2-uitzondering)
- Datum: 2026-07-14
- Gerelateerde user story / ticket: SP-CI-001 (CI Pipeline Herstel), Bevinding 4
- Gerelateerde pagina / route: company-dashboard (departments-overzicht)
- Gerelateerde backend endpoints: n.v.t. (client-side formattering + test-synchronisatie)
- Gerelateerde design componenten: `DepartmentCard`
- Versie: 1.0

---

## Doel en scope

### Doel

De CI-Frontend-job faalde consistent op 4 tests: 2 in `DepartmentCard.test.tsx` (budget-bedrag
werd getoond in Amerikaanse notatie i.p.v. de verwachte Nederlandse notatie) en 2 in
`useApiDocumentation.test.ts` (search/tag-lookups retourneerden leeg terwijl niet-lege
resultaten werden verwacht). Beide root-causes zijn empirisch vastgesteld:

1. `DepartmentCard.tsx:66` gebruikte `.toLocaleString()` zonder locale-argument. Dit resolvet
   naar de runtime-default-locale: `nl-NL` op deze Windows-devmachine (vandaar lokaal altijd
   groen), maar `en-US` op de Ubuntu-CI-runner (vandaar altijd rood in CI). Bevestigd met
   `node -e "console.log(new Intl.NumberFormat().resolvedOptions().locale)"` -> `nl-NL` lokaal.
2. `useApiDocumentation.test.ts` gebruikte in **5** `waitFor`-blokken (regels 289-291, 310-312,
   330-332, 357-359, 378-380) de matcher `toBeDefined()` op `result.current.documentation`, die
   als initiele state `null` heeft (niet `undefined`). `null` voldoet al aan `toBeDefined()`, dus
   `waitFor` kan resolven voordat de gemockte async fetch daadwerkelijk is afgerond -- een
   test-race, geen hook-bug (de hook zelf retourneert correct `[]` als `documentation === null`).
   Elders in exact hetzelfde bestand staat het juiste patroon (`not.toBeNull()`) al gevestigd.

   **Correctie (2026-07-14, onafhankelijke review FA-IND-004):** de oorspronkelijke versie van
   deze spec noemde "4 occurrences" en miste de 5e (regels 378-380, in de test "should return
   empty array for non-existent tag"). De code-fix zelf ving alle 5 al correct (via
   `replace_all` op de Edit-tool) -- alleen de documentatie was onvolledig, niet de fix.

### In scope

- `DepartmentCard.tsx`: expliciete `'nl-NL'`-locale toevoegen aan de ene `.toLocaleString()`-aanroep.
- `useApiDocumentation.test.ts`: 5x `toBeDefined()` -> `not.toBeNull()` (consistent met het
  reeds bestaande, correcte patroon in ditzelfde bestand).
- Nieuwe regressie-preventietest: `frontend/src/__tests__/architecture/no-unlocalized-tolocalestring.test.ts`.

### Out of scope

- De overige 68 `.toLocaleString()`-aanroepen zonder locale-argument, verspreid over 44 andere
  bestanden (gevonden tijdens `grep`-onderzoek naar vergelijkbare instanties). Dit overschrijdt
  de dag-2-scope-drempel (>3 bestanden buiten de twee die al aangeraakt worden, zie
  `docs/agent-briefs/generated/2026-07-14-sprint-dag-2-SP-CI-001.md` "Stopvoorwaarden") en wordt
  daarom NIET stilzwijgend meegefixed. In plaats daarvan is een regressie-ceiling-test
  toegevoegd (ceiling=68) die voorkomt dat het aantal verder groeit, zodat dit een zichtbaar,
  getrackt backlog-item is in plaats van een verzwegen gat (analoog aan de bestaande
  `test_dsm_api_violations.py::test_api_layer_violations_regression_ceiling`-patroon in de
  backend). Aanbevolen: eigen i18n-sprint om deze 44 bestanden op te lossen.

  **Correctie (2026-07-14, onafhankelijke review FA-IND-003):** het oorspronkelijk genoemde
  getal (73) kwam uit een foutieve grep-pipeline (`grep -o` verwijdert bestandsnamen voordat het
  test/story-uitsluitingsfilter er nog op kon worden toegepast, waardoor test/story-bestanden
  alsnog meetelden in de instantie-telling terwijl de bestandsteller wel al correct filterde).
  Het werkelijke, met de test-eigen glob/regex-logica gereproduceerde aantal is 68. De test en
  deze spec zijn beide gecorrigeerd naar ceiling=68.

- Dezelfde bug-klasse (runtime-default-locale-afhankelijkheid) komt ook voor bij
  `.toLocaleDateString()`/`.toLocaleTimeString()` zonder locale-argument: 55 instanties in 42
  andere bestanden (gevonden via onafhankelijke review, FA-IND-006). Datumnotatie is minstens
  zo zichtbaar voor eindgebruikers als getalnotatie en even gevoelig voor dezelfde
  CI-vs-lokaal-flakiness. Ook dit is buiten de dag-2-scope gehouden, maar nu WEL zichtbaar
  getrackt: de architectuurtest (`no-unlocalized-tolocalestring.test.ts`) heeft een tweede
  ceiling-check (ceiling=55) toegevoegd voor deze aanroepen.

---

## Build summary

- Gewijzigd: `frontend/src/components/company/DepartmentCard.tsx` (1 regel, `'nl-NL'` toegevoegd).
- Gewijzigd: `frontend/src/lib/hooks/__tests__/useApiDocumentation.test.ts` (5x matcher-fix).
- Nieuw gebouwd: `frontend/src/__tests__/architecture/no-unlocalized-tolocalestring.test.ts`
  (2 regressie-ceiling-checks: `.toLocaleString()` ceiling=68, `.toLocaleDateString()`/
  `.toLocaleTimeString()` ceiling=55).
- Verwijderd: geen.
- Beinvloede bestaande flows: company-dashboard department-overzicht (budgetweergave).
  `useApiDocumentation`-hook zelf ongewijzigd -- alleen de testbestanden zijn gecorrigeerd.

---

## Frontend inventory

| ID        | Naam                          | Type               | Locatie                                              | Nieuw/Wijziging | Gerelateerde flow                      |
| --------- | ----------------------------- | ------------------ | ---------------------------------------------------- | --------------- | -------------------------------------- |
| FE-CI-001 | DepartmentCard budgetweergave | Component (bugfix) | `frontend/src/components/company/DepartmentCard.tsx` | Wijziging       | Company-dashboard department-overzicht |

---

## [FE-CI-001] DepartmentCard budgetweergave

### 1. Type

Bestaand herbruikbaar UI-component (card), bugfix van de i18n-formattering.

### 2. Locatie

`frontend/src/components/company/DepartmentCard.tsx`, regel 66.

### 3. Gerelateerde flow

Company-dashboard: gebruiker bekijkt het department-overzicht van zijn bedrijf.

### 4. Doel

Het maandelijkse token-budget van een department tonen in de juiste, voor dit
Nederlandstalige platform consistente getalnotatie (punt als duizendtal-scheidingsteken).

### 5. Functionele beschrijving

De gebruiker ziet op elke department-kaart de tekst "Budget: X tokens/maand", waarbij X het
maandelijkse tokenbudget is, genoteerd volgens Nederlandse conventie (bv. "40.000" i.p.v.
"40,000").

### 6. Technische beschrijving

`department.budget_monthly_tokens?.toLocaleString('nl-NL') || 0` -- expliciete locale
voorkomt afhankelijkheid van de runtime-default-locale (die per omgeving verschilt: developer-
machine-instellingen vs. CI-runner-instellingen). Geen wijziging aan props, state of dataflow.

### 7. Zichtbaarheidsregels

Onveranderd: budget-regel wordt altijd getoond binnen de card-content; bij ontbrekend budget
toont de component "0 tokens/maand" (bestaand fallback-gedrag via `|| 0`, ongewijzigd).

### 8. States en gedrag

- Default: budget getoond in nl-NL-notatie.
- Empty (`budget_monthly_tokens` ontbreekt): "0 tokens/maand" (ongewijzigd fallback-gedrag).
- Overige states (hover, loading, error): niet van toepassing op dit statische tekstveld.

### 9. Input

`department.budget_monthly_tokens?: number` (via props, ongewijzigd).

### 10. Output

Geformatteerde tekststring in nl-NL-notatie.

### 11. Validaties

Geen (puur presentationeel, geen user-input).

### 12. Business rules

Dit platform is Nederlandstalig (zie CLAUDE.md, `.claude/rules/frontend.md`); alle
getalnotaties horen de Nederlandse conventie te volgen, ongeacht de runtime-omgeving van de
gebruiker of de CI-server.

### 13. Afhankelijkheden

`Intl.NumberFormat`/`Number.prototype.toLocaleString` (browser-native, geen externe library).

### 14. Foutafhandeling

Niet van toepassing -- `toLocaleString('nl-NL')` faalt niet op een geldig `number`-type; de
optional chaining (`?.`) en `|| 0`-fallback dekken het ontbrekende-budget-geval al.

### 15. Telemetry / logging / analytics

Niet van toepassing.

### 16. Accessibility-notities

Geen wijziging in DOM-structuur of ARIA-attributen; alleen de tekstinhoud van een bestaand
`<span>`-element verandert qua notatie, niet qua semantiek.

### 17. Acceptatiecriteria

- Gegeven een department met `budget_monthly_tokens: 40000`, toont de kaart de tekst die
  overeenkomt met `/40\.000 tokens/` (regex-match, ongeacht omringende tekst-nodes).
- Gegeven een department met `budget_monthly_tokens: 25000`, toont de kaart `/25\.000 tokens/`.
- Dit gedrag is identiek op elke runtime-omgeving (developer-machine, CI-runner, productie),
  ongeacht de OS-/systeemlocale.

### 18. Gebruikersuitleg

- Het maandelijkse tokenbudget van een afdeling wordt getoond met een punt als
  duizendtal-scheidingsteken (bv. "40.000"), consistent met de rest van het Nederlandstalige
  platform.

### 19. Trainingssamenvatting

- Actor: gebruiker die het company-dashboard bekijkt.
- Voorwaarde: een department heeft een `budget_monthly_tokens`-waarde.
- Actie: gebruiker navigeert naar het department-overzicht.
- Systeemreactie: `DepartmentCard` rendert het budget met `toLocaleString('nl-NL')`.
- Succesrespons: budget getoond als bv. "Budget: 40.000 tokens/maand".
- Foutrespons: niet van toepassing (geen foutpad voor dit statische veld).
- Uitzonderingen: ontbrekend budget -> "Budget: 0 tokens/maand" (bestaand fallback-gedrag).

---

## Handleidingstekst

### Voor eindgebruikers

Zie `docs/user-guide/frontend/department-card-locale-api-doc-test-race.md`.

**Correctie (2026-07-14):** de eerdere versie van deze sectie stelde dat geen user guide nodig
was omdat de wijziging "geen nieuwe flow of interactie" betreft. Dat was een onjuiste
interpretatie van de workflow-eis -- `docs/copilot-phase-2-frontend-visual-redesign/
FEATURE_DOC_WORKFLOW.md` Stap 4 en `scripts/validate_feature_docs.py` vereisen een user guide
voor ELK FE-ID zonder uitzonderingsclausule, ongeacht de omvang van de gedragswijziging. De
guide is alsnog aangemaakt.

---

## Open aannames

- Geen voor de twee gefixte bestanden.
- Voor de 68 + 55 out-of-scope instanties: aangenomen dat een aparte i18n-sprint de juiste plek
  is om ze op te lossen (zie "Out of scope" hierboven) -- Rakesh kan dit bevestigen of anders
  beslissen.

## Open vragen

- Wil Rakesh een aparte sprint plannen voor de resterende 68 unlocalized `.toLocaleString()`-
  en 55 unlocalized `.toLocaleDateString()`/`.toLocaleTimeString()`-aanroepen, of blijven de
  regressie-ceiling-tests voorlopig voldoende?

## Risico's

- Laag: de wijzigingen zijn minimaal en geisoleerd (1 productieregel, 4 identieke
  test-matcher-vervangingen, 1 nieuwe zelfstandige preventietest).

---

## QA-checks

- [x] Functioneel getest (`npx vitest run` op beide bestanden, 35/35 groen)
- [x] UI states getest (default + empty/fallback-pad, bestaande tests dekken dit)
- [x] Error states getest: n.v.t. (geen foutpad)
- [x] Accessibility gecontroleerd: geen DOM/ARIA-wijziging
- [x] Responsive gecontroleerd: n.v.t. (tekstformattering, geen layoutwijziging)
- [x] Cross-browser gecontroleerd: `toLocaleString('nl-NL')` is universeel ondersteund
      (ECMA-402), geen browser-specifiek risico
- [x] Analytics/logging gecontroleerd: n.v.t.

---

## Definition of Done

- [x] Feature is gebouwd (2 fixes + 1 preventietest)
- [x] Alle interactieve elementen zijn geinventariseerd (1 statisch tekstveld, geen nieuwe
      interactieve elementen)
- [x] Alle relevante states zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar (regex-matches, reeds bestaande tests)
- [x] Gebruikersuitleg is aanwezig: `docs/user-guide/frontend/department-card-locale-api-doc-test-race.md`
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: `docs/frontend/review/review-FE-CI-001.md` -- APPROVED
- [x] `python scripts/validate_feature_docs.py` -- exit 0 (510/510 IDs compleet)
