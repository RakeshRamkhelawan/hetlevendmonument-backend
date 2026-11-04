# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-022
- Feature naam: HITLQueue redesign swap (/hitl)
- Status: Implemented
- Auteur: SP-FE-2E Dag 1
- Reviewer: Code + Quality Review
- Datum: 2026-07-02
- Gerelateerde user story / ticket: SP-FE-2E — ToolBrokerRegistry + HITLQueue + ToolAuditLogs route wiring
- Gerelateerde pagina / route: /hitl
- Gerelateerde backend endpoints: POST /api/v1/hitl/{id}/decide
- Gerelateerde design componenten: HITLQueue, HITLDecisionForm, PermissionGate, ClassificationWrapper
- Versie: 1.0

---

## Doel en scope

### Doel

Vervangen van de legacy `HITLPage` op `/hitl` door de redesign `HITLQueue`, met scope-gating voor queue-weergave (`compliance:read`) en beslissingen (`compliance:manage`).

### In scope

- Swap `/hitl` route naar `<HITLQueueRedesign />` in `App.tsx`.
- Toevoegen van "HITL Queue" nav item in `BusinessSidebar`.
- Vervangen van `api` door `apiClient` in `HITLQueue.tsx`.
- Wrappen van `HITLQueue` in `PermissionGate requiredScope="compliance:read" showOverlay`.
- Wrappen van het beslissingsformulier in `PermissionGate requiredScope="compliance:manage"`.
- Wrappen van het counter-proposal veld in `ClassificationWrapper classification="confidential"`.
- Uitbreiden van `HITLQueue.test.tsx` met scope-gate scenario's.

### Out of scope

- Verwijderen van de legacy `HITLPage` component (kan elders nog gebruikt worden).
- Toevoegen van live polling/fetch voor de queue (bestaande store-based data blijft).

---

## Build summary

- Nieuw gebouwd: `/hitl` route naar redesign, `BusinessSidebar` nav link.
- Gewijzigd: `App.tsx`, `BusinessSidebar.tsx`, `HITLQueue.tsx`, `HITLDecisionForm.tsx`, `HITLQueue.test.tsx`.
- Verwijderd: legacy `HITLPage` import in `App.tsx`.
- Beinvloede bestaande flows: HITL goedkeuringsworkflow.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-022 | /hitl route swap | Route | App.tsx | Wijziging | HITL goedkeuring |
| FE-PGS-022-NAV | HITL Queue nav item | Navigatie | BusinessSidebar.tsx | Nieuw | HITL goedkeuring |
| FE-PGS-022-VIEW | Queue view scope gate | PermissionGate | HITLQueue.tsx | Wijziging | HITL queue inzien |
| FE-PGS-022-DEC | Decision form scope gate | PermissionGate | HITLQueue.tsx | Wijziging | HITL beslissing nemen |
| FE-PGS-022-CLS | Counter-proposal classification | ClassificationWrapper | HITLDecisionForm.tsx | Wijziging | HITL beslissing nemen |

---

## Gebruikersflows

### Flow ID: FE-FLW-022-001

- Naam: HITL escalatie goedkeuren via redesign queue
- Startconditie: Gebruiker is ingelogd en heeft `compliance:read` scope.
- Trigger: Gebruiker klikt op "HITL Queue" in de sidebar.
- Hoofdstappen:
  1. App navigeert naar `/hitl` en laadt `HITLQueue` lazy.
  2. Gebruiker ziet pending escalaties gesorteerd op SLA.
  3. Gebruiker selecteert een item.
  4. Indien `compliance:manage`, toont het beslissingsformulier.
  5. Gebruiker geeft een toelichting van minimaal 10 tekens en keurt goed/af.
- Succespad: Status wijzigt, toast verschijnt, item verdwijnt uit pending.
- Foutpad: API-fout toont fout-toast zonder statuswijziging.
- Eindtoestand: Escalatie is APPROVED of REJECTED.

---

## Detaildocumentatie per item

---

## [FE-PGS-022] /hitl route swap

### 1. Type

Route + lazy-loaded page component.

### 2. Locatie

`frontend/src/App.tsx`.

### 3. Gerelateerde flow

FE-FLW-022-001.

### 4. Doel

De redesign HITLQueue beschikbaar maken op `/hitl` in plaats van de legacy `HITLPage`.

### 5. Functionele beschrijving

Gebruiker navigeert naar `/hitl` en ziet de redesign HITL-wachtrij met statusfilters, SLA-timers en een beslissingsformulier.

### 6. Technische beschrijving

```tsx
const HITLQueueRedesign = React.lazy(() => import('./pages/redesign/HITLQueue'));
```

Route is gewrapped in `ProtectedRoute` en `LazyWrapper`. `HITLQueue` gebruikt `apiClient` voor `POST /api/v1/hitl/{id}/decide`.

### 7. Zichtbaarheidsregels

- `compliance:read` is vereist voor de hele pagina (overlay bij ontbreekt).
- `compliance:manage` is vereist voor het beslissingsformulier.

### 8. States en gedrag

- Default: lazy laadt de pagina.
- Loading: `LazyWrapper` fallback.
- Empty: "Geen escalaties in deze categorie.".
- Permission denied: overlay of verborgen formulier.

### 9. Input

- URL: `/hitl`.
- Store state: `hitlQueue`.

### 10. Output

- Gerenderde HITLQueue.

### 11. Validaties

- Toelichting minimaal 10 tekens.
- Alleen PENDING items kunnen worden goedgekeurd/afgewezen.

### 12. Business rules

- Beslissingen worden cryptografisch vastgelegd op de backend.
- SLA-timers worden berekend vanuit `slaExpiresAt - Date.now()`.

### 13. Afhankelijkheden

- `HITLQueue.tsx`, `HITLDecisionForm.tsx`, `useIntegrationsStore`, `apiClient`, `PermissionGate`, `ClassificationWrapper`.

### 14. Foutafhandeling

- API-fout toont toast en rolt geen store-update uit.

### 15. Telemetry / logging / analytics

- Geen nieuwe telemetry.

### 16. Accessibility-notities

- Sidebar link heeft zichtbaar label.
- Queue items zijn buttons met `aria-current`.

### 17. Acceptatiecriteria

- `/hitl` rendert de redesign `HITLQueue`.
- Pagina is alleen zichtbaar met `compliance:read`.
- Beslissingsformulier is alleen zichtbaar met `compliance:manage`.
- Toelichting van < 10 tekens deactiveert de knoppen.

### 18. Gebruikersuitleg

- Open "HITL Queue" in het menu.
- Selecteer een escalatie om de details te zien.
- Vul een toelichting in en kies Goedkeuren of Afwijzen.
- Zonder beheerrechten zie je de queue maar kun je geen beslissing nemen.

### 19. Trainingssamenvatting

- Actor: Compliance gebruiker met `compliance:read` of `compliance:manage` scope.
- Voorwaarde: Er zijn pending HITL-escalaties.
- Actie: Navigeer naar `/hitl`, selecteer een item, vul toelichting in en klik op Goedkeuren/Afwijzen.
- Systeemreactie: API-call naar `/api/v1/hitl/{id}/decide`; store-status wijzigt; toast wordt getoond.
- Succesrespons: Item-status wordt APPROVED/REJECTED.
- Foutrespons: Toast "Kon beslissing niet opslaan. Probeer het opnieuw."
- Uitzonderingen: Gebruiker zonder `compliance:manage` ziet geen formulier; niet-PENDING items zijn niet meer beslisbaar.

---

## Handleidingstekst

### Voor eindgebruikers

- De HITL Queue toont alle escalaties die een menselijke beslissing vereisen.
- Items met een rode, pulserende timer hebben een SLA die bijna verloopt.
- Je hebt `compliance:manage` rechten nodig om een beslissing te nemen.
- Een counter-voorstel kun je als JSON invoeren; dit veld wordt als vertrouwelijk gemarkeerd.

---

## Open aannames

- Legacy `HITLPage` wordt niet verwijderd in deze sprint.

## Open vragen

- Moet `/hitl` live polling krijgen of blijft de huidige store-gebaseerde data voldoen?

## Risico's

- Gebruikers die gewend zijn aan de oude `/hitl` layout zien een nieuwe interface.

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
