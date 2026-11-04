# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-025
- Feature naam: A2AContracts dark-mode pagina
- Status: Completed (SP-FE-2F CLOSED)
- Auteur: Implementatie-agent SP-FE-2F Dag 2
- Reviewer: reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2F Prana A2A / Shadow CEO Governance Pages
- Gerelateerde pagina / route: /prana/contracts (toegevoegd in dag 4)
- Gerelateerde backend endpoints: GET /v1/contracts
- Gerelateerde design componenten: A2AContractFlow, PermissionGate
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een dark-mode pagina waarmee een business gebruiker agent-to-agent (A2A) contracten kan bekijken, filteren op status, en visualiseren als flow.

### In scope

- Nieuwe pagina `A2AContracts` in `frontend/src/pages/redesign/A2AContracts.tsx`.
- Nieuwe herbruikbare component `A2AContractFlow` in `frontend/src/components/prana/A2AContractFlow.tsx`.
- Status filter buttons (All / Proposed / Agreed / Executing / Completed / Failed / Disputed).
- Agent selectie in de flow die de contractlijst filtert.
- Loading, empty en error states.
- PermissionGate met `prana:read` scope.
- Hergebruik van bestaande `usePranaContractsStore` data-logica.
- ADR-028 compliance: dark theme, geen inline styles, SVG-attributen toegestaan.

### Out of scope

- ~~Route-wiring in `App.tsx` en `BusinessSidebar.tsx`~~ — opgeleverd in dag 4.
- ~~Backend scope-registratie voor `prana:read` / `prana:manage`~~ — opgeleverd in dag 4.
- Contract creatie / editing / goedkeuring flows.
- Gedetailleerde contract detail view.

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/pages/redesign/A2AContracts.tsx`
  - `frontend/src/components/prana/A2AContractFlow.tsx`
  - `frontend/src/pages/redesign/__tests__/A2AContracts.test.tsx`
  - `frontend/src/components/prana/__tests__/A2AContractFlow.test.tsx`
- Gewijzigd:
  - `frontend/src/App.tsx` — route `/prana/contracts` toegevoegd onder `ProtectedRoute` / `LazyWrapper` (dag 4).
  - `frontend/src/components/layout/BusinessSidebar.tsx` — nav item "A2A Contracts" toegevoegd met `FileSignature` icoon (dag 4).
- Verwijderd: geen.
- Beinvloede bestaande flows: geen (pagina is gerouteerd).

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-025 | A2AContracts | Pagina | `src/pages/redesign/A2AContracts.tsx` | Nieuw | A2A contracten bekijken |
| FE-CMP-039 | A2AContractFlow | Component | `src/components/prana/A2AContractFlow.tsx` | Nieuw | A2A contracten bekijken |
| FE-FLT-001 | Status filter | Filter | `src/pages/redesign/A2AContracts.tsx` | Nieuw | Contracten filteren op status |
| FE-TBL-001 | Contract table | Tabel | `src/pages/redesign/A2AContracts.tsx` | Nieuw | Contractlijst weergeven |

---

## Gebruikersflows

### Flow ID: FE-FLW-001

- Naam: A2A contracten bekijken en filteren
- Startconditie: Gebruiker is ingelogd en heeft `prana:read` scope.
- Trigger: Gebruiker opent de A2A Contracts pagina.
- Hoofdstappen:
  1. Systeem toont de pagina met title "A2A Contracts".
  2. Systeem toont de status filter buttons.
  3. Systeem toont de A2AContractFlow visualisatie.
  4. Systeem toont de contract tabel.
  5. Gebruiker kan op een status filter klikken om de lijst te filteren.
  6. Gebruiker kan op een agent node klikken om te filteren op contracten voor die agent.
- Succespad: Gefilterde lijst en flow reflecteren de gekozen filters.
- Foutpad: Bij API-fout toont het systeem een rode error banner.
- Eindtoestand: Gebruiker heeft inzicht in de A2A contracten.

---

## Detaildocumentatie per item

---

## [FE-PGS-025] A2AContracts

### 1. Type

Pagina component (React function component).

### 2. Locatie

`frontend/src/pages/redesign/A2AContracts.tsx`

### 3. Gerelateerde flow

FE-FLW-002 — A2A contracten bekijken en filteren.

### 4. Doel

Centrale dark-mode pagina voor het bekijken en filteren van A2A contracten.

### 5. Functionele beschrijving

De pagina toont bovenaan een title en beschrijving. Daaronder staan status filter buttons. De A2AContractFlow component visualiseert agenten en contracten als een SVG netwerk. Onder de flow staat een tabel met contract details. Wanneer een agent wordt geselecteerd in de flow, wordt de contractlijst gefilterd op contracten waarbij die agent betrokken is.

### 6. Technische beschrijving

- Haalt `contracts`, `selectedAgentId`, `setSelectedAgent`, `isLoading` en `error` uit `usePranaContractsStore`.
- Houdt `statusFilter` bij in lokale `useState` ('all' | ContractStatus).
- Wrapped in `<PermissionGate requiredScope="prana:read" showOverlay>`.
- Container: `min-h-screen bg-slate-950 p-6 text-slate-100`.
- Geen inline styles; alle kleuren via Tailwind of `pranaColors` tokens.
- Filter logica:
  - Status filter: toont alleen contracten met de geselecteerde status.
  - Agent filter: toont alleen contracten waarbij de geselecteerde agent producer of consumer is.
  - Beide filters kunnen tegelijk actief zijn.

### 7. Zichtbaarheidsregels

- Alleen zichtbaar voor gebruikers met `prana:read` scope.
- Zonder scope toont PermissionGate een overlay met "Access Denied".

### 8. States en gedrag

- Default: toont flow en tabel met alle contracten.
- Loading: toont centered spinner binnen een card (`data-testid="a2a-loading-state"`).
- Empty: toont melding "No A2A contracts found" wanneer `contracts.length === 0`.
- Error: toont rode banner met store error (`data-testid="a2a-error-state"`).
- Filter active: geselecteerde status button krijgt `border-prana-primary bg-prana-primary/10 text-prana-primary`.
- Agent selected: toont boven de tabel een filter bar met "Clear filter" knop.

### 9. Input

- Data uit `usePranaContractsStore`.
- Gebruikersinteractie: klik op status filter, klik op agent node, klik op "Clear filter".

### 10. Output

- Visuele weergave van gefilterde A2A contracten.
- Bij agent selectie: `setSelectedAgent(agentId)` wordt aangeroepen.

### 11. Validaties

- Geen formulier-validatie.

### 12. Business rules

- Status badge kleuren komen uit `STATUS_BADGE_CLASSES` mapping.
- De flow toont altijd ALLE contracten, onafhankelijk van de status/agent filter (de filter beinvloedt alleen de tabel).

### 13. Afhankelijkheden

- `usePranaContractsStore`
- `PermissionGate`
- `A2AContractFlow`
- `lucide-react` icons

### 14. Foutafhandeling

- Store error wordt getoond in rode alert-banner.
- Permission denied wordt afgehandeld door PermissionGate overlay.

### 15. Telemetry / logging / analytics

- Geen telemetry toegevoegd.

### 16. Accessibility-notities

- Error banner heeft `role="alert"`.
- Filter buttons zijn `<button>` elementen.
- Tabel heeft `<thead>` en `<tbody>`.

### 17. Acceptatiecriteria

- [ ] Pagina rendert zonder crash.
- [ ] Status filter buttons zijn zichtbaar en klikbaar.
- [ ] Klikken op een status filter toont alleen contracten met die status.
- [ ] Klikken op "All" toont alle contracten.
- [ ] Klikken op een agent node in de flow selecteert die agent.
- [ ] Geselecteerde agent filtert de contract tabel.
- [ ] Loading state toont spinner.
- [ ] Empty state toont bij geen contracts.
- [ ] Error state toont store error.
- [ ] Zonder `prana:read` scope toont PermissionGate overlay.
- [ ] Geen inline styles in de gerenderde output.

### 18. Gebruikersuitleg

- Open A2A Contracts om een overzicht te zien van alle agent-overeenkomsten.
- Gebruik de filter buttons bovenaan om te filteren op contractstatus.
- Klik op een agent in de flow om alleen contracten voor die agent te zien.
- Klik op "Clear filter" om de agent-filter te verwijderen.
- Bij een fout verschijnt een rode melding bovenaan de pagina.

### 19. Trainingssamenvatting

- Actor: Business gebruiker
- Voorwaarde: Gebruiker is ingelogd en heeft `prana:read` scope; store bevat contracts.
- Actie: Gebruiker opent A2A Contracts en klikt op een status filter of agent node.
- Systeemreactie: Pagina toont title, filters, flow en gefilterde contract tabel.
- Succesrespons: De juiste contracten zijn zichtbaar op basis van de gekozen filters.
- Foutrespons: Rode error banner toont de foutmelding uit de store.
- Uitzonderingen: Zonder scope toont PermissionGate een toegangsweigering; bij lege data toont de pagina een empty-state.

---

## [FE-CMP-039] A2AContractFlow

### 1. Type

Herbruikbaar UI-component.

### 2. Locatie

`frontend/src/components/prana/A2AContractFlow.tsx`

### 3. Gerelateerde flow

FE-FLW-002 — A2A contracten bekijken en filteren.

### 4. Doel

Visuele weergave van agenten en hun A2A contracten als een SVG netwerk-flow in dark-mode.

### 5. Functionele beschrijving

Toont unieke agenten als nodes en contracten als gerichte lijnen (edges) tussen nodes. Edges hebben een kleur afhankelijk van de contractstatus en tonen de Prana kost. Agent nodes zijn klikbaar; klikken selecteert of deselecteert de agent.

### 6. Technische beschrijving

- Gebouwd met pure SVG (`<svg>`, `<line>`, `<circle>`, `<text>`, `<g>`, `<marker>`, `<polygon>`).
- Props:
  ```typescript
  interface A2AContractFlowProps {
    contracts: ContractEntry[];
    selectedAgentId: string | null;
    onAgentSelect: (agentId: string | null) => void;
  }
  ```
- `buildLayout` berekent een grid layout voor agent nodes.
- Edges gebruiken `stroke="currentColor"` + Tailwind stroke-utility klasse per status.
- Nodes gebruiken `fill-slate-800` + `stroke-*` voor border.
- Geen `style={}` props.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar binnen de parent pagina (zolang de gebruiker toegang heeft).
- Toont empty-state wanneer `contracts.length === 0`.

### 8. States en gedrag

- Default: toont alle agent nodes en contract edges.
- Selected node: krijgt een dikkere `stroke-prana-primary` border.
- Empty: toont "No active contracts to visualize."

### 9. Input

- `contracts: ContractEntry[]`
- `selectedAgentId: string | null`
- `onAgentSelect: (agentId: string | null) => void`

### 10. Output

- Visuele SVG flow.
- Bij node klik: `onAgentSelect` callback met geselecteerde of gedeselecteerde agent id.

### 11. Validaties

- Contracts met onbekende agenten worden genegeerd voor edges.

### 12. Business rules

- Status naar stroke-klasse mapping:
  - proposed: `stroke-slate-400`
  - negotiating: `stroke-blue-400`
  - agreed: `stroke-blue-500`
  - executing: `stroke-prana-primary`
  - completed: `stroke-status-success`
  - failed: `stroke-status-error`
  - disputed: `stroke-red-600`
- Proposed edges renderen met `strokeDasharray="4 2"`.

### 13. Afhankelijkheden

- React
- Tailwind CSS
- `pranaColors` / status tokens (via Tailwind config)

### 14. Foutafhandeling

- Geen; invalid input wordt stilzwijgend genegeerd.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- SVG heeft `role="img"` en `aria-label="A2A contract flow"`.
- Agent nodes hebben `data-testid` voor tests.
- Edge labels zijn `<text>` elementen.

### 17. Acceptatiecriteria

- [ ] Flow toont agent nodes voor alle producers en consumers.
- [ ] Flow toont edges voor alle contracts.
- [ ] Edges tonen de Prana kost.
- [ ] Edge kleur verandert per contract status.
- [ ] Klikken op een node selecteert/deselecteert de agent.
- [ ] Geen inline styles in de gerenderde HTML.
- [ ] Empty state toont bij geen contracts.

### 18. Gebruikersuitleg

- De flow toont agenten als cirkels en contracten als pijlen.
- De kleur van een pijl geeft de status van het contract aan.
- Klik op een agent-cirkel om de contractlijst eronder te filteren.
- Als er geen contracten zijn, zie je een melding in plaats van de flow.

### 19. Trainingssamenvatting

- Actor: Systeem (rendert op pagina) / gebruiker (interactie)
- Voorwaarde: Parent levert contracts, selectedAgentId en callback.
- Actie: Component rendert SVG nodes en edges; gebruiker klikt op een node.
- Systeemreactie: Geselecteerde agent krijgt visuele highlight; callback wordt aangeroepen.
- Succesrespons: Flow toont correct netwerk met gekleurde edges.
- Foutrespons: Geen.
- Uitzonderingen: Contracten met onbekende agenten worden niet getekend.

---

## [FE-FLT-001] Status filter

### 1. Type

Filter button groep.

### 2. Locatie

`frontend/src/pages/redesign/A2AContracts.tsx`.

### 3. Gerelateerde flow

FE-FLW-002.

### 4. Doel

Laat de gebruiker de contractlijst filteren op status.

### 5. Functionele beschrijving

Rij van buttons met status labels. De actieve button heeft een oranje rand en achtergrond; inactieve buttons zijn grijs.

### 6. Technische beschrijving

- Lokale state `statusFilter` in A2AContracts.
- Buttons roepen `setStatusFilter(value)` aan.
- Opties: All, Proposed, Negotiating, Agreed, Executing, Completed, Failed, Disputed.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar binnen de pagina.

### 8. States en gedrag

- Default: "All" is geselecteerd.
- Active: `border-prana-primary bg-prana-primary/10 text-prana-primary`.
- Inactive: `border-white/10 bg-slate-900/60 text-slate-400`.

### 9. Input

- Gebruikersklik.

### 10. Output

- Bijgewerkte `statusFilter` state en gefilterde contract tabel.

### 11. Validaties

- Alleen de gedefinieerde status-waarden zijn toegestaan.

### 12. Business rules

- De flow visualisatie wordt NIET gefilterd; alleen de tabel.

### 13. Afhankelijkheden

- A2AContracts state.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Buttons zijn native `<button>` elementen.

### 17. Acceptatiecriteria

- [ ] Alle status opties zijn zichtbaar.
- [ ] Klikken op een filter maakt deze actief.
- [ ] De tabel toont alleen contracten met de geselecteerde status.

### 18. Gebruikersuitleg

- Klik op een status om de contractlijst te filteren.
- Klik op "All" om alle contracten weer te zien.

### 19. Trainingssamenvatting

- Actor: Business gebruiker
- Voorwaarde: Pagina is zichtbaar.
- Actie: Gebruiker klikt op een status filter.
- Systeemreactie: De gekozen button krijgt active styling; tabel wordt gefilterd.
- Succesrespons: Alleen contracten met de gekozen status zijn zichtbaar.
- Foutrespons: Geen.
- Uitzonderingen: Geen.

---

## [FE-TBL-001] Contract table

### 1. Type

Tabel.

### 2. Locatie

`frontend/src/pages/redesign/A2AContracts.tsx`.

### 3. Gerelateerde flow

FE-FLW-002.

### 4. Doel

Toon contract details in een overzichtelijke tabel.

### 5. Functionele beschrijving

Tabel met kolommen: Contract ID, Producer, Consumer, Status, Cost. Rijen hebben een hover effect. Wanneer filters geen resultaat opleveren, toont de tabel een "No contracts match" melding.

### 6. Technische beschrijving

- HTML `<table>` met `<thead>` en `<tbody>`.
- Kolommen: contract_id, producer_agent, consumer_agent, status badge, prana_cost.
- Hover: `hover:bg-white/5`.

### 7. Zichtbaarheidsregels

- Zichtbaar wanneer er minimaal 1 contract is.
- Bij geen matches binnen de tabel wordt een melding getoond.

### 8. States en gedrag

- Default: toont gefilterde rijen.
- Empty tabel: melding "No contracts match the current filters."

### 9. Input

- Gefilterde contract array.

### 10. Output

- Visuele tabel.

### 11. Validaties

- Geen.

### 12. Business rules

- Prana cost wordt weergegeven met " P" suffix.

### 13. Afhankelijkheden

- A2AContracts filter logica.
- StatusBadge component.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Tabel gebruikt semantische `<table>`, `<thead>`, `<tbody>`, `<th>`, `<tr>`, `<td>`.

### 17. Acceptatiecriteria

- [ ] Tabel toont alle kolommen.
- [ ] Status kolom toont een badge.
- [ ] Hover state is zichtbaar.
- [ ] Bij geen matches toont de tabel een melding.

### 18. Gebruikersuitleg

- De tabel toont alle contracten die voldoen aan de huidige filters.
- De status badge laat in een oogopslag zien wat de status is.

### 19. Trainingssamenvatting

- Actor: Systeem
- Voorwaarde: Gefilterde contract array is beschikbaar.
- Actie: Systeem rendert tabelrijen.
- Systeemreactie: Tabel toont contract details met status badges.
- Succesrespons: Alle relevante contracten zijn zichtbaar.
- Foutrespons: Geen.
- Uitzonderingen: Bij lege filterresultaten toont de tabel een melding.

---

## Handleidingstekst

### Voor eindgebruikers

**A2A Contracts**

De A2A Contracts pagina geeft inzicht in alle agent-overeenkomsten binnen je organisatie.

1. Open A2A Contracts via het menu (beschikbaar na sprint-dag 4).
2. Bovenaan zie je filter buttons voor elke contractstatus.
3. In het midden zie je een flow waarin agenten en hun contracten zijn weergegeven.
4. Klik op een agent-cirkel om alleen contracten voor die agent te zien.
5. Onder de flow zie je een tabel met alle contract details.
6. Gebruik "Clear filter" om de agent-filter te verwijderen.

**Fouten en bijzondere situaties**

- **Geen contracten:** als er nog geen A2A overeenkomsten zijn, zie je de melding "No A2A contracts found."
- **Foutmelding:** bij een API-fout verschijnt een rode banner bovenaan de pagina.
- **Geen toegang:** als je "Access Denied" ziet, heb je niet de juiste permissie (`prana:read`).

---

## Open aannames

- De route `/prana/contracts` is op dag 4 toegevoegd in `App.tsx` en `BusinessSidebar.tsx`.
- De backend scopes `prana:read` / `prana:manage` zijn op dag 4 geregistreerd in `src/core/auth/scopes.py` en gekoppeld aan rollen in `src/core/auth/auth_service.py`.
- De flow visualisatie toont altijd alle contracten; filters beinvloeden alleen de contract tabel.

## Open vragen

- Moet de flow visualisatie in de toekomst ook mee filteren op status/agent?
- Is een aparte detail-view voor individuele contracten gewenst?

## Risico's

- ~~Backend scope gap~~ — opgelost in dag 4; `prana:read` is nu een geregistreerd OAuth2Scope.
- **Data-ontbreken:** als de store nooit wordt gehydrateerd, blijft de pagina in empty-state.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [x] Error states getest
- [x] Accessibility gecontroleerd
- [x] Responsive gecontroleerd (overflow-auto + h-auto w-full)
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
- **Dag 2 deliverable:** A2AContracts + A2AContractFlow — Final Approver: **GO WITH MINOR ISSUES** (minors later opgelost)
- **Dag 4 afsluiting:** route `/prana/contracts` en backend scopes opgeleverd.
- **Sprint eindoordeel:** **GO** — geen open bevindingen.
- **Commits:**
  - `af4d68af` — Dag 2: A2AContracts + A2AContractFlow
  - `a011504c` — Dag 2 FA-001: node stroke width conflict fix
  - `5eba2e83` — Dag 3-4: route wiring + backend scopes
  - `12bb06d2` — Dag 4: review fixes
  - `840536ef` — FA minors adres
  - `21e5713c` — Final Approver GO, sprint CLOSED
- **Testresultaat:** alle 3 Vitest shards groen (4783 + 4650 + 5165 passed / 0 failed).
- **Feature docs validatie:** `python scripts/validate_feature_docs.py` — 427 IDs [PASS].
