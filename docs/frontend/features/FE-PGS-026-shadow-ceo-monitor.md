# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-026
- Feature naam: ShadowCEOMonitor dark-mode pagina
- Status: Completed (SP-FE-2F CLOSED)
- Auteur: Implementatie-agent SP-FE-2F Dag 3
- Reviewer: reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2F Prana A2A / Shadow CEO Governance Pages
- Gerelateerde pagina / route: /shadow-ceo (toegevoegd in dag 4)
- Gerelateerde backend endpoints: GET /api/v1/governance/alerts
- Gerelateerde design componenten: ShadowCEOAlertFeed, PermissionGate
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een dark-mode monitor pagina waarmee een governance gebruiker real-time alerts en risicosignalen van de Shadow CEO kan bekijken, filteren op severity, en samenvattend kan inzien.

### In scope

- Nieuwe pagina `ShadowCEOMonitor` in `frontend/src/pages/redesign/ShadowCEOMonitor.tsx`.
- Nieuwe herbruikbare component `ShadowCEOAlertFeed` in `frontend/src/components/prana/ShadowCEOAlertFeed.tsx`.
- Nieuwe Zustand store `useShadowCEOStore` in `frontend/src/lib/stores/useShadowCEOStore.ts`.
- Nieuwe types `GovernanceAlertEntry` in `frontend/src/types/governanceAlerts.ts`.
- Severity filter buttons (All / Critical / High / Medium / Low).
- Toggle om acknowledged alerts wel of niet te tonen.
- Samenvattingscards: total / open / critical open alerts.
- Loading, empty en error states.
- PermissionGate met `governance:read` scope.
- ADR-028 compliance: dark theme, geen inline styles.

### Out of scope

- Route-wiring in `App.tsx` en `BusinessSidebar.tsx` (dag 4).
- Acknowledge-actie naar de backend (geen endpoint beschikbaar).
- Geluid / push notificaties bij nieuwe alerts.

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/pages/redesign/ShadowCEOMonitor.tsx`
  - `frontend/src/components/prana/ShadowCEOAlertFeed.tsx`
  - `frontend/src/lib/stores/useShadowCEOStore.ts`
  - `frontend/src/types/governanceAlerts.ts`
  - `frontend/src/lib/stores/__tests__/useShadowCEOStore.test.ts`
  - `frontend/src/components/prana/__tests__/ShadowCEOAlertFeed.test.tsx`
  - `frontend/src/pages/redesign/__tests__/ShadowCEOMonitor.test.tsx`
- Gewijzigd:
  - `frontend/src/lib/stores/authStore.ts` — `governance:read` scope toegevoegd.
- Verwijderd: geen.
- Beinvloede bestaande flows: geen (pagina is gerouteerd).

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-026 | ShadowCEOMonitor | Pagina | `src/pages/redesign/ShadowCEOMonitor.tsx` | Nieuw | Governance alerts bekijken |
| FE-CMP-040 | ShadowCEOAlertFeed | Component | `src/components/prana/ShadowCEOAlertFeed.tsx` | Nieuw | Governance alerts bekijken |
| FE-FLT-002 | Severity filter | Filter | `src/pages/redesign/ShadowCEOMonitor.tsx` | Nieuw | Alerts filteren op severity |
| FE-TBL-002 | Alert feed | Lijst | `src/components/prana/ShadowCEOAlertFeed.tsx` | Nieuw | Alert lijst weergeven |

---

## Gebruikersflows

### Flow ID: FE-FLW-002

- Naam: Governance alerts bekijken en filteren
- Startconditie: Gebruiker is ingelogd en heeft `governance:read` scope.
- Trigger: Gebruiker opent de Shadow CEO Monitor pagina.
- Hoofdstappen:
  1. Systeem toont de pagina met title "Shadow CEO Monitor".
  2. Systeem haalt governance alerts op via `GET /api/v1/governance/alerts`.
  3. Systeem toont samenvattingscards met total / open / critical open counts.
  4. Systeem toont severity filter buttons.
  5. Systeem toont de ShadowCEOAlertFeed lijst.
  6. Gebruiker kan op een severity filter klikken om de lijst te filteren.
  7. Gebruiker kan de "Show acknowledged" toggle inschakelen.
  8. Gebruiker kan op een alert klikken om deze te selecteren.
- Succespad: Gefilterde lijst reflecteert de gekozen filters.
- Foutpad: Bij API-fout toont het systeem een rode error banner in de feed.
- Eindtoestand: Gebruiker heeft inzicht in governance alerts.

---

## Detaildocumentatie per item

---

## [FE-PGS-026] ShadowCEOMonitor

### 1. Type

Pagina component (React function component).

### 2. Locatie

`frontend/src/pages/redesign/ShadowCEOMonitor.tsx`

### 3. Gerelateerde flow

FE-FLW-002 — Governance alerts bekijken en filteren.

### 4. Doel

Centrale dark-mode pagina voor het monitoren van governance alerts en risicosignalen.

### 5. Functionele beschrijving

De pagina toont bovenaan een title en beschrijving. Daaronder staan drie samenvattingscards. Daaronder bevinden zich severity filter buttons en een checkbox om acknowledged alerts te tonen. De ShadowCEOAlertFeed component toont de gefilterde alerts als een lijst. De pagina fetcht alerts bij mount via `useShadowCEOStore`.

### 6. Technische beschrijving

- Haalt `alerts`, `isLoading`, `error`, `severityFilter`, `showAcknowledged`, `selectedAlertId` en acties uit `useShadowCEOStore`.
- Houdt filters bij in de store (geen lokale `useState`).
- Wrapped in `<PermissionGate requiredScope="governance:read" showOverlay>`.
- Container: `min-h-screen bg-slate-950 p-6 text-slate-100`.
- Filter logica: `severityFilter === 'all' || alert.severity === severityFilter` en `showAcknowledged || !alert.acknowledged`.
- Samenvatting: total = `alerts.length`, open = niet acknowledged, critical open = critical en niet acknowledged.

### 7. Permissions / RBAC

- Vereiste scope: `governance:read`.
- `PermissionGate` toont een overlay bij ontbrekende scope.

### 8. A11y

- Samenvattingscards staan in een `<section aria-label="Alert summary">`.
- Filter buttons hebben `aria-pressed`.
- De alert feed heeft `role="list"` en items `role="listitem"`.
- Error state gebruikt `role="alert"`.

### 9. Tests

- Happy path: titel, summary counts, feed rendering.
- Filters: severity filter button klik, acknowledged toggle.
- Permission gate overlay zonder `governance:read`.
- Fetch wordt aangeroepen bij mount.

---

## [FE-CMP-040] ShadowCEOAlertFeed

### 1. Type

Herbruikbare React component.

### 2. Locatie

`frontend/src/components/prana/ShadowCEOAlertFeed.tsx`

### 3. Gerelateerde flow

FE-FLW-002.

### 4. Doel

Toon een lijst van governance alerts met severity badges en selectiegedrag.

### 5. Functionele beschrijving

De component accepteert alerts, loading, error en selectie props. Bij loading toont deze een loading state. Bij error een rode banner. Bij geen alerts een empty state. Anders sorteert de component alerts op `created_at` aflopend en toont ze als kaarten. Een klik op een alert selecteert of deselecteert deze.

### 6. Technische beschrijving

- Props interface: `ShadowCEOAlertFeedProps`.
- Severity mapping object `SEVERITY_CLASSES` bepaalt badge- en randkleuren.
- Gebruikt `useMemo` voor sorteren.
- Timestamp formatting via `toLocaleString`.

### 7. Permissions / RBAC

- Geen eigen scope-check; wordt afgeschermd door de pagina.

### 8. A11y

- `role="list"` / `role="listitem"`.
- `aria-label="Governance alerts"`.
- Severity badge heeft `data-testid` voor tests.

### 9. Tests

- Renderen van alerts.
- Sorteren op created_at descending.
- Severity badges.
- Selectie callbacks.
- Loading / error / empty states.

---

## [FE-FLT-002] Severity filter

### 1. Type

Filter controls op pagina niveau.

### 2. Locatie

`frontend/src/pages/redesign/ShadowCEOMonitor.tsx`

### 3. Doel

Toon alleen alerts van een bepaalde severity.

### 4. Technische beschrijving

- Buttons voor `all`, `critical`, `high`, `medium`, `low`.
- Active button heeft `bg-prana-primary text-slate-950`.
- Click roept `setSeverityFilter` aan.

---

## [FE-TBL-002] Alert feed

### 1. Type

Lijstweergave van governance alerts.

### 2. Locatie

`frontend/src/components/prana/ShadowCEOAlertFeed.tsx`

### 3. Doel

Toon alerts in een scanbare lijst met metadata.

### 4. Technische beschrijving

- Elke rij toont severity badge, violation_type, agent_name, timestamp en acknowledged status.
- Geselecteerde rij krijgt een gekleurde rand op basis van severity.

---

## Open aannames / risicos

- Backend endpoint `GET /api/v1/governance/alerts` moet de velden uit `GovernanceAlertEntry` teruggeven.
- Er is nog geen acknowledge endpoint; acknowledged badge is read-only.
- ~~Route wiring~~ — opgeleverd in dag 4 (`/shadow-ceo`).

---

## Trainingssamenvatting

| Aspect | Inhoud |
| ------ | ------ |
| Actor | Ingelogde gebruiker met `governance:read` scope. |
| Voorwaarde | Pagina is bereikbaar via `/shadow-ceo`. |
| Actie | Open Shadow CEO Monitor, pas filters toe. |
| Systeemreactie | Toont governance alerts, samenvatting en filterstatus. |
| Succesrespons | Gefilterde alert lijst is zichtbaar. |
| Foutrespons | Rode error banner bij API-fout. |
| Uitzonderingen | Ontbrekende scope toont PermissionGate overlay. |


---

## Sprint closure (SP-FE-2F)

- **Sprint:** SP-FE-2F — Phase 2 Visual Redesign: Prana economy + Shadow CEO governance
- **Dag 3 deliverable:** ShadowCEOMonitor + ShadowCEOAlertFeed — Final Approver: **GO**
- **Dag 4 afsluiting:** route `/shadow-ceo` en backend scope `governance:read` opgeleverd.
- **Sprint eindoordeel:** **GO** — geen open bevindingen.
- **Commits:**
  - `b2e5796b` / `936809da` — Dag 3 brief + correctie
  - `5eba2e83` — Dag 3-4: ShadowCEO + route wiring + backend scopes
  - `12bb06d2` — Dag 4: review fixes
  - `f7d0de3b` — pre-existing flaky test fixes
  - `840536ef` — FA minors adres
  - `21e5713c` — Final Approver GO, sprint CLOSED
- **Testresultaat:** alle 3 Vitest shards groen (4783 + 4650 + 5165 passed / 0 failed).
- **Feature docs validatie:** `python scripts/validate_feature_docs.py` — 427 IDs [PASS].
