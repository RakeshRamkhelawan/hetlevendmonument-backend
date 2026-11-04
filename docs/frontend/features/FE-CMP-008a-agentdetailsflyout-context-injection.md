# Frontend Feature Specification

## Metadata

- Feature ID: FE-CMP-008a
- Feature naam: AgentDetailsFlyout ContextInjectionPanel integratie
- Status: Done
- Auteur: SP-FE-2D Dag 2
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-FE-2D -- ContextInjectionPanel integreren in AgentDetailsFlyout
- Gerelateerde pagina / route: AgentDetailsFlyout (slide-over in redesign)
- Gerelateerde backend endpoints: WebSocket `/api/v1/ws/agent-context`
- Gerelateerde design componenten: AgentDetailsFlyout, ContextInjectionPanel, ErrorBoundary
- Versie: 1.0

---

## Doel en scope

### Doel

De `ContextInjectionPanel` component beschikbaar maken in de Overview tab van `AgentDetailsFlyout`, zodat gebruikers agent-context kunnen monitoren zonder de pagina te verlaten.

### In scope

- Toevoegen van `ContextInjectionPanel` aan de Overview tab van `AgentDetailsFlyout`.
- Flex-layout aanpassing zodat het panel correct binnen de tab past.
- Eenvoudige `ErrorBoundary` rond het panel zodat een fout in het panel de flyout niet crasht.
- NOTE comment over WebSocket levenscyclus.
- Tests voor zichtbaarheid op Overview, afwezigheid op andere tabs, en foutafhandeling.

### Out of scope

- Wijzigingen aan `ContextInjectionPanel` zelf.
- Per-agent filtering van context (panel toont de globale agent-context stream).
- WebSocket hergebruik optimalisatie bij herhaald openen/sluiten flyout.

---

## Build summary

- Nieuw gebouwd:
  - Inline `ErrorBoundary` in `AgentDetailsFlyout.tsx`
- Gewijzigd:
  - `frontend/src/components/features/AgentDetailsFlyout.tsx`
  - `frontend/src/components/features/__tests__/AgentDetailsFlyout.test.tsx`
- Verwijderd: niets.
- Beinvloede bestaande flows: AgentDetailsFlyout Overview tab toont nu ook context injectie monitor.

---

## Frontend inventory

| ID          | Naam                                  | Type          | Locatie                                                    | Nieuw/Wijziging | Gerelateerde flow          |
| ----------- | ------------------------------------- | ------------- | ---------------------------------------------------------- | --------------- | -------------------------- |
| FE-CMP-008a | ContextInjectionPanel in Flyout       | Integratie    | `frontend/src/components/features/AgentDetailsFlyout.tsx`  | Wijziging       | Agent details bekijken     |
| FE-CMP-008a | ErrorBoundary voor ContextInjectionPanel | ErrorBoundary | `frontend/src/components/features/AgentDetailsFlyout.tsx`  | Nieuw           | Foutafhandeling panel      |

---

## Gebruikersflows

### Flow ID: FE-FLW-008a

- Naam: Agent context monitoren in flyout
- Startconditie: Gebruiker opent de AgentDetailsFlyout voor een agent.
- Trigger: Flyout opent met de Overview tab actief.
- Hoofdstappen:
  1. Flyout rendert.
  2. Overview tab toont agent ID, placeholder en ContextInjectionPanel.
  3. ContextInjectionPanel verbindt met de agent-context WebSocket.
  4. Gebruiker ziet realtime context chunks en token gebruik.
- Succespad: Context panel laadt en toont data.
- Foutpad: ErrorBoundary toont fallback als ContextInjectionPanel crasht.
- Eindtoestand: Panel is zichtbaar op Overview, niet op andere tabs.

---

## Detaildocumentatie per item

---

## [FE-CMP-008a] ContextInjectionPanel in AgentDetailsFlyout

### 1. Type

Integratie-wijziging op component-niveau.

### 2. Locatie

`frontend/src/components/features/AgentDetailsFlyout.tsx`

### 3. Gerelateerde flow

FE-FLW-008a -- Agent context monitoren in flyout.

### 4. Doel

Gebruikers directe toegang geven tot context injectie monitoring binnen het agent detail overzicht.

### 5. Functionele beschrijving

De Overview tab van de flyout bevat onder de bestaande agent info een nieuwe sectie "Context Injectie". Deze sectie rendert de bestaande `ContextInjectionPanel`.

### 6. Technische beschrijving

- `ContextInjectionPanel` wordt geimporteerd als default export.
- Overview `Tabs.Content` is omgezet naar `flex flex-col gap-4 min-h-0` zodat het panel de resterende hoogte kan innemen.
- Het panel is gewrapt in een inline `ErrorBoundary` die een fallback toont bij een render-fout.
- NOTE comment documenteert dat `ContextInjectionPanel` bij mount een WebSocket opent en deze sluit bij unmount (flyout sluiten).

### 7. Zichtbaarheidsregels

- Alleen zichtbaar op de Overview tab.
- Wordt verwijderd uit DOM bij wisselen naar een andere tab of sluiten van de flyout.

### 8. States en gedrag

- Default: panel rendert en opent WebSocket.
- Connected: toont context chunks en token meter.
- Disconnected: toont disconnected banner.
- Error: ErrorBoundary toont fallback tekst.

### 9. Input

- Geen props; `ContextInjectionPanel` gebruikt intern `useKnowledgeStore` en `useAgenticWebSocket`.

### 10. Output

- Visuele weergave van context injectie monitor.
- Fallback bij fout.

### 11. Validaties

- Geen formuliervalidatie.

### 12. Business rules

- Panel alleen op Overview tab.
- Fout in panel mag flyout niet crashen.

### 13. Afhankelijkheden

- `ContextInjectionPanel` uit `@/components/knowledge/ContextInjectionPanel`.
- Inline `ErrorBoundary` class component.

### 14. Foutafhandeling

- Render-fout in `ContextInjectionPanel` wordt opgevangen door `ErrorBoundary`.
- WebSocket fouten worden intern afgehandeld door `useAgenticWebSocket`.

### 15. Telemetry / logging / analytics

Geen specifieke telemetry toegevoegd.

### 16. Accessibility-notities

- Sectie heeft een heading in `text-slate-400`.
- ErrorBoundary fallback is een `p` element.

### 17. Acceptatiecriteria

- [ ] ContextInjectionPanel is zichtbaar op Overview tab.
- [ ] ContextInjectionPanel is niet zichtbaar op andere tabs.
- [ ] Fout in ContextInjectionPanel crasht de flyout niet.
- [ ] Overview tab layout blijft correct (geen overflow issues).

### 18. Gebruikersuitleg

- Open de details van een agent.
- Blijf op de Overview tab; onderaan ziet u de Context Injectie monitor.
- De monitor toont realtime context chunks en het token gebruik.
- Als het panel niet kan laden, wordt een foutmelding getoond in plaats van de hele flyout te sluiten.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker die agent details bekijkt.
- Voorwaarde: AgentDetailsFlyout is geopend op Overview tab.
- Actie: Gebruiker bekijkt de Context Injectie sectie.
- Systeemreactie: ContextInjectionPanel verbindt en toont context/ tokens.
- Succesrespons: Panel toont data.
- Foutrespons: ErrorBoundary toont fallback.
- Uitzonderingen: Bij tabwissel of flyout sluiten wordt het panel verwijderd en de WebSocket verbinding gesloten.

---

## Handleidingstekst

### Voor eindgebruikers

In de Agent Details flyout kunt u op de Overview tab een Context Injectie monitor zien. Deze monitor toont welke context chunks naar de agent worden gestuurd en hoeveel tokens dit gebruikt. Het helpt om te debuggen waarom een agent bepaalde informatie wel of niet heeft.

---

## Open aannames

- `ContextInjectionPanel` toont de globale agent-context stream; per-agent filtering is nog niet geimplementeerd.
- De WebSocket levenscyclus (connect on open, disconnect on close) wordt geaccepteerd voor deze iteratie.

## Open vragen

- Moet ContextInjectionPanel worden afgeschermd achter een specifieke scope (bijv. `knowledge:debug`)?

## Risico's

- Low: herhaald openen/sluiten van de flyout opent elke keer een nieuwe WebSocket verbinding. Dit kan op termijn worden geoptimaliseerd.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [x] Error state getest
- [ ] Responsive gecontroleerd
- [ ] Cross-browser gecontroleerd

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
