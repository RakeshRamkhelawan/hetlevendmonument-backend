# Frontend Feature Specification

## Metadata

- Feature ID: FE-CMP-042
- Feature naam: OODATimeline -- stateless 4-step OODA phase indicator
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 2
- Reviewer: reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces
- Gerelateerde pagina / route: /digital-twin (DigitalTwin.tsx)
- Gerelateerde backend endpoints: geen (stateless component)
- Gerelateerde design componenten: cn utility
- Versie: 1.0

---

## Doel en scope

### Doel

Herbruikbare, stateless component die de voortgang van de OODA-cyclus (Observe, Orient, Decide, Act) visueel toont als een horizontale step-indicator. Completed fasen krijgen een check-icoon; de actieve fase is highlighted; toekomstige fasen zijn gedimd.

### In scope

- `frontend/src/components/twin/OODATimeline.tsx` -- nieuw component
- `frontend/src/components/twin/__tests__/OODATimeline.test.tsx` -- 5 tests

### Out of scope

- Koppeling met backend OODA-metrics (Dag 3)
- Animaties of transitions tussen fasen
- Klikbare stappen (navigatie is geen vereiste)

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/components/twin/OODATimeline.tsx`
  - `frontend/src/components/twin/__tests__/OODATimeline.test.tsx`
- Type conflict opgelost: component exporteert `OODATimelinePhase` (Title Case) om botsing met domain type `OODAPhase` (UPPERCASE) in `@/types/digitalTwin` te vermijden.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-CMP-042 | OODATimeline | Component | `src/components/twin/OODATimeline.tsx` | Nieuw | OODA fase tonen |

---

## Detaildocumentatie per item

### [FE-CMP-042] OODATimeline

#### 1. Type

Herbruikbare, stateless React component.

#### 2. Locatie

`frontend/src/components/twin/OODATimeline.tsx`

#### 3. Doel

Toon de 4 OODA-fasen als een horizontale reeks pills. Completed fasen (voor activePhase) krijgen een checkmark; de actieve fase is violet highlighted; toekomstige fasen zijn gedimd.

#### 4. Interface

```typescript
export type OODATimelinePhase = 'Observe' | 'Orient' | 'Decide' | 'Act';

interface OODATimelineProps {
  activePhase: OODATimelinePhase;
}
```

#### 5. Visuele toestanden

| Toestand | Klassen |
|----------|---------|
| Completed | `text-slate-300 bg-slate-800` + SVG check |
| Active | `text-violet-400 bg-violet-900/40 ring-1 ring-violet-500` + `aria-current="step"` |
| Pending | `text-slate-600 bg-slate-900` |

#### 6. Toegankelijkheid

- Root: `role="list"` op `<ol>`
- Per fase: `role="listitem"` op `<li>`
- Actieve fase: `aria-current="step"`
- Completed fasen: `data-completed="true"`
- SVG check: `aria-hidden="true"`

#### 7. Fallback

Onbekende `activePhase` (alleen runtime, TypeScript vangt dit op) → index 0 (`Observe`) wordt actief.

#### 8. Beperkingen

- Geen `useState`, `useEffect`, of API calls -- puur prop-driven.
- Fase-namen zijn exact: `"Observe"`, `"Orient"`, `"Decide"`, `"Act"` (ADR-025).

#### 9. Acceptatiecriteria

- [x] Rendert alle 4 fasen
- [x] Active fase heeft `aria-current="step"`
- [x] Completed fasen voor active hebben `data-completed="true"`
- [x] Prop-change werkt correct (stateless verificatie)
- [x] `role="list"` en 4 `role="listitem"` aanwezig

#### 10. Trainingssamenvatting

- Actor: Gebruiker op DigitalTwin pagina.
- Voorwaarde: OODATimeline gemonteerd met een geldige `activePhase` prop.
- Actie: Gebruiker bekijkt de OODA-cyclus indicator.
- Systeemreactie: 4 fasen zichtbaar; de actieve fase is violet highlighted; eerdere fasen hebben een checkmark.
- Succesrespons: Correct fase highlighted conform de doorgegeven prop.
- Foutrespons: Geen -- component is stateless; bij ongeldige prop: Observe als fallback.
- Uitzonderingen: In Dag 3 wordt `activePhase` dynamisch berekend vanuit backend OODA-metrics.

---

## Open aannames

- De prop `activePhase="Observe"` is in Dag 2 hardcoded in `DigitalTwin.tsx`; Dag 3 wiert de echte waarde.
- OODA fase-namen zijn altijd exact Title Case conform ADR-025.

## Risico's

- **Type naming conflict**: domein-type `OODAPhase` in `@/types/digitalTwin` gebruikt UPPERCASE values. Dit component gebruikt `OODATimelinePhase` om de namen-botsing te voorkomen.

---

## QA-checks

- [x] Functioneel getest (5 tests groen)
- [x] ARIA-structuur getest
- [x] Stateless gedrag getest (prop-change)
- [x] Type-check: 0 errors
- [x] ESLint: 0 errors, 0 warnings

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
