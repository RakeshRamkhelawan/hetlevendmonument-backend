# Frontend Feature Specification

## Metadata

- Feature ID: FE-CMP-041
- Feature naam: ConsentToggle
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 1
- Reviewer: reviewer-prompt
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces
- Gerelateerde pagina / route: /digital-twin (Dag 3)
- Gerelateerde backend endpoints:
  - GET /api/v1/twin/profile (via useDigitalTwinProfile hook)
  - POST /api/v1/twin/consent
- Gerelateerde design componenten: AlertDialog, status badge tokens
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een herbruikbare dark-mode component waarmee een gebruiker zijn Digital Twin consent status kan inzien en wijzigen: actief intrekken (revoke) of opnieuw activeren (grant). Revoke is een destructieve actie die via een Radix AlertDialog bevestigd moet worden.

### In scope

- Nieuw component `ConsentToggle` in `frontend/src/components/twin/ConsentToggle.tsx`.
- Nieuwe hook `useDigitalTwinProfile` in `frontend/src/hooks/useDigitalTwinProfile.ts`.
- Scope uitbreiding in `frontend/src/lib/stores/authStore.ts`: `twin:read` volgt `noun:verb` conventie.
- Status badges voor `active`, `revoked` en `pending`.
- Revoke-bevestiging via Radix AlertDialog.
- Mutatie POST /api/v1/twin/consent en invalidatie van de twin profile query.
- ADR-028 compliance: dark theme, geen inline styles.

### Out of scope

- `DigitalTwin.tsx` page retrofit (Dag 2).
- `OODATimeline` component (Dag 2).
- `TraceViewerPage`, `useTraceSteps`, `TraceStepList` (Dag 3).
- Route wiring `/digital-twin` en backend scope registratie (Dag 3).
- Verwerken van de daadwerkelijke backend response structuur buiten `{ consent_status }`.

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/components/twin/ConsentToggle.tsx`
  - `frontend/src/hooks/useDigitalTwinProfile.ts`
  - `frontend/src/components/twin/__tests__/ConsentToggle.test.tsx`
  - `frontend/src/hooks/__tests__/useDigitalTwinProfile.test.ts`
- Gewijzigd:
  - `frontend/src/lib/stores/authStore.ts` — `OAuth2Scope` union uitgebreid met `twin:read`.
- Verwijderd: geen.
- Beinvloede bestaande flows: geen (component nog niet op een pagina gemonteerd).

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-CMP-041 | ConsentToggle | Component | `src/components/twin/ConsentToggle.tsx` | Nieuw | Consent wijzigen |
| (geen) | useDigitalTwinProfile | Hook | `src/hooks/useDigitalTwinProfile.ts` | Nieuw | Profiel ophalen |

---

## Gebruikersflows

### Flow ID: FE-FLW-001

- Naam: Digital Twin consent wijzigen
- Startconditie: Gebruiker is ingelogd en heeft `twin:read` scope.
- Trigger: Gebruiker opent de DigitalTwin pagina en ziet de ConsentToggle.
- Hoofdstappen:
  1. Systeem toont huidige consent status als badge (Active / Paused / Pending).
  2. Bij `active`: gebruiker klikt op "Revoke".
  3. Systeem toont een AlertDialog met waarschuwing.
  4. Gebruiker bevestigt revoke.
  5. Systeem POST naar `/api/v1/twin/consent` met `{ action: 'revoke' }`.
  6. Systeem invalidatieert de twin profile query.
  7. Badge wijzigt naar "Paused".
- Alternatief pad (grant): bij `revoked` klikt gebruiker op "Reactivate"; systeem POST `{ action: 'grant' }` zonder dialog.
- Succespad: Badge toont nieuwe status; query is geinvalidatieerd.
- Foutpad: Mutatie faalt; badge blijft ongewijzigd; applicatie toont eventueel een foutmelding.
- Eindtoestand: Consent status in UI en cache is consistent met backend.

---

## Detaildocumentatie per item

---

## [FE-CMP-041] ConsentToggle

### 1. Type

Herbruikbare React component.

### 2. Locatie

`frontend/src/components/twin/ConsentToggle.tsx`

### 3. Gerelateerde flow

FE-FLW-001 — Digital Twin consent wijzigen.

### 4. Doel

Toon de huidige Digital Twin consent status en biedt knoppen om deze te wijzigen, met een destructieve-bevestiging voor revoke.

### 5. Functionele beschrijving

De component toont een kaart met een status badge (Active / Paused / Pending) en een label "Twin data consent". Afhankelijk van de status toont de component een "Revoke" knop (alleen bij active) of een "Reactivate" knop (alleen bij revoked). Bij pending zijn er geen actieknoppen. Klikken op Revoke opent een Radix AlertDialog die waarschuwt dat de actie onomkeerbaar is.

### 6. Technische beschrijving

- Props: `{ consentStatus: 'active' | 'revoked' | 'pending' }`.
- Interne state: `isOpen` voor de AlertDialog.
- `useMutation` POST naar `/api/v1/twin/consent` met body `{ action: 'grant' | 'revoke' }`.
- `onSuccess` invalidatieert `TWIN_PROFILE_QUERY_KEY` via `useQueryClient().invalidateQueries`.
- Named export `ConsentToggle`.
- Gebruikt de project AlertDialog wrapper uit `@/components/ui/alert-dialog`.

### 7. Zichtbaarheidsregels

- Revoke knop: alleen zichtbaar bij `consentStatus === 'active'`.
- Reactivate knop: alleen zichtbaar bij `consentStatus === 'revoked'`.
- AlertDialog: alleen zichtbaar nadat de gebruiker op Revoke heeft geklikt.

### 8. States en gedrag

- Default: badge toont huidige status, actieknop indien van toepassing.
- Hover: knoppen krijgen een lichte achtergrondtint.
- Loading: `useMutation` isPending; knoppen worden niet expliciet disabled, maar mutatie kan niet parallel starten.
- Error: mutatie error wordt niet intern getoond; parent pagina is verantwoordelijk.
- Dialog open: achtergrond is gedimd; focus zit in de dialog.
- Dialog confirm: POST wordt uitgevoerd; dialog sluit bij success.

### 9. Input

- `consentStatus` prop.
- Backend endpoint `/api/v1/twin/consent`.
- QueryClient van parent tree (vereist voor invalidatie).

### 10. Output

- Visuele weergave van status + actieknoppen.
- POST request naar consent endpoint.
- Invalidatie van twin profile query.

### 11. Validaties

- Geen formulier-validatie; alleen status-driven rendering.

### 12. Business rules

- Revoke is alleen mogelijk vanuit `active`.
- Grant (reactivate) is alleen mogelijk vanuit `revoked`.
- Pending toont geen acties.
- `twin:read` scope is vereist op pagina-niveau; de component zelf doet geen scope-check.

### 13. Afhankelijkheden

- `@tanstack/react-query`
- `@/lib/api/client` (`api`)
- `@/hooks/useDigitalTwinProfile` (`TWIN_PROFILE_QUERY_KEY`)
- `@/components/ui/alert-dialog`
- `@/lib/utils` (`cn`)

### 14. Foutafhandeling

- Mutatie error wordt door `useMutation` teruggegeven; parent kan deze tonen.
- Component toont badge ongewijzigd bij fout.

### 15. Telemetry / logging / analytics

- Geen telemetry toegevoegd.

### 16. Accessibility-notities

- Status badge heeft `data-testid="consent-status-badge"`.
- Revoke knop heeft `aria-label="Revoke consent"`.
- Reactivate knop heeft `aria-label="Reactivate consent"`.
- AlertDialog gebruikt Radix primitives: focus trap, `role="alertdialog"`, ESC sluit dialog.

### 17. Acceptatiecriteria

- [ ] Component rendert zonder crash.
- [ ] Badge toont "Active" bij active, "Paused" bij revoked, "Pending" bij pending.
- [ ] Revoke knop is alleen zichtbaar bij active.
- [ ] Reactivate knop is alleen zichtbaar bij revoked.
- [ ] Klikken op Revoke opent AlertDialog.
- [ ] Bevestigen in dialog roept POST `/api/v1/twin/consent` met `{ action: 'revoke' }`.
- [ ] Klikken op Reactivate roept POST `/api/v1/twin/consent` met `{ action: 'grant' }`.
- [ ] Na succesvolle mutatie wordt `['twin', 'profile']` query geinvalidatieerd.
- [ ] Geen inline styles in de gerenderde output.

### 18. Gebruikersuitleg

- De ConsentToggle toont of je Digital Twin data toegang actief is.
- Klik op "Revoke" om toegang in te trekken. Je moet dit bevestigen in een dialog.
- Klik op "Reactivate" om toegang opnieuw toe te staan.
- Bij "Pending" zijn er nog geen acties beschikbaar.

### 19. Trainingssamenvatting

- Actor: Ingelogde gebruiker met `twin:read` scope.
- Voorwaarde: DigitalTwin pagina is geladen; consent_status is zichtbaar.
- Actie: Gebruiker klikt op "Revoke" of "Reactivate".
- Systeemreactie: AlertDialog (revoke) of directe POST (grant); na success wordt de twin profile query geinvalidatieerd.
- Succesrespons: Badge toont de nieuwe consent_status.
- Foutrespons: Badge blijft ongewijzigd; parent toont eventueel een foutmelding.
- Uitzonderingen: Bij `pending` zijn er geen knoppen zichtbaar.

---

## [useDigitalTwinProfile] Hook

### 1. Type

React hook (TanStack Query `useQuery` wrapper).

### 2. Locatie

`frontend/src/hooks/useDigitalTwinProfile.ts`

### 3. Gerelateerde flow

FE-FLW-001.

### 4. Doel

Ophalen van het Digital Twin profiel inclusief consent_status.

### 5. Functionele beschrijving

De hook haalt het profiel op via GET `/api/v1/twin/profile`. Hij retourneert loading, error en data states. Een optionele `enabled` parameter kan het automatisch ophalen uitschakelen.

### 6. Technische beschrijving

- Exporteert `TWIN_PROFILE_QUERY_KEY = ['twin', 'profile']`.
- `useQuery<DigitalTwinProfile, Error>` met `staleTime: 5 * 60_000`.
- `queryFn` unwrapt `{ data }` uit `api.get`.
- `enabled` default true.

### 7. Afhankelijkheden

- `@tanstack/react-query`
- `@/lib/api/client` (`api`)

### 8. Acceptatiecriteria

- [ ] Hook retourneert loading state bij initieel laden.
- [ ] Hook retourneert profiel data bij success.
- [ ] Hook retourneert error state bij API fout.
- [ ] Hook doet geen request als `enabled: false`.

---

## Handleidingstekst

### Voor eindgebruikers

**Digital Twin consent**

Je kunt zelf bepalen of je Digital Twin profiel actief mag zijn.

1. Open de Digital Twin pagina.
2. Kijk bij "Twin data consent" naar de status:
   - **Active** — je profiel wordt bijgehouden.
   - **Paused** — je profiel is uitgeschakeld.
   - **Pending** — de status wordt nog bepaald.
3. Klik op "Revoke" om je toestemming in te trekken. Bevestig dit in de dialog.
4. Klik op "Reactivate" om je toestemming opnieuw te geven.

---

## Open aannames

- Backend endpoint `GET /api/v1/twin/profile` retourneert een `DigitalTwinProfile` object.
- Backend endpoint `POST /api/v1/twin/consent` accepteert `{ action: 'grant' | 'revoke' }`.
- `twin:read` scope wordt op Dag 3 geregistreerd in de backend.
- De `ConsentToggle` wordt pas op Dag 2/3 in de DigitalTwin pagina gemonteerd.

## Open vragen

- Moet de grant-actie ook een bevestigingsdialog krijgen? (Huidige implementatie: nee.)
- Wat is het exacte foutformaat van `/api/v1/twin/consent`? (Niet nodig voor vandaag.)

## Risico's

- **Endpoint mismatch:** als de backend andere veldnamen of status-waarden gebruikt, moet de hook/interface aangepast worden.
- **Scope registratie:** `twin:read` is nu frontend-only; zonder backend registratie werkt PermissionGate niet voor echte gebruikers.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [x] Error states getest
- [x] Mutatie + invalidatie getest
- [x] Accessibility gecontroleerd (aria-labels, AlertDialog)
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
