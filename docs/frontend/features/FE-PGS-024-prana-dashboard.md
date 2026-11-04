# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-024
- Feature naam: PranaDashboard dark-mode pagina
- Status: Completed (SP-FE-2F CLOSED)
- Auteur: Implementatie-agent SP-FE-2F Dag 1
- Reviewer: Reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2F Prana A2A / Shadow CEO Governance Pages
- Gerelateerde pagina / route: /prana (toegevoegd in dag 4)
- Gerelateerde backend endpoints: GET /v1/prana/balance, GET /v1/prana/ledger, GET /v1/contracts
- Gerelateerde design componenten: PranaGauge, PermissionGate
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een dark-mode dashboard waarmee een business gebruiker het Prana-economieoverzicht van zijn tenant kan bekijken: huidige balans, verbruik, quota en periodecontext.

### In scope

- Nieuwe pagina `PranaDashboard` in `frontend/src/pages/redesign/PranaDashboard.tsx`.
- Nieuwe herbruikbare component `PranaGauge` in `frontend/src/components/prana/PranaGauge.tsx`.
- Periode-selector (Day / Month / Year) als lokale UI-state.
- Loading, empty en error states.
- PermissionGate met `prana:read` scope.
- Hergebruik van bestaande `usePranaContractsStore` data-logica.
- ADR-028 compliance: dark theme, geen inline styles, SVG-attributen toegestaan.

### Out of scope

- ~~Route-wiring in `App.tsx` en `BusinessSidebar.tsx`~~ — opgeleverd in dag 4.
- ~~Backend scope-registratie voor `prana:read` / `prana:manage`~~ — opgeleverd in dag 4.
- Live data polling / refreshes.
- Gedetailleerde ledger-tabel of contract-grafiek (dag 2 / dag 3).
- A2A contract flow integratie (dag 2).

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/pages/redesign/PranaDashboard.tsx`
  - `frontend/src/components/prana/PranaGauge.tsx`
  - `frontend/src/pages/redesign/__tests__/PranaDashboard.test.tsx`
  - `frontend/src/components/prana/__tests__/PranaGauge.test.tsx`
- Gewijzigd:
  - `frontend/src/lib/stores/authStore.ts` — OAuth2Scope union uitgebreid met `prana:read` en `prana:manage`.
  - `frontend/src/App.tsx` — route `/prana` toegevoegd onder `ProtectedRoute` / `LazyWrapper` (dag 4).
  - `frontend/src/components/layout/BusinessSidebar.tsx` — nav item "Prana" toegevoegd (dag 4).
  - `src/core/auth/scopes.py` — `PRANA_READ` / `PRANA_MANAGE` scopes geregistreerd (dag 4).
  - `src/core/auth/auth_service.py` — `prana:read` / `prana:manage` toegekend aan relevante rollen (dag 4).
- Verwijderd: geen.
- Beinvloede bestaande flows: geen (pagina is gerouteerd).

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-024 | PranaDashboard | Pagina | `src/pages/redesign/PranaDashboard.tsx` | Nieuw | Prana overzicht bekijken |
| FE-CMP-037 | PranaGauge | Component | `src/components/prana/PranaGauge.tsx` | Nieuw | Prana overzicht bekijken |
| FE-TAB-001 | Period selector | Tab groep | `src/pages/redesign/PranaDashboard.tsx` | Nieuw | Periode wisselen |

---

## Gebruikersflows

### Flow ID: FE-FLW-001

- Naam: Prana-dashboard bekijken
- Startconditie: Gebruiker is ingelogd en heeft `prana:read` scope.
- Trigger: Gebruiker opent de Prana-dashboard pagina.
- Hoofdstappen:
  1. Systeem toont de pagina met title "Prana Dashboard".
  2. Systeem toont metrics: Current Balance, Locked in Escrow, Remaining Budget.
  3. Systeem toont drie gauges: Balance, Usage, Quota.
  4. Gebruiker kan periode wisselen via Day / Month / Year tabs.
- Succespad: Alle data wordt getoond; tabs zijn interactief.
- Foutpad: Bij API-fout toont het systeem een rode error banner.
- Eindtoestand: Gebruiker heeft inzicht in de Prana-economie.

---

## Detaildocumentatie per item

---

## [FE-PGS-024] PranaDashboard

### 1. Type

Pagina component (React function component).

### 2. Locatie

`frontend/src/pages/redesign/PranaDashboard.tsx`

### 3. Gerelateerde flow

FE-FLW-001 — Prana-dashboard bekijken.

### 4. Doel

Centrale dark-mode pagina voor het monitoren van de Prana-economie binnen een tenant.

### 5. Functionele beschrijving

De pagina toont bovenaan een title en een periode-selector. Daaronder worden drie metric-cards getoond met de huidige balans, het bedrag in escrow en het resterende budget. Onder de metrics staan drie circulaire gauges die dezelfde waarden visueel weergeven. De pagina heeft een loading-skeleton, een empty-state en een error-banner.

### 6. Technische beschrijving

- Haalt `balances`, `metrics`, `isLoading` en `error` uit `usePranaContractsStore`.
- Houdt `period` bij in lokale `useState` ('day' | 'month' | 'year').
- Wrapped in `<PermissionGate requiredScope="prana:read" showOverlay>`.
- Container: `min-h-screen bg-slate-950 p-6 text-slate-100`.
- Geen inline styles; alle kleuren via Tailwind of `pranaColors` tokens.

### 7. Zichtbaarheidsregels

- Alleen zichtbaar voor gebruikers met `prana:read` scope.
- Zonder scope toont PermissionGate een overlay met "Access Denied".

### 8. States en gedrag

- Default: toont metrics en gauges zodra data beschikbaar is.
- Loading: toont centered spinner binnen een card (`data-testid="prana-loading"`).
- Empty: toont melding "No Prana data available" wanneer `balances.length === 0`.
- Error: toont rode banner met store error (`role="alert"`).
- Tab active: geselecteerde periode krijgt `bg-slate-700 text-white` en `aria-selected="true"`.

### 9. Input

- Data uit `usePranaContractsStore`.
- Gebruikersinteractie: klik op periode-tab.

### 10. Output

- Visuele weergave van Prana metrics.
- Lokale state `period` wordt bijgewerkt.

### 11. Validaties

- Geen formulier-validatie.

### 12. Business rules

- Metrics worden berekend door `usePranaContractsStore` op basis van balances en contracts.
- Gauge maxima worden afgeleid van `currentBalance + totalConsumed` met minimum 100.

### 13. Afhankelijkheden

- `usePranaContractsStore`
- `PermissionGate`
- `PranaGauge`
- `lucide-react` icons

### 14. Foutafhandeling

- Store error wordt getoond in rode alert-banner.
- Permission denied wordt afgehandeld door PermissionGate overlay.

### 15. Telemetry / logging / analytics

- Geen telemetry toegevoegd.

### 16. Accessibility-notities

- Error banner heeft `role="alert"`.
- Periode-tabs hebben `role="tab"` en `aria-selected`.
- Title is een `h1`.

### 17. Acceptatiecriteria

- [ ] Pagina rendert zonder crash.
- [ ] Metrics tonen de waarden uit de store.
- [ ] Drie gauges zijn zichtbaar.
- [ ] Periode-tabs zijn klikbaar en updaten `aria-selected`.
- [ ] Loading state toont spinner.
- [ ] Empty state toont bij geen balances.
- [ ] Error state toont store error.
- [ ] Zonder `prana:read` scope toont PermissionGate overlay.
- [ ] Geen inline styles in de gerenderde output.

### 18. Gebruikersuitleg

- Open het Prana-dashboard om de financiele gezondheid van je agent-economie te zien.
- De metrics bovenaan tonen cijfers; de gauges geven een visueel inzicht.
- Wissel tussen Day, Month en Year om de periodecontext te veranderen.
- Bij een fout verschijnt een rode melding bovenaan de pagina.

### 19. Trainingssamenvatting

- Actor: Business gebruiker
- Voorwaarde: Gebruiker is ingelogd en heeft `prana:read` scope; store bevat balances/metrics.
- Actie: Gebruiker opent het Prana-dashboard en klikt eventueel op een periode-tab.
- Systeemreactie: Pagina toont title, metrics, gauges en de geselecteerde periode.
- Succesrespons: Alle data is zichtbaar en de juiste tab is actief.
- Foutrespons: Rode error banner toont de foutmelding uit de store.
- Uitzonderingen: Zonder scope toont PermissionGate een toegangsweigering; bij lege data toont de pagina een empty-state.

---

## [FE-CMP-037] PranaGauge

### 1. Type

Herbruikbaar UI-component.

### 2. Locatie

`frontend/src/components/prana/PranaGauge.tsx`

### 3. Gerelateerde flow

FE-FLW-001 — Prana-dashboard bekijken.

### 4. Doel

Visuele weergave van een numerieke waarde als circulaire gauge in dark-mode.

### 5. Functionele beschrijving

Toont een cirkelvormige voortgangsmeter met een label, numerieke waarde en optionele eenheid. De indicator kleurt afhankelijk van de variant (balance, usage, quota).

### 6. Technische beschrijving

- Gebouwd met SVG `<circle>` elementen.
- Achtergrondtrack en indicator hebben elk een `<circle>`.
- `strokeDasharray` en `strokeDashoffset` bepalen de gevulde boog.
- Waarde wordt geclampd tussen 0 en `max`.
- Variant bepaalt de Tailwind kleur class (`text-prana-balance`, `text-prana-spent`, `text-prana-cap`).

### 7. Zichtbaarheidsregels

- Altijd zichtbaar wanneer gerenderd door parent.
- Geen eigen permission logic.

### 8. States en gedrag

- Default: toont gauge met percentage gebaseerd op value/max.
- Clamping: waarden boven max worden getoond als 100%; negatieve waarden als 0%.

### 9. Input

- `label: string`
- `value: number`
- `max?: number` (default 100)
- `unit?: string`
- `variant?: 'balance' | 'usage' | 'quota'` (default 'balance')

### 10. Output

- Visuele gauge.
- SVG heeft `role="img"`, `aria-label`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`.

### 11. Validaties

- `max` moet een niet-negatief getal zijn; `value` wordt geclampd.

### 12. Business rules

- Kleuren komen uit `tokens.colors.pranaColors` via Tailwind (`text-prana-*`).

### 13. Afhankelijkheden

- React
- Tailwind CSS
- `pranaColors` tokens (via Tailwind config)

### 14. Foutafhandeling

- Geen; clamping voorkomt invalid visuele output.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- SVG heeft `role="img"` en `aria-label`.
- ARIA waarde-attributen worden gezet op basis van percentage.
- Center label is plain text binnen een div.

### 17. Acceptatiecriteria

- [ ] Gauge toont label, waarde en eenheid.
- [ ] Indicator boog verandert mee met percentage.
- [ ] Waarden boven max worden op 100% geclampd.
- [ ] Negatieve waarden worden op 0% geclampd.
- [ ] Variant wijzigt de kleur class.
- [ ] Geen inline styles in de gerenderde HTML.
- [ ] SVG heeft correcte ARIA-attributen.

### 18. Gebruikersuitleg

- Elke gauge toont een getal in een cirkel.
- Het groene vlak van de cirkel laat zien hoe ver de waarde ten opzichte van het maximum is.
- Balance is groen, Usage is rood, Quota is paars.

### 19. Trainingssamenvatting

- Actor: Systeem (rendert op dashboard)
- Voorwaarde: Parent levert label, value, max, unit en variant.
- Actie: Component rendert SVG gauge met geclampde waarde.
- Systeemreactie: Gauge toont visuele percentageboog en ARIA-waarden.
- Succesrespons: Correct gevulde cirkel met label en waarde.
- Foutrespons: Geen; clamping corrigeert buiten-bereik waarden.
- Uitzonderingen: Negatieve waarden worden 0%; waarden boven max worden 100%.

---

## [FE-TAB-001] Period selector

### 1. Type

Tab groep (buttons met role="tab").

### 2. Locatie

`frontend/src/pages/redesign/PranaDashboard.tsx` (header sectie).

### 3. Gerelateerde flow

FE-FLW-001 — Prana-dashboard bekijken.

### 4. Doel

Laat de gebruiker wisselen tussen dag-, maand- en jaaroversicht.

### 5. Functionele beschrijving

Drie buttons naast elkaar die eruitzien als tabs. De actieve tab heeft een donkere achtergrond; inactieve tabs zijn lichter grijs.

### 6. Technische beschrijving

- Lokale state `period` in PranaDashboard.
- Buttons hebben `role="tab"` en `aria-selected`.
- `onClick` updateert de lokale state.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar binnen de pagina (zolang de gebruiker toegang heeft).

### 8. States en gedrag

- Default: "Day" is geselecteerd.
- Active: `bg-slate-700 text white`.
- Inactive: `text-slate-400 hover:text-slate-200`.

### 9. Input

- Gebruikersklik.

### 10. Output

- Bijgewerkte `period` state.
- Visuele active-state wijziging.

### 11. Validaties

- Alleen de drie gedefinieerde waarden zijn toegestaan.

### 12. Business rules

- Periode beinvloedt momenteel alleen de UI-state; filtering op data is out-of-scope.

### 13. Afhankelijkheden

- PranaDashboard state.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Buttons hebben `role="tab"` en `aria-selected`.

### 17. Acceptatiecriteria

- [ ] Drie tabs zijn zichtbaar: Day, Month, Year.
- [ ] Klikken op een tab maakt deze actief.
- [ ] Actieve tab heeft `aria-selected="true"`.

### 18. Gebruikersuitleg

- Klik op Day, Month of Year om de periodecontext te veranderen.

### 19. Trainingssamenvatting

- Actor: Business gebruiker
- Voorwaarde: Dashboard is zichtbaar.
- Actie: Gebruiker klikt op een periode-tab.
- Systeemreactie: De gekozen tab krijgt active styling en `aria-selected="true"`.
- Succesrespons: Juiste tab is visueel actief.
- Foutrespons: Geen.
- Uitzonderingen: Geen.

---

## Handleidingstekst

### Voor eindgebruikers

**Prana Dashboard**

Het Prana-dashboard geeft inzicht in de agent-economie van je organisatie.

1. Open het dashboard via het navigatiemenu (beschikbaar na sprint-dag 4).
2. Bovenaan zie je drie cijfers: huidige balans, bedrag in escrow en resterend budget.
3. Onder de cijfers zie je drie gauges die de waarden visueel weergeven.
4. Gebruik de tabs Day / Month / Year om de periodecontext te wisselen.
5. Als er geen data is, zie je een melding dat er nog geen transacties zijn.
6. Bij een fout verschijnt een rode banner met de foutmelding.

**Toegang:** je hebt de `prana:read` permissie nodig. Zonder deze permissie zie je een toegangsweigering.

---

## Open aannames

- De route `/prana` is op dag 4 toegevoegd in `App.tsx` en `BusinessSidebar.tsx`.
- De backend scopes `prana:read` / `prana:manage` zijn op dag 4 geregistreerd in `src/core/auth/scopes.py` en gekoppeld aan rollen in `src/core/auth/auth_service.py`.
- Data fetching gebeurt via de bestaande `usePranaContractsStore`; de pagina zelf doet geen nieuwe API calls.

## Open vragen

- Moet de periode-selector in de toekomst daadwerkelijk de opgehaalde data filteren of alleen de visualisatie beinvloeden?

## Risico's

- ~~Backend scope gap~~ — opgelost in dag 4; `prana:read` is nu een geregistreerd OAuth2Scope.
- **Data-ontbreken:** als de store nooit wordt gehydrateerd, blijft de pagina in empty-state.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [x] Error states getest
- [x] Accessibility gecontroleerd
- [x] Responsive gecontroleerd (grid gebruikt sm: breakpoints)
- [ ] Cross-browser gecontroleerd
- [ ] Analytics/logging gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle interactieve elementen zijn geinventariseerd
- [x] Alle relevante states zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Gebruikersuitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS


---

## Sprint closure (SP-FE-2F)

- **Sprint:** SP-FE-2F — Phase 2 Visual Redesign: Prana economy + Shadow CEO governance
- **Dag 1 deliverable:** PranaDashboard + PranaGauge — Final Approver: **GO**
- **Dag 4 afsluiting:** route `/prana` en backend scopes opgeleverd.
- **Sprint eindoordeel:** **GO** — geen open bevindingen.
- **Commits:**
  - `9582c83f` — Dag 1: PranaDashboard + PranaGauge
  - `0ff021fa` — Dag 1 revisie: PranaGauge stroke + role=meter
  - `5eba2e83` — Dag 3-4: route wiring + backend scopes
  - `12bb06d2` — Dag 4: review fixes
  - `840536ef` — FA minors adres
  - `21e5713c` — Final Approver GO, sprint CLOSED
- **Testresultaat:** alle 3 Vitest shards groen (4783 + 4650 + 5165 passed / 0 failed).
- **Feature docs validatie:** `python scripts/validate_feature_docs.py` — 427 IDs [PASS].
