# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-017
- Feature naam: CouncilVerdictTimeline
- Status: Done
- Auteur: SP-FE-2C Dag 2
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-28
- Gerelateerde user story / ticket: SP-FE-2C -- CouncilVerdictTimeline + HashChainVisualizer integratie
- Gerelateerde pagina / route: /council (CouncilDashboard)
- Gerelateerde backend endpoints: geen (frontend-only, data komt uit Zustand store)
- Gerelateerde design componenten: HashChainVisualizer, OfficerStatusCard, CouncilDashboard
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een overzichtelijke tijdlijn met definitieve Council-besluiten (resolved proposals) zodat compliance officers en auditors snel kunnen zien welke voorstellen zijn goedgekeurd, geblokkeerd of een HITL-verdict hebben gekregen.

### In scope

- Nieuw component `CouncilVerdictTimeline` in `frontend/src/components/compliance/`.
- Weergave van afgesloten proposals (status `APPROVED`, `BLOCKED`, `HITL`) met titel, status-badge, officer-verdict-chips en optionele block-hash.
- Filteren van `PENDING` proposals uit de tijdlijn.
- Empty state met duidelijke placeholder-tekst.

### Out of scope

- Klikgedrag op tijdlijn-items (geen navigatie of detail-modal).
- Live updates via WebSocket (wordt afzonderlijk afgehandeld in CouncilDashboard).
- Backend-integratie voor daadwerkelijke chain-data.

---

## Build summary

- Nieuw gebouwd: `frontend/src/components/compliance/CouncilVerdictTimeline.tsx` + unit tests.
- Gewijzigd: geen bestaande componenten direct gewijzigd; component wordt geconsumeerd door CouncilDashboard.
- Verwijderd: niets.
- Beinvloede bestaande flows: CouncilDashboard `/council` toont nu extra sectie "Verdict Tijdlijn".

---

## Frontend inventory

| ID          | Naam                    | Type          | Locatie                                                | Nieuw/Wijziging | Gerelateerde flow           |
| ----------- | ----------------------- | ------------- | ------------------------------------------------------ | --------------- | --------------------------- |
| FE-PGS-017  | CouncilVerdictTimeline  | Component     | `frontend/src/components/compliance/`                  | Nieuw           | Council audit & compliance  |
| FE-CMP-017a | Status badge (timeline) | Badge         | Binnen `CouncilVerdictTimeline`                        | Nieuw           | Council verdict weergave    |
| FE-CMP-017b | Verdict chip (timeline) | Badge/chip    | Binnen `CouncilVerdictTimeline`                        | Nieuw           | Officer verdict weergave    |

---

## Gebruikersflows

### Flow ID: FE-FLW-017

- Naam: Bekijk afgesloten Council besluiten
- Startconditie: Gebruiker is ingelogd met scope `compliance:read` en bevindt zich op `/council`.
- Trigger: CouncilDashboard rendert de "Verdict Tijdlijn" sectie.
- Hoofdstappen:
  1. Component ontvangt `proposals` array via props.
  2. Component filtert `PENDING` proposals eruit.
  3. Component toont resolved proposals in verticale lijst.
  4. Per item toont het de titel, status-badge, officer-verdict-chips en optionele block-hash.
- Succespad: Gebruiker ziet een lijst met afgesloten besluiten en kan de status per besluit aflezen.
- Foutpad: Geen netwerkcalls; bij lege data toont de component een placeholder.
- Eindtoestand: Tijdlijn is zichtbaar met 0 of meer resolved proposals.

---

## Detaildocumentatie per item

---

## [FE-PGS-017] CouncilVerdictTimeline

### 1. Type

Presentational React component (TSX).

### 2. Locatie

`frontend/src/components/compliance/CouncilVerdictTimeline.tsx`

### 3. Gerelateerde flow

FE-FLW-017 -- Bekijk afgesloten Council besluiten.

### 4. Doel

Toon een gefilterde, leesbare tijdlijn van resolved Council proposals voor audit en compliance-overzicht.

### 5. Functionele beschrijving

De component toont een verticale lijst van afgesloten besluiten. Elk item toont:
- De titel van het proposal.
- Een status-badge met de definitieve uitkomst (`APPROVED`, `BLOCKED`, `HITL`).
- Per officer verdict een chip met het officer-id en het verdict.
- Optioneel de volledige block-hash indien beschikbaar.

Als er geen afgesloten besluiten zijn, toont de component een gestippelde placeholder met de tekst "Geen afgesloten besluiten".

### 6. Technische beschrijving

- Props interface:
  ```typescript
  interface CouncilVerdictTimelineProps {
    proposals: DeliberationProposal[];
  }
  ```
- `DeliberationProposal` en `OfficerVerdict` worden geimporteerd uit `@/lib/stores/useComplianceStore`.
- De filteroperatie `resolvedProposals = proposals.filter((p) => p.status !== 'PENDING')` wordt boven het `return` statement uitgevoerd, niet inline in JSX.
- Kleurmappingen zijn lokale `Record<string, string>` constanten (`STATUS_COLORS`, `VERDICT_COLORS`) met fallback naar neutrale slate-styling.
- Root element heeft `data-testid="verdict-timeline"`; elk item heeft `data-testid={`timeline-entry-${proposal.id}`}`; status-badges hebben `data-testid={`timeline-status-${proposal.status}`}`.
- Named export `CouncilVerdictTimeline` en default export voor backward compatibility.

### 7. Zichtbaarheidsregels

- Component is altijd zichtbaar binnen de CouncilDashboard "Verdict Tijdlijn" sectie.
- Individuele items zijn alleen zichtbaar wanneer `status !== 'PENDING'`.
- De block-hash regel is alleen zichtbaar wanneer `proposal.blockHash` een truthy waarde bevat.

### 8. States en gedrag

- Default: toont resolved proposals of de empty-state placeholder.
- Empty: gestippelde container met tekst "Geen afgesloten besluiten".
- Loading: niet van toepassing; component ontvangt sync props.
- Error: niet van toepassing; geen async operaties.

### 9. Input

- `proposals`: array van `DeliberationProposal` objecten.

### 10. Output

- Rendered JSX; geen events of callbacks.

### 11. Validaties

- Geen runtime validaties; TypeScript props-interface waarborgt structuur.

### 12. Business rules

- Alleen proposals met een status ongelijk aan `PENDING` worden weergegeven.
- Status-badge kleuren zijn: `APPROVED` = emerald, `BLOCKED` = red, `HITL` = violet.
- Officer-verdict-chips gebruiken dezelfde kleuren als in CouncilDashboard.

### 13. Afhankelijkheden

- `@/lib/stores/useComplianceStore` voor TypeScript types.
- Tailwind CSS utility classes.

### 14. Foutafhandeling

- Bij ontbrekende status in kleurmap wordt een neutrale slate-styling fallback toegepast.
- Bij ontbrekende officer-verdict kleur wordt een neutrale slate-styling fallback toegepast.

### 15. Telemetry / logging / analytics

- Geen telemetry in deze component.

### 16. Accessibility-notities

- Titel en status zijn tekstueel leesbaar zonder alleen op kleur te vertrouwen.
- Verdict-chips bevatten een `title` attribuut met de officer reden voor screenreader-context.

### 17. Acceptatiecriteria

- [ ] Component rendert resolved proposals (`APPROVED`, `BLOCKED`, `HITL`) correct.
- [ ] `PENDING` proposals worden niet getoond.
- [ ] Empty state toont "Geen afgesloten besluiten".
- [ ] Status-badge heeft juiste kleur per status.
- [ ] Officer-verdict-chips gebruiken overeenkomstige kleuren.
- [ ] `blockHash` wordt alleen getoond wanneer aanwezig.
- [ ] Unit tests dekken happy path, empty state, filtering en kleuren.

### 18. Gebruikersuitleg

- Op de Council pagina zie je onder "Verdict Tijdlijn" een lijst met definitieve besluiten.
- Groen (`APPROVED`) betekent goedgekeurd, rood (`BLOCKED`) betekekt geblokkeerd, paars (`HITL`) betekent menselijke tussenkomst vereist.
- Klikken is niet mogelijk; het is een alleen-lezen overzicht.

### 19. Trainingssamenvatting

- Actor: Compliance officer / auditor
- Voorwaarde: Gebruiker heeft `compliance:read` scope en opent `/council`
- Actie: Scroll naar de "Verdict Tijdlijn" sectie
- Systeemreactie: Component filtert pending proposals en toont resolved proposals
- Succesrespons: Lijst met titel, status-badge en officer-chips is zichtbaar
- Foutrespons: Geen fout; bij geen data wordt de empty-state placeholder getoond
- Uitzonderingen: proposals met status `PENDING` zijn niet zichtbaar in de tijdlijn

---

## Handleidingstekst

### Voor eindgebruikers

De "Verdict Tijdlijn" geeft een overzicht van alle definitieve Council-besluiten. Je ziet direct welke voorstellen zijn goedgekeurd, geblokkeerd of een menselijke review vereisen. Pending voorstellen verschijnen niet in dit overzicht.

---

## Open aannames

- De `DeliberationProposal.status` waarden blijven beperkt tot `PENDING`, `APPROVED`, `BLOCKED`, `HITL`.
- Officer verdicts in `proposal.verdicts` gebruiken de waarden `APPROVED`, `BLOCKED`, `HITL_REQUIRED`, `MODIFIED`, `DEFERRED`.

## Open vragen

- Moet de tijdlijn in de toekomst sorteerbaar worden op tijdstip? (nu ongesorteerd, volgorde van input array)

## Risico's

- Kleurcodering alleen is niet voldoende voor toegankelijkheid; tekstuele labels zijn aanwezig.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [ ] Error states getest (niet van toepassing)
- [x] Accessibility gecontroleerd (tekst + title attributen)
- [x] Responsive gecontroleerd (flex-wrap, standaard Tailwind spacing)
- [ ] Cross-browser gecontroleerd
- [ ] Analytics/logging gecontroleerd (niet van toepassing)

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
- [x] Review door reviewer-prompt: APPROVED
