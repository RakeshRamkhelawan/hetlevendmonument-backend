# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-016
- Feature naam: AuditLogs dark theme retrofit
- Status: Done
- Auteur: SP-FE-2C Dag 1 (implementatie) + Dag 3 (documentatie)
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-28 (implementatie), 2026-06-29 (documentatie)
- Gerelateerde user story / ticket: SP-FE-2C -- Phase 2 Sprint 2c (Compliance & Audit)
- Gerelateerde pagina / route: /admin/audit, /settings/audit (via bestaande callers)
- Gerelateerde backend endpoints: `GET /admin/logs`
- Gerelateerde design componenten: AuditLogs, Search input, Severity filter buttons, Logs table
- ADR / design system: ADR-028 (Phase 2 Frontend Visual Redesign), ASCII-only, geen emoji
- Versie: 1.0

---

## Doel en scope

### Doel

De `AuditLogs` pagina visueel aanpassen aan de ADR-028 dark theme standaard (`bg-slate-950 text-slate-100`) zonder bestaande functionaliteit of callers te breken.

### In scope

- Vervangen van de oude gradient outer-container className in de drie hoofdtakken (loading, error, success) door `min-h-screen bg-slate-950 text-slate-100 p-8`.
- Behoud van de `naked` prop voor bestaande callers (`AdminAuditLogs`, `SettingsAuditLogs`).
- Behoud van alle bestaande interactieve elementen: zoekveld, severity filter, export knoppen, logs tabel.
- Dark-theme tests.

### Out of scope

- Wijzigingen aan de logica van zoeken, filteren, exporteren of data fetching.
- Nieuwe componenten of routes.
- Wijzigingen aan de `AuditLog` data interface.

---

## Build summary

- Nieuw gebouwd: dark-theme tests voor `AuditLogs`.
- Gewijzigd: `frontend/src/pages/AuditLogs.tsx` (3 outer-container classNames).
- Verwijderd: niets.
- Beinvloede bestaande flows: `/admin/audit` en `/settings/audit` tonen nu dezelfde logs in dark theme.

---

## Frontend inventory

| ID          | Naam                          | Type          | Locatie                                          | Nieuw/Wijziging | Gerelateerde flow         |
| ----------- | ----------------------------- | ------------- | ------------------------------------------------ | --------------- | ------------------------- |
| FE-PGS-016  | AuditLogs dark theme retrofit | Page          | `frontend/src/pages/AuditLogs.tsx`               | Wijziging       | Audit logs bekijken       |
| FE-FLW-016  | Bekijk audit logs             | Gebruikersflow| `frontend/src/pages/AuditLogs.tsx`               | Wijziging       | Audit logs bekijken       |
| --          | Search input                  | Input         | Binnen `AuditLogs`                               | Ongewijzigd     | Zoeken in logs            |
| --          | Severity filter buttons       | Button group  | Binnen `AuditLogs`                               | Ongewijzigd     | Filteren op severity      |
| --          | JSON export button            | Button        | Binnen `AuditLogs`                               | Ongewijzigd     | Exporteren logs           |
| --          | CSV export button             | Button        | Binnen `AuditLogs`                               | Ongewijzigd     | Exporteren logs           |
| --          | Logs table                    | Tabel         | Binnen `AuditLogs`                               | Ongewijzigd     | Logs weergeven            |

---

## Gebruikersflows

### Flow ID: FE-FLW-016

- Naam: Bekijk audit logs
- Startconditie: Gebruiker is ingelogd en opent `/admin/audit` of `/settings/audit`.
- Trigger: Pagina wordt geladen.
- Hoofdstappen:
  1. `AuditLogs` fetched logs via `useQuery` (`GET /admin/logs`).
  2. Bij loading toont de pagina een spinner.
  3. Bij error toont de pagina een foutmelding.
  4. Bij success toont de pagina de logs tabel met zoek- en filtermogelijkheden.
  5. Gebruiker kan zoeken, filteren op severity, of exporteren (export is stub).
- Succespad: Gebruiker ziet een dark-theme overzicht van audit logs.
- Foutpad: Foutmelding bij falende fetch.
- Eindtoestand: Pagina toont logs, loading state, error state of "No logs found".

---

## Detaildocumentatie per item

---

## [FE-PGS-016] AuditLogs dark theme retrofit

### 1. Type

Pagina component (retrofit).

### 2. Locatie

`frontend/src/pages/AuditLogs.tsx`.

### 3. Gerelateerde flow

FE-FLW-016 -- Bekijk audit logs.

### 4. Doel

De AuditLogs pagina visueel laten aansluiten bij de ADR-028 dark theme standaard zonder functionaliteit te wijzigen.

### 5. Functionele beschrijving

De pagina toont een overzicht van audit logs. De header bevat titel, beschrijving en export knoppen. Onder de header bevinden zich een zoekveld en severity filter knoppen. De logs worden in een tabel met kolommen Timestamp, Event Type, Message, Severity en IP Address weergegeven. Bij lege resultaten toont de pagina een "No logs found" bericht.

De retrofit heeft alleen de achtergrondkleur en tekstkleur van de drie outer containers aangepast (loading, error, success) naar `bg-slate-950 text-slate-100`. Alle andere elementen waren al dark-theme consistent.

### 6. Technische beschrijving

- `AuditLogs` is een default export function component.
- Accepteert optionele `naked` prop (`{ naked?: boolean }`).
- `naked === true`: rendert inhoud zonder outer container styling (gebruikt door `AdminAuditLogs` en `SettingsAuditLogs` die hun eigen wrapper hebben).
- `naked !== true`: rendert met `min-h-screen bg-slate-950 text-slate-100 p-8` en `max-w-7xl mx-auto`.
- De drie hoofdtakken (loading, error, success) passeren dezelfde outer className logica.
- Data fetching via `@tanstack/react-query` `useQuery` met key `['audit-logs']`.
- Client-side filtering op `event_type`, `message` en `severity`.

### 7. Zichtbaarheidsregels

- De pagina is zichtbaar voor ingelogde gebruikers met toegang tot de audit routes.
- Export knoppen tonen een toast dat export niet beschikbaar is.
- `naked` prop bepaalt of de outer container styling wordt toegepast.

### 8. States en gedrag

- Default: success state met logs tabel of "No logs found".
- Loading: spinner getoond in een gecentreerde layout.
- Error: waarschuwingsicoon + foutmelding.
- Empty: "No logs found" bericht met zoek-/filter suggestie.
- Hover: tabelrijen lichten op; filter knoppen krijgen hover achtergrond.
- Active: geselecteerde severity filter heeft `bg-violet-500`.
- Disabled: export knoppen zijn niet disabled maar tonen een stub toast.

### 9. Input

- `naked` prop (boolean).
- Zoektekst (`searchQuery`).
- Geselecteerde severity (`filterSeverity`).
- Backend data via `GET /admin/logs`.

### 10. Output

- Gefilterde lijst van audit logs.
- Toast meldingen bij export acties.

### 11. Validaties

- Geen formuliervalidatie.
- Zoek en filter zijn client-side string matches.

### 12. Business rules

- `naked` prop moet volledig behouden blijven voor bestaande callers.
- De outer container gebruikt ADR-028 dark theme kleuren.
- Export functionaliteit is een stub (toont toast).

### 13. Afhankelijkheden

- `@tanstack/react-query` (`useQuery`).
- `lucide-react` (`Shield`, `Search`, `Download`, `Loader2`, `AlertTriangle`).
- `react-hot-toast`.
- `@/lib/api/client`.

### 14. Foutafhandeling

- Fetch error: toont foutmelding met `AlertTriangle` icoon.
- Export: toont `toast.error('Export not available')`.

### 15. Telemetry / logging / analytics

- Geen telemetry in deze pagina.

### 16. Accessibility-notities

- Zoekveld heeft placeholder tekst.
- Tabel heeft `th` elementen voor kolomkoppen.
- Filter knoppen zijn focusable.

### 17. Acceptatiecriteria

- [ ] Drie outer containers (loading, error, success) gebruiken `bg-slate-950 text-slate-100`.
- [ ] Oude gradient (`from-slate-900 via-purple-900 to-slate-900`) is verwijderd.
- [ ] `naked` prop behoudt bestaand gedrag.
- [ ] Bestaande callers (`AdminAuditLogs`, `SettingsAuditLogs`) blijven werken.
- [ ] Zoekveld, severity filter en export knoppen blijven functioneel.
- [ ] Dark-theme tests slagen.
- [ ] Geen non-ASCII in gewijzigde bestanden.

### 18. Gebruikersuitleg

- De Audit Logs pagina toont alle systeemactiviteiten in een donker thema.
- Je kunt zoeken op tekst en filteren op severity.
- De export knoppen zijn nog niet functioneel; ze geven een melding.
- Als de pagina wordt ingebed in een andere pagina (bijv. instellingen), wordt de buitenste wrapper weggelaten via de `naked` modus.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker met audit-toegang
- Voorwaarde: Gebruiker opent `/admin/audit` of `/settings/audit`
- Actie: Bekijk, zoek of filter audit logs
- Systeemreactie: Pagina fetched logs en toont deze in dark theme tabel
- Succesrespons: Logs zijn zichtbaar en kunnen worden gefilterd
- Foutrespons: Foutmelding bij falende fetch
- Uitzonderingen: `naked` modus toont dezelfde inhoud zonder outer container styling

---

## [FE-INP-016a] Search input

### 1. Type

Tekst input veld.

### 2. Locatie

`frontend/src/pages/AuditLogs.tsx` (regels 108-116).

### 3. Gerelateerde flow

FE-FLW-016 -- Bekijk audit logs.

### 4. Doel

Gebruikers toestaan te zoeken in audit logs op event type of bericht.

### 5. Functionele beschrijving

Een tekstveld met een zoekicoon. Bij wijziging filtert de lijst client-side.

### 6. Technische beschrijving

- Controlled input gekoppeld aan `searchQuery` state.
- Filter logica: case-insensitive `includes` op `event_type` en `message`.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar in success state.

### 8. States en gedrag

- Default: leeg invoerveld.
- Focus: border kleurt violet.

### 9. Input

- Toetsaanslagen van gebruiker.

### 10. Output

- Gewijzigde `searchQuery` state.

### 11. Validaties

- Geen.

### 12. Business rules

- Case-insensitive zoeken.

### 13. Afhankelijkheden

- `lucide-react` `Search` icoon.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Placeholder tekst aanwezig.
- Focus outline via `outline-none` + `focus:border-violet-500`.

### 17. Acceptatiecriteria

- [ ] Input veld is zichtbaar.
- [ ] Typen filtert de logs client-side.

### 18. Gebruikersuitleg

- Typ in het zoekveld om logs te filteren op event type of bericht.

### 19. Trainingssamenvatting

- Actor: Gebruiker
- Voorwaarde: Audit logs zijn geladen
- Actie: Typ zoekterm in het zoekveld
- Systeemreactie: Tabel toont alleen logs die de term bevatten
- Succesrespons: Gefilterde logs zichtbaar
- Foutrespons: Geen
- Uitzonderingen: Geen

---

## [FE-BTN-016a] Severity filter buttons

### 1. Type

Button group.

### 2. Locatie

`frontend/src/pages/AuditLogs.tsx` (regels 120-140).

### 3. Gerelateerde flow

FE-FLW-016 -- Bekijk audit logs.

### 4. Doel

Filteren van logs op severity niveau.

### 5. Functionele beschrijving

Een rij knoppen voor `All`, `Low`, `Medium`, `High`, `Critical`. De geselecteerde knop krijgt een violet thema.

### 6. Technische beschrijving

- Array van `[value, label]` tuples.
- `filterSeverity` state bepaat geselecteerde waarde.
- Click handler update state.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar in success state.

### 8. States en gedrag

- Default: "All" geselecteerd.
- Active: `bg-violet-500 text-white`.
- Hover: `bg-slate-900/80`.

### 9. Input

- Gebruikersklik.

### 10. Output

- Gewijzigde `filterSeverity` state.

### 11. Validaties

- Geen.

### 12. Business rules

- `All` toont alle logs.
- Exacte match op `log.severity`.

### 13. Afhankelijkheden

- Geen externe dependencies.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Knoppen zijn focusable.

### 17. Acceptatiecriteria

- [ ] Alle severity niveaus zijn beschikbaar.
- [ ] Geselecteerde knop heeft visuele active state.
- [ ] Filteren werkt client-side.

### 18. Gebruikersuitleg

- Klik op een severity om alleen logs van dat niveau te zien.

### 19. Trainingssamenvatting

- Actor: Gebruiker
- Voorwaarde: Audit logs zijn geladen
- Actie: Klik op severity knop
- Systeemreactie: Tabel filtert op geselecteerde severity
- Succesrespons: Gefilterde logs zichtbaar
- Foutrespons: Geen
- Uitzonderingen: Geen

---

## [FE-TBL-016a] Logs table

### 1. Type

Tabel.

### 2. Locatie

`frontend/src/pages/AuditLogs.tsx` (regels 147-211).

### 3. Gerelateerde flow

FE-FLW-016 -- Bekijk audit logs.

### 4. Doel

Toon audit logs in een gestructureerde tabel.

### 5. Functionele beschrijving

Tabel met kolommen Timestamp, Event Type, Message, Severity en IP Address. Severity heeft een gekleurde badge.

### 6. Technische beschrijving

- Standaard HTML `table`.
- Severity kleuren: critical/high = rood, medium = geel, overig = groen.

### 7. Zichtbaarheidsregels

- Zichtbaar in success state wanneer logs beschikbaar zijn.

### 8. States en gedrag

- Default: toont gefilterde logs.
- Hover: rijen lichten op.

### 9. Input

- Gefilterde logs array.

### 10. Output

- Gerenderde tabel.

### 11. Validaties

- Geen.

### 12. Business rules

- Timestamp wordt geformatteerd via `new Date(log.timestamp).toLocaleString()`.

### 13. Afhankelijkheden

- Geen externe dependencies.

### 14. Foutafhandeling

- Geen.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- `th` elementen voor kolomkoppen.

### 17. Acceptatiecriteria

- [ ] Tabel toont alle log kolommen (Timestamp, Event Type, Message, Severity, IP Address).
- [ ] Severity badges hebben juiste kleur.

### 18. Gebruikersuitleg

- De tabel toont per log het tijdstip, type, bericht, severity en IP adres.

### 19. Trainingssamenvatting

- Actor: Gebruiker
- Voorwaarde: Audit logs zijn geladen
- Actie: Bekijk de logs tabel
- Systeemreactie: Tabel toont logs met severity kleurcodering
- Succesrespons: Logs zichtbaar
- Foutrespons: Geen
- Uitzonderingen: Geen

---

## Handleidingstekst

### Voor eindgebruikers

De Audit Logs pagina toont een overzicht van alle systeemactiviteiten. Je kunt zoeken op woorden en filteren op severity (Low, Medium, High, Critical). De pagina gebruikt een donker thema dat consistent is met de rest van de business-mode interface. Export knoppen zijn op dit moment nog niet functioneel.

---

## Open aannames

- `AuditLogs` wordt op twee plekken gebruikt: met `naked={false}` (eigen pagina) en met `naked={true}` (ingebouwd in instellingen/admin pagina's).
- De bestaande callers (`AdminAuditLogs`, `SettingsAuditLogs`) passen hun eigen padding/achtergrond toe.
- De `GET /admin/logs` endpoint blijft ongewijzigd.

## Open vragen

- Wanneer wordt de export functionaliteit (JSON/CSV) daadwerkelijk geimplementeerd?

## Risico's

- De `naked` prop is essentieel voor bestaande callers. Een fout hier breekt de admin- en settings-integratie.
- De oude gradient className is verwijderd; callers die hierop vertrouwden kunnen visueel breken (geen bekende afhankelijkheden).

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest (loading, error, empty, success)
- [ ] Error states getest (fetch fout handmatig gecontroleerd)
- [x] Accessibility gecontroleerd (tabel headers, focus states)
- [x] Responsive gecontroleerd (flex-wrap filters, overflow-x tabel)
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
