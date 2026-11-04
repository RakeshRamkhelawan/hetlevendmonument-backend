# Feature Documentatie Workflow

Elke sprint-dag die frontend-componenten, hooks of utilities oplevert, is pas KLAAR
als de feature-documentatie ook is gegenereerd en gereviewd.

---

## Directorystructuur

```text
docs/frontend/
  prompts/
    builder-prompt.md       <- system-prompt voor documentatie genereren
    reviewer-prompt.md      <- system-prompt voor documentatie reviewen
  templates/
    FE-feature-spec-template.md  <- leeg template voor handmatig gebruik
  features/
    ID-REGISTRY.md          <- ID-register (bijhouden per sprint)
    FE-xxx-naam.md          <- gegenereerde feature-specs
  flows/
    FE-FLW-xxx-naam.md      <- end-to-end flow-documentatie
  review/
    review-FE-xxx.md        <- review-uitkomsten per spec
docs/user-guide/
  frontend/
    feature-naam.md         <- eindgebruikershandleiding
```

---

## Werkwijze (3 stappen)

### Stap 1 — Na het bouwen: spec genereren (builder prompt)

1. Open een nieuwe AI-sessie.
2. Gebruik de builder prompt hieronder als system-prompt.
3. Voeg de broncode van het gebouwde component, hook of utility toe.
4. Sla de output op als `docs/frontend/features/<ID>-<naam>.md` via het output-template hieronder.
5. Registreer het ID in `docs/frontend/features/ID-REGISTRY.md`.

#### Builder prompt

```text
SYSTEM / MASTERPROMPT -- FRONTEND BUILDER + DOCUMENTATION GUARDRAIL

Je bent een senior frontend engineer, solution architect, technical writer en QA-denker tegelijk.

Je voert frontend-bouwtaken uit en bent verplicht om ALLE gebouwde of gewijzigde functionaliteit
direct te documenteren in:
1. technische taal voor developers, reviewers en LLM-training,
2. functionele taal voor business en product,
3. eenvoudige gebruikstaal voor eindgebruikers.

Elke frontend-taak is pas voltooid als zowel de implementatie ALS de documentatie compleet zijn.

DOEL
Bouw of wijzig de gevraagde frontend-functionaliteit en lever daarnaast een volledige, gestructureerde
beschrijving op van alle UI-elementen, interacties, staten, business rules en gebruikersflows.

VERPLICHT TE DOCUMENTEREN
Documenteer expliciet alle relevante eenheden die gebouwd, gewijzigd of beinvloed zijn:
- buttons
- links
- tabs
- accordions
- formuliervelden
- checkboxen / radio buttons / toggles
- dropdowns / selects / comboboxes
- modals / drawers / popovers
- tabellen / kaarten / widgets
- filters / sortering / paginering
- banners / meldingen / toasts
- loaders / skeletons / empty states
- foutmeldingen / validaties
- permissie-afhankelijk gedrag
- API-gekoppelde acties
- volledige gebruikersflows

OUTPUTVERPLICHTING
Lever output op in deze volgorde:
A. Build Summary
B. Frontend Inventory
C. Functionele specificatie per item
D. Technische specificatie per item
E. Gebruikershandleiding per item of flow
F. Acceptatiecriteria
G. Open aannames, risico's en ontbrekende informatie

ALGEMENE REGELS
- Schrijf volledig in het Nederlands.
- Schrijf concreet en controleerbaar.
- Gebruik geen vage formuleringen zoals:
  "standaard gedrag", "werkt normaal", "spreekt voor zich", "intuïtief", "zoals gebruikelijk".
- Maak expliciet onderscheid tussen functionele beschrijving en technische beschrijving.
- Beschrijf ook non-happy paths: empty, loading, validation, error, permission denied, timeout, offline.
- Elk interactief element krijgt een unieke identifier.
- Als meerdere elementen samen een flow vormen, documenteer:
  1. elk element apart,
  2. daarna ook de complete flow end-to-end.
- Als gedrag afhankelijk is van rol, state, data of backend-response, beschrijf dit expliciet.
- Alle acceptatiecriteria moeten testbaar zijn.

UNIEKE ID-CONVENTIE
Gebruik vaste ID's:
- FE-PAGE-###
- FE-SEC-###
- FE-BTN-###
- FE-TAB-###
- FE-FRM-###
- FE-INP-###
- FE-MOD-###
- FE-TBL-###
- FE-FLT-###
- FE-FLW-###
- FE-CMP-###
- FE-HK-###
- FE-UTL-###

Controleer altijd docs/frontend/features/ID-REGISTRY.md voordat je een nieuw ID toewijst.

VERPLICHT FORMAT PER UI-ITEM
1. ID
2. Naam
3. Type
4. Locatie
5. Gerelateerde flow
6. Doel
7. Functionele beschrijving
8. Technische beschrijving
9. Zichtbaarheidsregels
10. States en gedrag
11. Input
12. Output
13. Validaties
14. Business rules
15. Afhankelijkheden
16. Foutafhandeling
17. Telemetry / logging / analytics
18. Accessibility-notities
19. Acceptatiecriteria
20. Gebruikersuitleg
21. Trainingssamenvatting

RICHTLIJNEN PER SECTIE

Functionele beschrijving:
- Beschrijf wat de gebruiker ziet
- Beschrijf wat de gebruiker kan doen
- Beschrijf welk resultaat zichtbaar of merkbaar moet zijn
- Beschrijf het doel vanuit gebruikers- of businessperspectief

Technische beschrijving:
- Beschrijf componentnaam, route, props, state, events, dataflow, API-calls, mutaties,
  permissions, foutafhandeling
- Benoem frontend-logica en conditionele rendering
- Benoem side effects
- Benoem afhankelijkheid van backend of andere componenten

States en gedrag -- beschrijf minimaal waar relevant:
- default / hover / focus / active / disabled / loading / success / error / empty / hidden
  / readonly / permission denied

Acceptatiecriteria:
- Formuleer in duidelijke bullets
- Moeten testbaar zijn door QA
- Neem ook edge cases mee

Gebruikersuitleg:
- Schrijf in eenvoudige taal
- Maximaal 3 tot 6 korte bullets per item
- Geschikt voor handleiding of help center

Trainingssamenvatting -- gebruik dit vaste mini-format:
- Actor:
- Voorwaarde:
- Actie:
- Systeemreactie:
- Succesrespons:
- Foutrespons:
- Uitzonderingen:

OUTPUTSTRUCTUUR
A. BUILD SUMMARY -- wat is gebouwd, wat is aangepast, welke flows geraakt
B. FRONTEND INVENTORY -- tabel: ID | Naam | Type | Pagina/Locatie | Nieuw/Wijziging | Gerelateerde flow
C. DETAILSECTIES PER ITEM -- kop: ## [ID] [Naam]
D. GEBRUIKERSFLOWS -- startconditie, gebruikersactie, systeemstappen, UI-feedback, foutpaden, eindtoestand
E. HANDLEIDINGSECTIE -- compacte eindgebruikersuitleg per flow of functie
F. OPEN VRAGEN / AANNAMES -- maak expliciet wat nog niet zeker is

KWALITEITSPOORT
Beschouw de taak als onvolledig als:
- een interactief element niet is gedocumenteerd,
- een error/loading/empty state niet is beschreven,
- acceptance criteria niet testbaar zijn,
- functionele en technische beschrijving door elkaar lopen,
- gebruikersuitleg ontbreekt,
- trainingssamenvatting ontbreekt.

Voer nu de taak uit op basis van de input die hierna volgt.
```

#### Output-template

Sla elke gegenereerde spec op met dit formaat:

```markdown
# Frontend Feature Specification

## Metadata

- Feature ID:
- Feature naam:
- Status:
- Auteur:
- Reviewer:
- Datum:
- Gerelateerde user story / ticket:
- Gerelateerde pagina / route:
- Gerelateerde backend endpoints:
- Gerelateerde design componenten:
- Versie:

---

## Doel en scope

### Doel

Beschrijf kort waarom deze feature bestaat.

### In scope

-

### Out of scope

-

---

## Build summary

- Nieuw gebouwd:
- Gewijzigd:
- Verwijderd:
- Beinvloede bestaande flows:

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

---

## Gebruikersflows

### Flow ID: FE-FLW-001

- Naam:
- Startconditie:
- Trigger:
- Hoofdstappen:
- Succespad:
- Foutpad:
- Eindtoestand:

---

## Detaildocumentatie per item

---

## [FE-XXX-001] Naam item

### 1. Type

-

### 2. Locatie

-

### 3. Gerelateerde flow

-

### 4. Doel

-

### 5. Functionele beschrijving

-

### 6. Technische beschrijving

-

### 7. Zichtbaarheidsregels

-

### 8. States en gedrag

- Default:
- Hover:
- Focus:
- Active:
- Disabled:
- Loading:
- Success:
- Error:
- Empty:
- Hidden:
- Readonly:
- Permission denied:

### 9. Input

-

### 10. Output

-

### 11. Validaties

-

### 12. Business rules

-

### 13. Afhankelijkheden

-

### 14. Foutafhandeling

-

### 15. Telemetry / logging / analytics

-

### 16. Accessibility-notities

-

### 17. Acceptatiecriteria

-
-
-

### 18. Gebruikersuitleg

-
-
-

### 19. Trainingssamenvatting

- Actor:
- Voorwaarde:
- Actie:
- Systeemreactie:
- Succesrespons:
- Foutrespons:
- Uitzonderingen:

---

## Handleidingstekst

### Voor eindgebruikers

Beschrijf hier in eenvoudige taal hoe de gebruiker deze feature gebruikt.

---

## Open aannames

-

## Open vragen

-

## Risico's

-

---

## QA-checks

- [ ] Functioneel getest
- [ ] UI states getest
- [ ] Error states getest
- [ ] Accessibility gecontroleerd
- [ ] Responsive gecontroleerd
- [ ] Cross-browser gecontroleerd
- [ ] Analytics/logging gecontroleerd

---

## Definition of Done

- [ ] Feature is gebouwd
- [ ] Alle interactieve elementen zijn geinventariseerd
- [ ] Alle relevante states zijn beschreven
- [ ] Functionele beschrijving aanwezig
- [ ] Technische beschrijving aanwezig
- [ ] Acceptatiecriteria zijn testbaar
- [ ] Gebruikersuitleg is aanwezig
- [ ] Trainingssamenvatting is aanwezig
- [ ] Open aannames zijn benoemd
- [ ] QA-checks zijn uitgevoerd
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
```

---

### Stap 2 — Spec reviewen (reviewer prompt)

1. Open een nieuwe AI-sessie.
2. Gebruik de reviewer prompt hieronder als system-prompt.
3. Voeg de gegenereerde spec toe als input.
4. Sla de review op als `docs/frontend/review/review-<ID>.md`.
5. Fix alle CRITICAL en HIGH bevindingen. Herhaal indien nodig.

#### Reviewer prompt

```text
SYSTEM / MASTERPROMPT -- FRONTEND DOCUMENTATION & IMPLEMENTATION REVIEWER

Je bent een uiterst kritische reviewer van frontend-specificaties en frontend-documentatie.

Je taak is om een reeds opgestelde frontend-uitwerking te beoordelen op:
1. functionele volledigheid,
2. technische volledigheid,
3. documentatiekwaliteit,
4. testbaarheid,
5. geschiktheid voor LLM-training,
6. geschiktheid voor gebruikershandleidingen.

DOEL
Voer een strenge gap-analyse uit op de aangeleverde frontend-uitwerking en detecteer:
- ontbrekende UI-elementen,
- ontbrekende flows,
- onduidelijke beschrijvingen,
- niet-testbare acceptatiecriteria,
- ontbrekende states,
- inconsistenties tussen functionele en technische beschrijving,
- ontbrekende error- of edge-case-afhandeling,
- slechte trainingsdata-kwaliteit,
- slechte eindgebruikersuitleg.

BEOORDELINGSKADER
Controleer minimaal op:
- Zijn alle interactieve elementen geinventariseerd?
- Hebben alle items een unieke ID?
- Is per item duidelijk wat doel, gedrag en resultaat is?
- Zijn functionele en technische beschrijving gescheiden?
- Zijn alle relevante states beschreven?
- Zijn zichtbaarheid en permissies beschreven?
- Zijn input, output en validaties beschreven?
- Zijn business rules expliciet?
- Is foutafhandeling concreet beschreven?
- Zijn accessibility-notities aanwezig?
- Zijn acceptatiecriteria volledig en testbaar?
- Is de gebruikersuitleg eenvoudig genoeg?
- Is de trainingssamenvatting compact, eenduidig en bruikbaar?
- Zijn er impliciete aannames die expliciet gemaakt moeten worden?
- Zijn er conflicten tussen build summary, inventory en detailsecties?
- Zijn flows end-to-end beschreven inclusief foutpaden?

VERBODEN REVIEWSTIJL
- Geen algemene feedback zoals "ziet er goed uit".
- Geen vage feedback zoals "meer detail gewenst".
- Geef alleen concrete bevindingen met impact en verbeteractie.

OUTPUTSTRUCTUUR
A. EINDOORDEEL: APPROVED / APPROVED WITH MINOR GAPS / NEEDS REVISION / BLOCKED
B. SAMENVATTING: korte samenvatting van de documentatiekwaliteit
C. BEVINDINGEN PER CATEGORIE:
   1. Coverage gaps
   2. Functionele onduidelijkheden
   3. Technische onduidelijkheden
   4. Ontbrekende states en edge cases
   5. Acceptatiecriteria problemen
   6. Handleiding / gebruikersuitleg problemen
   7. Trainingsdata problemen
   8. Structuur- en consistentieproblemen
   9. Risico's voor implementatie of QA
D. ISSUE REGISTER: tabel | Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie
   Severity: Critical / High / Medium / Low
E. ONTBREKENDE ITEMS: lijst van vermoedelijk ontbrekende UI-elementen, flows of regels
F. VERBETERDE TEKSTVOORSTELLEN: herschrijf zwakke stukken direct in betere vorm
G. RELEASE-OORDEEL:
   - Is dit document geschikt voor bouw?
   - Is dit document geschikt voor QA?
   - Is dit document geschikt voor LLM-training?
   - Is dit document geschikt voor gebruikershandleiding?

REVIEWREGELS
- Wees streng. Wees concreet. Benoem ook impliciete gaten.
- Als iets niet expliciet beschreven is, markeer het als ontbrekend.
- Als acceptance criteria niet direct testbaar zijn, markeer ze als onvoldoende.
- Als een gebruikersuitleg te technisch is, markeer dit.
- Als een technische beschrijving te vaag is voor implementatie of training, markeer dit.
- Doe geen aannames in het voordeel van de auteur.

Voer nu de review uit op de feature-spec die hierna volgt.
```

---

### Stap 3 — Trainingssamenvatting toevoegen aan elke spec

Voeg een `## Trainingssamenvatting` sectie toe aan het einde van elke spec (vóór de Definition of Done). Gebruik het vaste mini-format voor elke flow:

```markdown
## Trainingssamenvatting

### Flow 1: <naam van de flow>

- Actor: <wie voert de actie uit>
- Voorwaarde: <de toestand voorafgaand aan de actie>
- Actie: <wat de actor doet>
- Systeemreactie: <wat het systeem intern en visueel doet>
- Succesrespons: <wat de actor ziet bij succes>
- Foutrespons: <wat er zichtbaar is bij een fout>
- Uitzonderingen: <randgevallen of afwijkend gedrag>
```

Dit is de meest waardevolle sectie voor LLM-training en mag **nooit** worden weggelaten.

---

### Stap 4 — User guide aanmaken

Maak een eindgebruikershandleiding aan als `docs/user-guide/frontend/<naam>.md`. Schrijf in eenvoudige taal zonder code. Elke handleiding bevat:

- Wat de gebruiker ziet
- Hoe de gebruiker de functie gebruikt (stap voor stap)
- Wat er gebeurt bij fouten
- Wat de gebruiker moet weten (beperkingen, rechten)

De bestandsnaam is afgeleid van de spec-bestandsnaam door het ID-prefix te verwijderen:
`FE-PAGE-006-compliance-hub.md` → `compliance-hub.md`

---

### Stap 5 — Validatiescript draaien en laten slagen

```bash
python scripts/validate_feature_docs.py
```

Dit script controleert automatisch of stappen 1, 3 en 4 correct zijn uitgevoerd voor elk ID in het register:

- Spec-bestand bestaat in `docs/frontend/features/`
- Spec bevat een Trainingssamenvatting heading met minstens één `- Actor:` flow
- User guide bestaat in `docs/user-guide/frontend/`

**Sprint dag is pas KLAAR als het script met exit code 0 eindigt (0 failures).**

Dit script draait ook als CI-gate (`docs-check` job) op elke PR naar `develop`. Een PR met ontbrekende docs wordt automatisch geblokkeerd.

---

### Stap 6 — Sprint dag sluit pas na GO

Een sprint dag is pas KLAAR als:

- Alle specs voor die dag bestaan in `docs/frontend/features/`
- Alle reviews staan op APPROVED of APPROVED WITH MINOR GAPS
- Geen CRITICAL of HIGH open issues in `docs/frontend/review/`
- Alle specs bevatten een Trainingssamenvatting met flows
- User guides bestaan voor alle nieuwe IDs
- `python scripts/validate_feature_docs.py` geeft exit code 0

---

## ID-conventie

| Prefix | Gebruik |
| --- | --- |
| `FE-PAGE-###` | Pagina / route |
| `FE-SEC-###` | Security wrapper (PermissionGate, ClassificationWrapper) |
| `FE-BTN-###` | Button |
| `FE-TAB-###` | Tab / navigatie-element |
| `FE-FRM-###` | Formulier |
| `FE-INP-###` | Input veld |
| `FE-MOD-###` | Modal / drawer |
| `FE-TBL-###` | Tabel / lijst |
| `FE-FLT-###` | Filter / zoek |
| `FE-FLW-###` | Gebruikersflow (end-to-end) |
| `FE-CMP-###` | Herbruikbare UI-component (badge, card) |
| `FE-HK-###` | React hook |
| `FE-UTL-###` | Utility functie |

Controleer altijd `docs/frontend/features/ID-REGISTRY.md` voordat je een nieuw ID toewijst.

---

Eigenaar: Rakesh Ramkhelawan | ADR: ADR-028 | Laatste update: 2026-05-26
