# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-019
- Feature naam: Knowledge page uitbreiding
- Status: Done
- Auteur: SP-FE-2D Dag 1
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2D -- Knowledge.tsx uitbreiden + useKnowledgeDocuments hook
- Gerelateerde pagina / route: /knowledge (redesign)
- Gerelateerde backend endpoints: GET /api/v1/knowledge/documents
- Gerelateerde design componenten: BusinessWrapper, PermissionGate, SemanticSearch, EmbeddingsQualityDashboard, Dialog
- Versie: 1.0

---

## Doel en scope

### Doel

De Knowledge pagina in de redesign-modus uitbreiden van een stub naar een volwaardig documentbeheer- en kwaliteitsoverzicht. Gebruikers kunnen documenten bekijken, filteren, zoeken en beheren binnen hun tenant.

### In scope

- Nieuwe `useKnowledgeDocuments` hook voor het ophalen van documenten.
- Volledige vervanging van de 10-regel `Knowledge.tsx` stub.
- Documentenlijst met zoekbalk, agent-filter, status-filter en min-kwaliteit slider.
- Client-side filtering en paginering (maximaal 50 documenten per pagina).
- Kwaliteitsbadge per document (rood bij score < 0.70, groen daarboven).
- Destructieve acties "Re-index" en "Verwijder" achter `PermissionGate` met scope `memory:manage`.
- Verwijder-bevestiging via Radix `Dialog`.
- Integratie van bestaande `SemanticSearch` en `EmbeddingsQualityDashboard` componenten.
- Unit tests voor de hook (5) en de pagina (10).

### Out of scope

- Wijzigingen aan `SemanticSearch` of `EmbeddingsQualityDashboard` zelf.
- Echte backend-acties voor re-indexeren of verwijderen (alleen UI voorbereid).
- Bulkacties op documenten.
- Nieuwe upload-functionaliteit.

---

## Build summary

- Nieuw gebouwd:
  - `frontend/src/hooks/useKnowledgeDocuments.ts`
  - `frontend/src/hooks/__tests__/useKnowledgeDocuments.test.ts`
  - `frontend/src/pages/redesign/__tests__/Knowledge.test.tsx` (vervangt oude stub-test)
- Gewijzigd:
  - `frontend/src/pages/redesign/Knowledge.tsx` (stub -> volledige pagina)
  - `frontend/src/pages/redesign/Knowledge.stories.tsx` (RAGPipeline referentie verwijderd)
  - `frontend/src/hooks/index.ts` (barrel export toegevoegd)
- Verwijderd:
  - Import en rendering van `RAGPipeline` in `Knowledge.tsx`.
- Beinvloede bestaande flows:
  - `/knowledge?ui=business` toont nu documentbeheer, semantisch zoeken en embedding kwaliteit.

---

## Frontend inventory

| ID         | Naam                       | Type   | Locatie                                                | Nieuw/Wijziging | Gerelateerde flow         |
| ---------- | -------------------------- | ------ | ------------------------------------------------------ | --------------- | ------------------------- |
| FE-PGS-019 | Knowledge page             | Pagina | `frontend/src/pages/redesign/Knowledge.tsx`            | Wijziging       | Documenten beheren        |
| FE-HK-007  | useKnowledgeDocuments hook | Hook   | `frontend/src/hooks/useKnowledgeDocuments.ts`          | Nieuw           | Documenten ophalen        |
| FE-FLT-002 | Document filterbar         | Filter | Binnen `frontend/src/pages/redesign/Knowledge.tsx`     | Nieuw           | Documenten filteren       |
| FE-TBL-002 | Document card grid         | Grid   | Binnen `frontend/src/pages/redesign/Knowledge.tsx`     | Nieuw           | Documenten overzicht      |
| FE-MOD-003 | Verwijder dialoog          | Dialog | Binnen `frontend/src/pages/redesign/Knowledge.tsx`     | Nieuw           | Document verwijderen      |
| FE-PGS-019a| Semantisch zoeken sectie   | Sectie | Binnen `frontend/src/pages/redesign/Knowledge.tsx`     | Nieuw           | Semantisch zoeken         |
| FE-PGS-019b| Embedding kwaliteit sectie | Sectie | Binnen `frontend/src/pages/redesign/Knowledge.tsx`     | Nieuw           | Embedding kwaliteit check |

---

## Gebruikersflows

### Flow ID: FE-FLW-019

- Naam: Documenten bekijken en filteren
- Startconditie: Gebruiker is ingelogd met scope `knowledge:read` of bredere kennis-scope en bevindt zich op `/knowledge?ui=business`.
- Trigger: Gebruiker opent de Knowledge pagina.
- Hoofdstappen:
  1. Pagina haalt documenten op via `useKnowledgeDocuments`.
  2. Documenten worden getoond in een card grid.
  3. Gebruiker typt in de zoekbalk; na 300ms debounce wordt client-side gefilterd.
  4. Gebruiker selecteert een agent, status of min-kwaliteit.
  5. Filtering gebeurt client-side; paginering wordt teruggezet naar pagina 1.
- Succespad: De gebruiker ziet de gefilterde documentenlijst en kan door paginas bladeren.
- Foutpad: Bij een API-fout wordt een rode foutmelding getoond.
- Eindtoestand: Documentenlijst is zichtbaar, gefilterd of leeg met een placeholder.

---

## Detaildocumentatie per item

---

## [FE-PGS-019] Knowledge page

### 1. Type

Pagina component.

### 2. Locatie

`frontend/src/pages/redesign/Knowledge.tsx`

### 3. Gerelateerde flow

FE-FLW-019 -- Documenten bekijken en filteren.

### 4. Doel

Bieden van een centrale plek voor het beheren en inspecteren van knowledge documenten, met directe toegang tot semantisch zoeken en embedding kwaliteitsinformatie.

### 5. Functionele beschrijving

De pagina opent binnen `BusinessWrapper` met titel "Knowledge" en beschrijving. Bovenaan staat een documentenlijst met:
- Zoekveld om op titel te filteren.
- Dropdown om op agent te filteren.
- Knoppen voor status: Alle / Geindexeerd / In behandeling / Fout.
- Slider voor minimum kwaliteitsscore.
- Cards per document met titel, agent badge, token count, status en kwaliteitsbadge.
- "Re-index" en "Verwijder" acties (alleen zichtbaar met scope `memory:manage`).
- Paginering indien meer dan 50 documenten.

Daaronder staan secties "Semantisch Zoeken" en "Embedding Kwaliteit" die de bestaande componenten inladen.

### 6. Technische beschrijving

- Default export `Knowledge()`.
- Outer wrapper: `BusinessWrapper`.
- Gebruikt `useKnowledgeDocuments()` voor data.
- Client-side filter via `useMemo` op `search`, `agentFilter`, `statusFilter` en `minQuality`.
- `useMemo` voor debounced zoekterm met `setTimeout(300ms)`.
- Paginering: `PAGE_SIZE = 50`; `filteredDocs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)`.
- Verwijder dialoog via Radix `Dialog` met `DialogContent className="border-slate-800 bg-slate-900 text-slate-200"`.
- Destructieve acties achter `PermissionGate requiredScope={['memory:manage']}`.
- Loading state toont een spinner met `role="status"`.
- Error state toont een div met `role="alert"`.
- Empty state heeft `data-testid="empty-state"`.

### 7. Zichtbaarheidsregels

- Pagina zichtbaar voor geauthenticeerde gebruikers met toegang tot `/knowledge`.
- "Re-index" en "Verwijder" alleen zichtbaar bij scope `memory:manage`.
- Kwaliteitsbadge rood indien `quality_score < 0.70`.

### 8. States en gedrag

- Default: documentenlijst laadt.
- Loading: spinner zichtbaar.
- Error: rode foutmelding zichtbaar.
- Empty: placeholder "Geen documenten gevonden".
- Active: cards zichtbaar met filter- en pagineringscontrols.
- Delete dialog: geopend bij klik op "Verwijder"; gesloten na bevestigen of annuleren.

### 9. Input

- Documentenlijst uit `useKnowledgeDocuments()`.
- Gebruikersinteracties: zoekterm, agent selectie, status knoppen, min-kwaliteit slider, paginering.

### 10. Output

- Gefilterde en gepagineerde weergave van documenten.
- Open/gesloten state van verwijder dialoog.

### 11. Validaties

- Geen formuliervalidatie; filters zijn optioneel.
- `minQuality` slider begrensd tussen 0 en 1 met stap 0.05.

### 12. Business rules

- Maximaal 50 documenten per pagina.
- Documenten met kwaliteitsscore < 0.70 krijgen een rode badge.
- Verwijderen vereist expliciete bevestiging.

### 13. Afhankelijkheden

- `BusinessWrapper`, `PermissionGate`, `Dialog`, `Slider`.
- `SemanticSearch`, `EmbeddingsQualityDashboard`.
- `useKnowledgeDocuments` hook.

### 14. Foutafhandeling

- API-fout toont foutmelding; documentenlijst blijft leeg.
- Client-side filtering kan geen lege zoekresultaten veroorzaken zonder placeholder.

### 15. Telemetry / logging / analytics

Geen specifieke telemetry toegevoegd in deze iteratie.

### 16. Accessibility-notities

- Zoekveld heeft `label` via `htmlFor`.
- Loading spinner heeft `role="status"` en sr-only tekst.
- Foutmelding heeft `role="alert"`.
- Secties hebben koppen met unieke IDs.

### 17. Acceptatiecriteria

- [ ] Pagina rendert zonder fouten in `/knowledge?ui=business`.
- [ ] Documenten worden opgehaald via `useKnowledgeDocuments`.
- [ ] Zoekbalk filtert na 300ms debounce.
- [ ] Agent, status en min-kwaliteit filters werken client-side.
- [ ] Maximaal 50 cards zijn tegelijk zichtbaar.
- [ ] Kwaliteitsbadge is rood bij score < 0.70.
- [ ] "Re-index" en "Verwijder" zijn alleen zichtbaar met `memory:manage`.
- [ ] Verwijderen opent een bevestigingsdialoog.
- [ ] `SemanticSearch` en `EmbeddingsQualityDashboard` secties zijn zichtbaar.

### 18. Gebruikersuitleg

- Open de Knowledge pagina om uw documenten te bekijken.
- Gebruik de zoekbalk en filters om snel documenten te vinden.
- Documenten met een rode kwaliteitsbadge hebben een lage embedding score.
- Met de juiste rechten kunt u documenten opnieuw indexeren of verwijderen.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met toegang tot Knowledge pagina.
- Voorwaarde: Gebruiker heeft documenten in de knowledge store.
- Actie: Gebruiker opent Knowledge, filtert op agent/status/kwaliteit en bekijkt documenten.
- Systeemreactie: Pagina toont gefilterde documenten met kwaliteitsindicatie.
- Succesrespons: Gebruiker ziet de gewenste documenten en kan acties uitvoeren.
- Foutrespons: Pagina toont foutmelding bij API-problemen.
- Uitzonderingen: Geen documenten geeft een lege-state placeholder.

---

## Handleidingstekst

### Voor eindgebruikers

De Knowledge pagina is het centrale overzicht voor alle documenten en kennisbronnen van uw tenant.

1. **Documenten bekijken**: bij openen van de pagina worden alle documenten geladen.
2. **Zoeken en filteren**: gebruik de zoekbalk, agent dropdown, status knoppen of de kwaliteitsslider.
3. **Kwaliteit controleren**: een rode badge betekent dat de embedding score onder de 70% zit.
4. **Acties**: met de juiste rechten kunt u een document opnieuw indexeren of verwijderen. Verwijderen vraagt altijd om bevestiging.
5. **Semantisch zoeken**: gebruik de onderste sectie om gerelateerde inhoud te vinden op basis van betekenis.
6. **Embedding kwaliteit**: bekijk het histogram en de verdeling van embedding scores.

---

## Open aannames

- Het backend endpoint `GET /api/v1/knowledge/documents` retourneert de verwachte documentstructuur.
- De scope `memory:manage` is beschikbaar voor gebruikers die documenten mogen beheren.

## Open vragen

Geen.

## Risico's

- Low: re-index en verwijderen zijn nog alleen UI-voorbereid zonder echte mutatie-calls.

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
