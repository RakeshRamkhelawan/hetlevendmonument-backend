# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-027
- Feature naam: DigitalTwin page dark-mode retrofit (ADR-028)
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 2
- Reviewer: reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces
- Gerelateerde pagina / route: /digital-twin (route wiring Dag 3)
- Gerelateerde backend endpoints:
  - GET /v1/digital-twin/profile
  - GET /v1/digital-twin/ooda-metrics
  - POST /v1/digital-twin/consent
  - DELETE /v1/digital-twin/profile
- Gerelateerde design componenten: SyncStateBadge, MetricBar, ErasureModal, OODATimeline (FE-CMP-042)
- Versie: 1.0

---

## Doel en scope

### Doel

Retrofit van de bestaande DigitalTwin pagina naar het ADR-028 dark-mode ontwerp: vervang alle lichte Tailwind-klassen door dark-theme equivalenten, gebruik `status-*` tokens voor badge states, en integreer de nieuwe `OODATimeline` component.

### In scope

- `frontend/src/pages/DigitalTwin.tsx` -- dark-mode retrofit:
  - Root container: `bg-gradient-to-br from-slate-900 via-violet-900 to-slate-900` → `bg-slate-950` (loading en main state)
  - Kaarten: `bg-white border-gray-200` → `bg-slate-900 border-slate-800`
  - `SyncStateBadge`: `bg-green-100 text-green-800` → `bg-status-success/20 text-status-success` etc.
  - `MetricBar`: `text-gray-600 bg-gray-200` → `text-slate-400 bg-slate-800`
  - `ErasureModal`: `bg-white` → `bg-slate-950 border-slate-800`; invoerveld en knoppen donker
  - 4 `data-testid` attributen: `twin-profile-card`, `twin-consent-card`, `twin-ooda-card`, `twin-portability-card`
  - Export/erase knoppen: violet/red-50 hover → violet/red-950 hover
  - Integratie van `OODATimeline` component (hardcoded `activePhase="Observe"` voor MVP)
- `OODATimelinePhase` type collision opgelost: domein-type `OODAPhase` (UPPERCASE) in `@/types/digitalTwin` blijft onaangetast

### Out of scope

- Route wiring `/digital-twin` en PermissionGate `twin:read` (Dag 3)
- ADR-026 consent gate wiring (Dag 3)
- Dynamische OODA fase-berekening vanuit backend data (Dag 3)
- Backend scope registratie (Dag 3)

---

## Build summary

- Gewijzigd:
  - `frontend/src/pages/DigitalTwin.tsx` -- dark-mode retrofit + OODATimeline integratie
- Nieuw gebouwd:
  - `frontend/src/components/twin/OODATimeline.tsx` (zie FE-CMP-042)
  - `frontend/src/pages/__tests__/DigitalTwin.dark.test.tsx` -- 5 dark-mode tests
- Verwijderd: geen

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-027 | DigitalTwin | Page | `src/pages/DigitalTwin.tsx` | Wijziging (RF) | Digital Twin profiel bekijken |
| FE-CMP-042 | OODATimeline | Component | `src/components/twin/OODATimeline.tsx` | Nieuw | OODA fase tonen |

---

## Gebruikersflows

### Flow ID: FE-FLW-003

- Naam: Digital Twin profiel bekijken
- Startconditie: Gebruiker navigeert naar /digital-twin.
- Trigger: Pagina laadt.
- Hoofdstappen:
  1. Pagina toont laadspinner op donkere achtergrond.
  2. Profiel en OODA metrics worden opgehaald via API.
  3. Pagina toont: Profile Overview kaart, GDPR Consent kaart, OODA Analyse kaart, Data Portability kaart.
  4. SyncStateBadge toont huidige sync-status met `status-*` token kleur.
  5. OODATimeline toont de actieve OODA fase (MVP: Observe).
- Alternatief pad (error): API fout toont error banner.
- Succespad: Alle 4 kaarten zichtbaar en leesbaar in dark-mode.
- Foutpad: Error banner `bg-red-900/40 text-red-300` zichtbaar.
- Eindtoestand: Gebruiker kan profiel inzien en GDPR controls gebruiken.

---

## Detaildocumentatie per item

### [FE-PGS-027] DigitalTwin dark-mode retrofit

#### 1. Type

Bestaande page component (refactor).

#### 2. Locatie

`frontend/src/pages/DigitalTwin.tsx`

#### 3. Doel

Alle light-mode Tailwind klassen vervangen door ADR-028-conforme dark-mode equivalenten, zodat de pagina consistent is met het rest van het platform.

#### 4. Dark-mode mapping

| Oud | Nieuw |
|-----|-------|
| `bg-gradient-to-br from-slate-900 via-violet-900 to-slate-900` | `bg-slate-950` |
| `bg-white` | `bg-slate-900` |
| `border-gray-200` | `border-slate-800` |
| `text-gray-900` (headings) | `text-slate-100` |
| `text-gray-600`/`text-gray-500` (muted) | `text-slate-400` |
| `bg-green-100 text-green-800` (badge) | `bg-status-success/20 text-status-success` |
| `bg-amber-100 text-amber-800` (badge) | `bg-status-warning/20 text-status-warning` |
| `bg-gray-100 text-gray-700` (badge) | `bg-status-info/20 text-status-info` |
| `bg-gray-200` (progress track) | `bg-slate-800` |
| `text-violet-700 border-violet-300 hover:bg-violet-50` | `text-violet-400 border-violet-800 hover:bg-violet-950` |
| `text-red-700 border-red-300 hover:bg-red-50` | `text-red-400 border-red-800 hover:bg-red-950` |

#### 5. States en gedrag

- Loading: donkere spinner op `bg-slate-950`
- Loaded: 4 kaarten in `bg-slate-900` met `border-slate-800`
- Error: bestaande error banner (al donker: `bg-red-900/40`)
- Erasure modal: `bg-slate-950 border-slate-800`

#### 6. Acceptatiecriteria

- [x] Root container heeft class `bg-slate-950` in zowel loading als main state
- [x] Geen `bg-white` of `bg-green-100` etc. op pagina-niveau
- [x] SyncStateBadge SYNCHRONIZED gebruikt `bg-status-success/20 text-status-success`
- [x] OODATimeline is aanwezig in OODA kaart
- [x] `data-testid="twin-portability-card"` aanwezig
- [x] Alle bestaande functionaliteit (erasure, export, GDPR) werkt

#### 7. Trainingssamenvatting

- Actor: Ingelogde gebruiker met `twin:read` scope.
- Voorwaarde: DigitalTwin pagina geladen.
- Actie: Gebruiker bekijkt gedragsprofiel, OODA-analyse of GDPR-controls.
- Systeemreactie: Pagina toont dark-themed kaarten met status badges in `status-*` tokens.
- Succesrespons: Alle 4 secties zichtbaar en leesbaar.
- Foutrespons: Error banner toont foutmelding in donkerrode stijl.
- Uitzonderingen: Consent gate-logica (ADR-026) wordt gefinaliseerd in Dag 3.

---

## Open aannames

- `OODATimeline activePhase="Observe"` is MVP hardcode; echte fase-berekening volgt in Dag 3.
- Backend endpoints zijn functioneel ongewijzigd.

## Risico's

- Geen -- styling-only refactor. Bestaande tests (10/10) passen door.

---

## QA-checks

- [x] Functioneel getest (10 bestaande tests groen)
- [x] Dark-mode tests geschreven en groen (5 nieuwe tests)
- [x] Type-check: 0 errors
- [x] ESLint: 0 errors, 0 warnings
- [ ] Cross-browser gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle interactieve elementen zijn geinventariseerd
- [x] Alle relevante states zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Trainingssamenvatting is aanwezig
- [x] Review door reviewer-prompt: APPROVED
