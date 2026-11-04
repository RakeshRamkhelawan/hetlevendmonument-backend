# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-020
- Feature naam: Integrations.tsx ADR-028 quick-audit
- Status: Verified
- Auteur: SP-FE-2D Dag 2
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-FE-2D -- Integrations.tsx quick-audit
- Gerelateerde pagina / route: /integrations (redesign)
- Gerelateerde backend endpoints: POST /api/v1/integrations/{id}/toggle
- Gerelateerde design componenten: ServiceCard, useIntegrationsStore
- Versie: 1.0

---

## Doel en scope

### Doel

Verifiëren dat `Integrations.tsx` voldoet aan ADR-028 (Phase 2 Frontend Visual Redesign) zonder ingrijpende wijzigingen te introduceren.

### In scope

- Visuele inspectie op ADR-028 checklist: dark theme, Tailwind-only, geen inline styles, geen raw hex, ASCII-only, geen `any`.
- Documenteren van bevindingen en uitzonderingen.

### Out of scope

- BusinessWrapper vervanging (pagina heeft eigen full-page studio-layout).
- PermissionGate toevoegen (vereist scope-beslissing en ServiceCard wijzigingen).
- Functionaliteitswijzigingen aan toggles of OAuth flow.

---

## Build summary

- Nieuw gebouwd: geen.
- Gewijzigd: geen.
- Verwijderd: niets.
- Beinvloede bestaande flows: geen; alleen audit-documentatie.

---

## Frontend inventory

| ID         | Naam                         | Type   | Locatie                                         | Nieuw/Wijziging | Gerelateerde flow         |
| ---------- | ---------------------------- | ------ | ----------------------------------------------- | --------------- | ------------------------- |
| FE-PGS-020 | Integrations ADR-028 audit   | Audit  | `frontend/src/pages/redesign/Integrations.tsx`  | Verificatie     | Integraties overzicht     |

---

## Gebruikersflows

### Flow ID: FE-FLW-020

- Naam: Integraties bekijken en beheren
- Startconditie: Gebruiker is ingelogd en bevindt zich op `/integrations?ui=business`.
- Trigger: Gebruiker opent de Integrations pagina.
- Hoofdstappen:
  1. Pagina toont de lijst met integratieservices.
  2. Gebruiker filtert op All / Connected / Available.
  3. Gebruiker klikt op een toggle of OAuth connect knop.
- Succespad: Service status wordt bijgewerkt (optimistic) en bevestigd.
- Foutpad: Toast toont een foutmelding bij mislukte API-call.
- Eindtoestand: Service grid toont de bijgewerkte status.

---

## Detaildocumentatie per item

---

## [FE-PGS-020] Integrations.tsx ADR-028 audit

### 1. Type

Pagina / quick-audit.

### 2. Locatie

`frontend/src/pages/redesign/Integrations.tsx`

### 3. Gerelateerde flow

FE-FLW-020 -- Integraties bekijken en beheren.

### 4. Doel

Bieden van een consistente, dark-themed gebruikersinterface voor het beheren van integratieservices.

### 5. Functionele beschrijving

De pagina toont een 3-panel layout:
- Linker navigatiepaneel met filteropties (All, Connected, Available).
- Centraal canvas met titel, egress-info banner en service grid.
- Rechter instellingenpaneel (placeholder).

### 6. Technische beschrijving

- Full-page layout met `bg-slate-950 text-slate-100`.
- Tailwind-only styling; geen inline styles of raw hex kleuren.
- `FilterOption` type is getypeerd; geen `any`.
- Service toggles en OAuth connect worden afgehandeld via `useIntegrationsStore` en `api.post`.
- ASCII-only identifiers en strings.

### 7. Zichtbaarheidsregels

- Pagina zichtbaar voor ingelogde gebruikers met toegang tot `/integrations`.
- Service toggles en OAuth connect zijn momenteel niet achter een `PermissionGate` geplaatst.

### 8. States en gedrag

- Default: service grid laadt op basis van store-state.
- Loading: `pendingServiceIds` in store toont optimistic UI in `ServiceCard`.
- Error: toast bij mislukte toggle of geblokkeerde popup.
- Empty: mogelijk wanneer filter geen resultaten geeft (afhankelijk van ServiceCard implementatie).

### 9. Input

- `services` uit `useIntegrationsStore`.
- Gebruikersinteracties: filterknoppen, toggle, OAuth connect.

### 10. Output

- Gewijzigde service status in store + backend.
- Toast notificaties.

### 11. Validaties

- `encodeURIComponent(id)` bij API calls.
- Optimistic toggle met rollback bij fout.

### 12. Business rules

- Egress restricted services worden visueel gemarkeerd (info banner).
- OAuth connect opent een popup; bij blokkade wordt een fout getoond.

### 13. Afhankelijkheden

- `useIntegrationsStore`, `ServiceCard`, `api`, `openOAuthPopup`, `react-hot-toast`.

### 14. Foutafhandeling

- API-fout: rollback + toast error.
- Popup blokkade: toast error.

### 15. Telemetry / logging / analytics

Geen specifieke telemetry toegevoegd in deze audit.

### 16. Accessibility-notities

- `aria-label` op aside elementen.
- `aria-current` op actieve filterknop.
- `aria-labelledby` op main canvas.
- `role="note"` op egress info banner.

### 17. Acceptatiecriteria

- [ ] Pagina gebruikt dark theme consistent met redesign.
- [ ] Geen inline styles of raw hex kleuren.
- [ ] Geen emoji of non-ASCII in code/comments.
- [ ] Geen onbewakte `any` types.
- [ ] ADR-028 checklist is gedocumenteerd met uitzonderingen.

### 18. Gebruikersuitleg

- Open Integrations om beschikbare en verbonden services te zien.
- Gebruik de linker filter om te focussen op connected of available services.
- Klik op een toggle om een service in of uit te schakelen.
- Klik op Connect om OAuth-gebaseerde services te koppelen.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker op Integrations pagina.
- Voorwaarde: Gebruiker heeft toegang tot /integrations.
- Actie: Gebruiker filtert services en klikt op toggle of connect.
- Systeemreactie: Pagina toont optimistic update en bevestigt via API.
- Succesrespons: Service status is bijgewerkt.
- Foutrespons: Toast toont foutmelding.
- Uitzonderingen: Geen services gevonden bij strikte filter.

---

## ADR-028 Audit checklist

| Check | Resultaat | Opmerking |
| ----- | --------- | --------- |
| Dark theme | PASS | `bg-slate-950`, `text-slate-100`, slate-800 borders |
| Geen inline styles | PASS | Tailwind-only className |
| Geen raw hex | PASS | Tailwind tokens |
| ASCII-only | PASS | Engelse identifiers/strings, geen emoji |
| Geen `any` types | PASS | `FilterOption` getypeerd |
| BusinessWrapper | NVT | Pagina heeft eigen full-page studio-layout |
| PermissionGate | GAP | Service toggles/connect niet achter scope guard; backlog |

## Open aannames

- De huidige Integrations layout wordt geaccepteerd als studio-achtige full-page layout.
- PermissionGate scope voor integratie-beheer is nog niet vastgesteld.

## Open vragen

- Welke OAuth2Scope hoort bij integratie toggle/connect? (bijv. `integrations:manage`)

## Risico's

- Low: ontbrekende PermissionGate is een beveiligingsdebt; moet worden opgepakt in een dedicated auth/scope sprint.

---

## QA-checks

- [x] Visuele ADR-028 checklist doorlopen
- [ ] Responsive gecontroleerd
- [ ] Cross-browser gecontroleerd
- [ ] PermissionGate scope vastgesteld en geimplementeerd

---

## Definition of Done

- [x] Feature is geaudit
- [x] Checklist resultaten gedocumenteerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Gebruikersuitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
