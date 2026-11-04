# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-018
- Feature naam: HashChainVisualizer integratie in CouncilDashboard
- Status: Done
- Auteur: SP-FE-2C Dag 2
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-28
- Gerelateerde user story / ticket: SP-FE-2C -- CouncilVerdictTimeline + HashChainVisualizer integratie
- Gerelateerde pagina / route: /council (CouncilDashboard)
- Gerelateerde backend endpoints: geen (demo-data via callback)
- Gerelateerde design componenten: HashChainVisualizer, CouncilVerdictTimeline, CouncilDashboard
- Versie: 1.0

---

## Doel en scope

### Doel

Integreren van de bestaande `HashChainVisualizer` in het CouncilDashboard zodat gebruikers een visuele hash-chain kunnen inladen en controleren op tampering.

### In scope

- Toevoegen van de "Hash Chain Audit" sectie aan CouncilDashboard.
- "Laad Keten" knop die demo audit-blocks in de Zustand store plaatst.
- Afleiden van `tamperBlockId` uit `tamperAlert` en `auditBlocks`.
- Doorgeven van `auditBlocks` en `tamperBlockId` aan `HashChainVisualizer`.

### Out of scope

- Nieuwe backend endpoints voor chain-data.
- Echte tamper-detectie logica (alleen bestaande store-state visualiseren).
- Wijzigingen aan het `HashChainVisualizer` component zelf.

---

## Build summary

- Nieuw gebouwd: geen nieuw component; integratie in bestaand dashboard.
- Gewijzigd: `frontend/src/pages/redesign/CouncilDashboard.tsx` + bijbehorende tests.
- Verwijderd: niets.
- Beinvloede bestaande flows: `/council` route toont hash-chain audit functionaliteit.

---

## Frontend inventory

| ID         | Naam                     | Type    | Locatie                                               | Nieuw/Wijziging | Gerelateerde flow        |
| ---------- | ------------------------ | ------- | ----------------------------------------------------- | --------------- | ------------------------ |
| FE-PGS-018 | HashChain Audit sectie   | Sectie  | `frontend/src/pages/redesign/CouncilDashboard.tsx`    | Wijziging       | Council audit            |
| FE-BTN-002 | Laad Keten knop          | Button  | Binnen CouncilDashboard "Hash Chain Audit" sectie     | Nieuw           | Chain inladen            |
| FE-PGS-018a| Tamper block indicator   | Visual  | Binnen `HashChainVisualizer` via `tamperBlockId` prop | Wijziging       | Tampering weergave       |

---

## Gebruikersflows

### Flow ID: FE-FLW-018

- Naam: Hash chain inladen en visueel controleren
- Startconditie: Gebruiker is ingelogd met scope `compliance:read` en bevindt zich op `/council`.
- Trigger: Gebruiker klikt op de "Laad Keten" knop.
- Hoofdstappen:
  1. Knop roept `handleLoadChain` callback aan.
  2. Callback plaatst 3 demo `AuditBlock` objecten in de store via `setAuditBlocks`.
  3. `HashChainVisualizer` rendert de blocks als horizontale tijdlijn.
  4. Indien `tamperAlert` aanwezig is, wordt het corresponderende blok rood gemarkeerd.
- Succespad: Gebruiker ziet een visuele chain met hashes, parent hashes en verdicts.
- Foutpad: Geen netwerkcalls; bij lege store toont HashChainVisualizer een placeholder.
- Eindtoestand: Chain is zichtbaar of de placeholder blijft staan.

---

## Detaildocumentatie per item

---

## [FE-PGS-018] HashChainVisualizer integratie in CouncilDashboard

### 1. Type

Integratie-wijziging op pagina-niveau.

### 2. Locatie

`frontend/src/pages/redesign/CouncilDashboard.tsx`

### 3. Gerelateerde flow

FE-FLW-018 -- Hash chain inladen en visueel controleren.

### 4. Doel

Toon een interactieve hash-chain audit visualisatie binnen het CouncilDashboard zodat auditors de integriteit van vastgelegde besluiten kunnen controleren.

### 5. Functionele beschrijving

Het CouncilDashboard bevat een nieuwe sectie "Hash Chain Audit". Deze sectie toont:
- Een koptekst "Hash Chain Audit".
- Een "Laad Keten" knop rechts van de koptekst.
- Het `HashChainVisualizer` component onder de knop.

Bij klik op "Laad Keten" worden demo audit-blocks geladen. Het visualisatiecomponent toont elk blok met sequence id, proposal titel, verdict, hash en parent hash. Wanneer een tamper-alert actief is, wordt het betreffende blok rood gemarkeerd.

### 6. Technische beschrijving

- Store destructuring is uitgebreid met `auditBlocks`, `setAuditBlocks` en `tamperAlert`.
- `tamperBlockId` wordt afgeleid met `useMemo`:
  ```typescript
  const tamperBlockId = useMemo(
    () =>
      tamperAlert != null
        ? (auditBlocks.find((b) => b.sequenceId === tamperAlert.brokenSequenceId)?.id ?? null)
        : null,
    [auditBlocks, tamperAlert]
  );
  ```
- `handleLoadChain` is een `useCallback` met afhankelijkheid `[setAuditBlocks]`. De callback bevat demo data met `Date.now()` voor tijdstempels. Een NOTE comment legt uit dat `Date.now()` hier alleen is toegestaan omdat het demo-data in een callback betreft.
- De sectie heeft `data-testid="hashchain-section"`.
- De knop heeft `type="button"` en toont tekst "Laad Keten".

### 7. Zichtbaarheidsregels

- Sectie is zichtbaar voor gebruikers met toegang tot `/council`.
- `HashChainVisualizer` toont een placeholder wanneer `auditBlocks` leeg is.
- Tamper-markering is alleen zichtbaar wanneer `tamperAlert` niet null is en een matching sequenceId heeft.

### 8. States en gedrag

- Default: lege chain; visualizer toont placeholder "Geen audit blocks geladen...".
- Active: na klik op "Laad Keten" worden 3 demo blocks getoond.
- Tampered: bij matching tamper-alert wordt het blok rood gemarkeerd en de connector toont BREAK.
- Loading: niet van toepassing.
- Error: niet van toepassing.

### 9. Input

- `auditBlocks` uit `useComplianceStore`.
- `tamperAlert` uit `useComplianceStore`.
- Gebruikersklik op "Laad Keten".

### 10. Output

- Gewijzigde `auditBlocks` in de Zustand store.
- Visuele weergave van de chain.

### 11. Validaties

- Geen formuliervalidatie.
- `tamperBlockId` valt terug op `null` wanneer geen matching block wordt gevonden.

### 12. Business rules

- Demo data bestaat uit 3 blocks met oplopende sequence IDs en gekoppelde parent hashes.
- `tamperBlockId` is `string | null` en nooit `undefined`.

### 13. Afhankelijkheden

- `frontend/src/components/compliance/HashChainVisualizer.tsx`
- `@/lib/stores/useComplianceStore`
- Tailwind CSS utility classes.

### 14. Foutafhandeling

- Wanneer `tamperAlert.brokenSequenceId` niet matched met een block, blijft `tamperBlockId` null en toont de visualizer geen tamper-styling.

### 15. Telemetry / logging / analytics

- Geen telemetry in deze flow.

### 16. Accessibility-notities

- De knop heeft `type="button"` zodat deze geen formulier submit.
- Koptekst en knop staan in een visueel duidelijke header.

### 17. Acceptatiecriteria

- [ ] "Hash Chain Audit" sectie is zichtbaar op `/council`.
- [ ] "Laad Keten" knop is aanwezig en klikbaar.
- [ ] Klik op "Laad Keten" vult de store met 3 demo blocks.
- [ ] `HashChainVisualizer` toont de geladen chain.
- [ ] `tamperBlockId` wordt correct afgeleid uit `tamperAlert` en `auditBlocks`.
- [ ] Integratie tests dekken sectie, knop en visualizer aanwezigheid.

### 18. Gebruikersuitleg

- In het Council Dashboard vind je de "Hash Chain Audit" sectie.
- Klik op "Laad Keten" om een voorbeeld van de audit-chain te zien.
- Elk blok toont het proposal, het verdict en de SHA-256 hash. Een rood blok of BREAK label geeft een integriteitsprobleem aan.

### 19. Trainingssamenvatting

- Actor: Compliance officer / auditor
- Voorwaarde: Gebruiker heeft `compliance:read` scope en opent `/council`
- Actie: Klik op de "Laad Keten" knop in de "Hash Chain Audit" sectie
- Systeemreactie: Demo audit blocks worden in de store gezet en de visualizer rendert de chain
- Succesrespons: Een horizontale tijdlijn met 3 blokken, hashes en verdicts is zichtbaar
- Foutrespons: Geen fout; bij lege chain toont de visualizer een placeholder
- Uitzonderingen: Een tamper-alert markeert het corresponderende blok rood

---

## Handleidingstekst

### Voor eindgebruikers

De "Hash Chain Audit" toont de onderlinge verbinding tussen vastgelegde Council-besluiten. Door op "Laad Keten" te klikken laad je een demo-chain waarin je kunt zien hoe elke beslissing koppelt aan de vorige via een hash. Een rood gemarkeerd blok of een BREAK-label geeft aan dat de keten mogelijk is aangepast.

---

## Open aannames

- De hash-chain data is momenteel demo-data; een latere sprint vervangt dit door een backend endpoint.
- `AuditBlock` structuur in de store blijft ongewijzigd.

## Open vragen

- Welk backend endpoint levert uiteindelijk de chain-data? (nu niet in scope)

## Risico's

- Demo-data kan verwarrend zijn voor productiegebruikers; duidelijke placeholder-tekst maakt dit expliciet.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest
- [ ] Error states getest (niet van toepassing)
- [x] Accessibility gecontroleerd (type=button, semantische kop)
- [x] Responsive gecontroleerd (overflow-x-auto op visualizer)
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
