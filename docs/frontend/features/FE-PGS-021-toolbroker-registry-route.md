# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-021
- Feature naam: ToolBrokerRegistry route wiring (/tools)
- Status: Implemented
- Auteur: SP-FE-2E Dag 1
- Reviewer: Code + Quality Review
- Datum: 2026-07-02
- Gerelateerde user story / ticket: SP-FE-2E — ToolBrokerRegistry + HITLQueue + ToolAuditLogs route wiring
- Gerelateerde pagina / route: /tools
- Gerelateerde backend endpoints: POST /api/v1/tools/{id}/toggle
- Gerelateerde design componenten: ToolBrokerCard, PermissionGate, Switch
- Versie: 1.0

---

## Doel en scope

### Doel

Maken van een beschermde, lazy-loaded route `/tools` die de redesign-versie van het Tool Broker Registry toont, plus een sidebar-navigatie-link. De tool-toggle wordt beveiligd met de `agents:manage` scope.

### In scope

- Toevoegen van lazy import `ToolBrokerRegistry` in `App.tsx`.
- Toevoegen van `/tools` route binnen `ProtectedRoute` + `LazyWrapper`.
- Toevoegen van "Tool Broker" nav item in `BusinessSidebar`.
- Vervangen van `api` door `apiClient` in `ToolBrokerRegistry.tsx`.
- Wrappen van de tool-toggle `Switch` in `ToolBrokerCard.tsx` met `PermissionGate requiredScope="agents:manage"`.
- Uitbreiden van `ToolBrokerRegistry.test.tsx` met PermissionGate-scenario's.

### Out of scope

- Wijzigen van de legacy `/tool-broker` route.
- Backend-wijzigingen aan de tool-toggle endpoint.
- Volledige live data fetch/polling voor de tool-lijst (blijft op bestaande Zustand-store).

---

## Build summary

- Nieuw gebouwd: `/tools` route, `BusinessSidebar` nav link.
- Gewijzigd: `App.tsx`, `BusinessSidebar.tsx`, `ToolBrokerRegistry.tsx`, `ToolBrokerCard.tsx`, `ToolBrokerRegistry.test.tsx`.
- Verwijderd: `HITLPage` import in `App.tsx` (alleen nog gebruikt op `/hitl` nu redesign).
- Beinvloede bestaande flows: Business navigatie, tool allowlist beheer.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-021 | /tools route | Route | App.tsx | Nieuw | Tool Broker beheer |
| FE-PGS-021-NAV | Tool Broker nav item | Navigatie | BusinessSidebar.tsx | Nieuw | Tool Broker beheer |
| FE-PGS-021-TOG | Tool toggle scope gate | PermissionGate | ToolBrokerCard.tsx | Wijziging | Tool allowlist wijzigen |

---

## Gebruikersflows

### Flow ID: FE-FLW-021-001

- Naam: Navigeren naar Tool Broker Registry
- Startconditie: Gebruiker is ingelogd en heeft de business sidebar zichtbaar.
- Trigger: Gebruiker klikt op "Tool Broker" in de sidebar.
- Hoofdstappen:
  1. Sidebar link `/tools` wordt geactiveerd.
  2. App laadt `ToolBrokerRegistry` lazy binnen `ProtectedRoute`.
  3. Pagina toont tool-lijst met risk-tier filters.
- Succespad: Gebruiker ziet tools en kan (met juiste scope) togglen.
- Foutpad: Geen toegang tot route als niet ingelogd.
- Eindtoestand: Tool Broker Registry is zichtbaar.

---

## Detaildocumentatie per item

---

## [FE-PGS-021] /tools route

### 1. Type

Route + lazy-loaded page component.

### 2. Locatie

`frontend/src/App.tsx` (regel toegevoegd na CouncilDashboard lazy import).

### 3. Gerelateerde flow

FE-FLW-021-001.

### 4. Doel

Beschikbaar maken van de redesign Tool Broker Registry op een canonical URL.

### 5. Functionele beschrijving

Gebruiker navigeert naar `/tools` en ziet de redesign Tool Broker Registry met linker filterpanel, centrale kaartenlijst en rechter detailpaneel.

### 6. Technische beschrijving

```tsx
const ToolBrokerRegistry = React.lazy(() => import('./pages/redesign/ToolBrokerRegistry'));
```

Route is gewrapped in `ProtectedRoute` en `LazyWrapper`. Component importeert `apiClient` (niet `api`) voor `POST /api/v1/tools/{id}/toggle`.

### 7. Zichtbaarheidsregels

- Vereist ingelogde gebruiker (`ProtectedRoute`).
- Tool toggle is alleen zichtbaar bij scope `agents:manage`.

### 8. States en gedrag

- Default: lazy laadt de pagina.
- Loading: `LazyWrapper` toont fallback.
- Error: route-level error boundary.
- Permission denied: toggle wordt verborgen.

### 9. Input

- URL: `/tools`.
- Store state: `tools`, `pendingToolIds`.

### 10. Output

- Gerenderde Tool Broker Registry.

### 11. Validaties

- `ProtectedRoute` valideert authenticatie.

### 12. Business rules

- HIGH/CRITICAL tools vereisen een extra "ALLOW" bevestiging.

### 13. Afhankelijkheden

- `ToolBrokerRegistry.tsx`, `ToolBrokerCard.tsx`, `useIntegrationsStore`, `apiClient`.

### 14. Foutafhandeling

- API-fout bij toggle rolt de optimistische update terug en toont toast.

### 15. Telemetry / logging / analytics

- Geen nieuwe telemetry.

### 16. Accessibility-notities

- Sidebar link heeft zichtbaar label en `NavLink` active state.

### 17. Acceptatiecriteria

- `/tools` rendert de redesign Tool Broker Registry.
- Route is beschermd door `ProtectedRoute`.
- Sidebar bevat een werkende link naar `/tools`.
- Toggle is alleen zichtbaar met `agents:manage` scope.

### 18. Gebruikersuitleg

- Open de Tool Broker via de sidebar.
- Bekijk per tool de risk tier en huidige allowlist-status.
- Alleen gebruikers met beheerdersrechten voor agents kunnen tools in- of uitschakelen.

### 19. Trainingssamenvatting

- Actor: Ingelogde gebruiker met of zonder `agents:manage` scope.
- Voorwaarde: Gebruiker bevindt zich in de business UI en ziet de sidebar.
- Actie: Klik op "Tool Broker" in de sidebar.
- Systeemreactie: App navigeert naar `/tools` en laadt de Tool Broker Registry.
- Succesrespons: Tool-lijst, filters en detailpaneel zijn zichtbaar.
- Foutrespons: Niet-ingelogde gebruiker wordt naar login doorgestuurd.
- Uitzonderingen: Gebruiker zonder `agents:manage` ziet tools maar kan niet togglen.

---

## Handleidingstekst

### Voor eindgebruikers

- De Tool Broker bepaalt welke tools AI-agents mogen gebruiken.
- Ga naar "Tool Broker" in het linkermenu.
- Tools met een hogere risk tier vragen om extra bevestiging voordat ze worden ingeschakeld.
- Als je geen schakelaar ziet, heb je niet de juiste rechten om tools te wijzigen.

---

## Open aannames

- De legacy `/tool-broker` route blijft bestaan naast `/tools`.

## Open vragen

- Moet `/tool-broker` op termijn redirecten naar `/tools`?

## Risico's

- Dubbele route kan verwarrend zijn voor gebruikers die `/tool-broker` hebben gebookmarkt.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [x] Error states getest
- [x] Accessibility gecontroleerd
- [ ] Responsive gecontroleerd
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
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
