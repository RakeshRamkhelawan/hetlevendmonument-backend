# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-023
- Feature naam: ToolAuditLogs route wiring (/tool-audit-logs)
- Status: Implemented
- Auteur: SP-FE-2E Dag 1
- Reviewer: Code + Quality Review
- Datum: 2026-07-02
- Gerelateerde user story / ticket: SP-FE-2E — ToolBrokerRegistry + HITLQueue + ToolAuditLogs route wiring
- Gerelateerde pagina / route: /tool-audit-logs
- Gerelateerde backend endpoints: Geen nieuwe endpoint (client-side filtered store data)
- Gerelateerde design componenten: ToolAuditLogs, ToolExecutionDetails
- Versie: 1.0

---

## Doel en scope

### Doel

Maken van een beschermde, lazy-loaded route `/tool-audit-logs` voor de Tool Audit Logs redesign-pagina, inclusief deep-linking via `?tool={name}` en alarm bij een error rate boven 5%.

### In scope

- Toevoegen van lazy import `ToolAuditLogs` in `App.tsx`.
- Toevoegen van `/tool-audit-logs` route binnen `ProtectedRoute` + `LazyWrapper`.
- Toevoegen van "Audit Logs" nav item in `BusinessSidebar`.
- Aanpassen van `ERROR_RATE_THRESHOLD` van 15 naar 5 procent.
- Toevoegen van `useSearchParams` ondersteuning voor `?tool=` query parameter.
- Uitbreiden van `ToolAuditLogs.test.tsx` met query-param test.

### Out of scope

- Backend endpoint voor aggregatie van error rates.
- Link vanuit ToolBrokerRegistry naar `/tool-audit-logs?tool=...`.

---

## Build summary

- Nieuw gebouwd: `/tool-audit-logs` route, `BusinessSidebar` nav link.
- Gewijzigd: `App.tsx`, `BusinessSidebar.tsx`, `ToolAuditLogs.tsx`, `ToolAuditLogs.test.tsx`.
- Verwijderd: n.v.t.
- Beinvloede bestaande flows: Audit / observability van tool-executies.

---

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-PGS-023 | /tool-audit-logs route | Route | App.tsx | Nieuw | Tool audit bekijken |
| FE-PGS-023-NAV | Audit Logs nav item | Navigatie | BusinessSidebar.tsx | Nieuw | Tool audit bekijken |
| FE-PGS-023-ALARM | Error rate alarm banner | Banner | ToolAuditLogs.tsx | Wijziging | Tool audit bekijken |
| FE-PGS-023-DEEP | ?tool= deep link | Query param | ToolAuditLogs.tsx | Nieuw | Tool audit bekijken |

---

## Gebruikersflows

### Flow ID: FE-FLW-023-001

- Naam: Audit logs bekijken via navigatie
- Startconditie: Gebruiker is ingelogd.
- Trigger: Gebruiker klikt op "Audit Logs" in de sidebar.
- Hoofdstappen:
  1. App navigeert naar `/tool-audit-logs`.
  2. Pagina toont statusfilters, error-rate banner, zoekveld en logtabel.
  3. Gebruiker filtert op status of zoekt op tool/agent.
- Succespad: Logtabel toont gefilterde resultaten.
- Foutpad: Geen toegang zonder login.
- Eindtoestand: Gewenste audit logs zijn zichtbaar.

### Flow ID: FE-FLW-023-002

- Naam: Deep link naar logs van een specifieke tool
- Startconditie: Gebruiker opent `/tool-audit-logs?tool=sql-query`.
- Trigger: URL bevat `tool` query parameter.
- Hoofdstappen:
  1. Component leest `tool` parameter.
  2. Zoekveld wordt gevuld met de tool naam.
  3. Debounced store query wordt bijgewerkt.
- Succespad: Logtabel toont alleen logs voor die tool.
- Foutpad: Geen logs → empty state.
- Eindtoestand: Gefilterde logs voor de tool zijn zichtbaar.

---

## Detaildocumentatie per item

---

## [FE-PGS-023] /tool-audit-logs route

### 1. Type

Route + lazy-loaded page component.

### 2. Locatie

`frontend/src/App.tsx`.

### 3. Gerelateerde flow

FE-FLW-023-001, FE-FLW-023-002.

### 4. Doel

Beschikbaar maken van de redesign Tool Audit Logs pagina op een canonical URL.

### 5. Functionele beschrijving

Gebruiker navigeert naar `/tool-audit-logs` en ziet een overzicht van tool-executies met filters, zoeken, paginering en een detailpaneel.

### 6. Technische beschrijving

```tsx
const ToolAuditLogs = React.lazy(() => import('./pages/redesign/ToolAuditLogs'));
```

Route is gewrapped in `ProtectedRoute` en `LazyWrapper`. Error rate wordt client-side berekend over `auditLogs`.

### 7. Zichtbaarheidsregels

- Vereist ingelogde gebruiker.
- Error-rate alarm banner wordt zichtbaar bij error rate > 5%.

### 8. States en gedrag

- Default: lazy laadt de pagina.
- Loading: `LazyWrapper` fallback.
- Empty: "Geen logvermeldingen gevonden.".
- Alarm: rode banner met `[ALARM]` tekst.

### 9. Input

- URL: `/tool-audit-logs` of `/tool-audit-logs?tool={name}`.
- Store state: `auditLogs`, `auditQuery`, `selectedAuditEntry`.

### 10. Output

- Gerenderde Tool Audit Logs.

### 11. Validaties

- `ProtectedRoute` valideert authenticatie.

### 12. Business rules

- Error rate > 5% toont een alarm banner.
- Filters zijn client-side.

### 13. Afhankelijkheden

- `ToolAuditLogs.tsx`, `ToolExecutionDetails.tsx`, `useIntegrationsStore`, `useSearchParams`.

### 14. Foutafhandeling

- Geen specifieke nieuwe foutafhandeling.

### 15. Telemetry / logging / analytics

- Geen nieuwe telemetry.

### 16. Accessibility-notities

- Alarm banner heeft `role="alert"` en `aria-live="polite"`.
- Sidebar link heeft zichtbaar label.

### 17. Acceptatiecriteria

- `/tool-audit-logs` rendert de redesign Tool Audit Logs.
- Route is beschermd door `ProtectedRoute`.
- Sidebar bevat een werkende link naar `/tool-audit-logs`.
- Error rate alarm verschijnt bij > 5% failed logs.
- `?tool=` vult het zoekveld en werkt de store query bij.

### 18. Gebruikersuitleg

- Open "Audit Logs" in het menu.
- Gebruik de statusfilters of het zoekveld om logs te doorzoeken.
- Klik op een rij om details van de payload en eventuele foutmelding te zien.
- Een rode banner waarschuwt als meer dan 5% van de recente uitvoeringen is mislukt.

### 19. Trainingssamenvatting

- Actor: Ingelogde gebruiker.
- Voorwaarde: Gebruiker bevindt zich in de business UI.
- Actie: Klik op "Audit Logs" in de sidebar of open `/tool-audit-logs?tool={name}`.
- Systeemreactie: App navigeert naar `/tool-audit-logs`, laadt Tool Audit Logs en vult eventueel het zoekveld.
- Succesrespons: Logtabel toont gefilterde logs; detailpaneel toont payload bij selectie.
- Foutrespons: Niet-ingelogde gebruiker wordt naar login doorgestuurd.
- Uitzonderingen: Geen logs voor de zoekterm toont de empty state.

---

## Handleidingstekst

### Voor eindgebruikers

- Audit Logs tonen alle tool-uitvoeringen van AI-agents.
- Je kunt filteren op status (SUCCESS / FAILED) of zoeken op tool- of agentnaam.
- Een rood alarm betekent dat meer dan 5% van de uitvoeringen mislukt; controleer dan de integratie.
- Klik op een rij om de payload en eventuele foutmelding uit te klappen.

---

## Open aannames

- Error-rate threshold van 5% is de gewenste business drempel.

## Open vragen

- Moet de error-rate threshold per tenant configureerbaar zijn?

## Risico's

- Client-side error rate kan afwijken van backend-metrices als de lijst gepagineerd of beperkt is.

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
