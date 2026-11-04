# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-015
- Feature naam: CouncilDashboard route /council
- Status: Done
- Auteur: SP-FE-2C Dag 1 (implementatie) + Dag 3 (documentatie)
- Reviewer: Laag A code-reviewer + quality-reviewer
- Datum: 2026-06-28 (implementatie), 2026-06-29 (documentatie)
- Gerelateerde user story / ticket: SP-FE-2C -- Phase 2 Sprint 2c (Compliance & Audit)
- Gerelateerde pagina / route: /council
- Gerelateerde backend endpoints: geen (frontend-only route)
- Gerelateerde design componenten: CouncilDashboard, BusinessSidebar, ProtectedRoute, LazyWrapper
- ADR / design system: ADR-028 (Phase 2 Frontend Visual Redesign), ASCII-only, geen emoji
- Versie: 1.0

---

## Doel en scope

### Doel

Het CouncilDashboard (`pages/redesign/CouncilDashboard.tsx`) beschikbaar maken via de top-level route `/council` in de business-mode lay-out, met passende autorisatie, lazy loading en een zichtbare navigatielink in de BusinessSidebar.

### In scope

- Lazy import van `CouncilDashboard` in `App.tsx`.
- `/council` route binnen `ProtectedRoute > LazyWrapper`.
- Navigatielink "Council" met `Scale` icoon in `BusinessSidebar`, geplaatst na "Compliance".
- Route-test die controleert dat `/council` rendert en in `App.tsx` is geregistreerd.
- ADR-028 en ASCII-only naleving.

### Out of scope

- Wijzigingen aan het `CouncilDashboard` component zelf (dat is FE-PGS-017/018 of eerdere sprint-werk).
- Nieuwe backend endpoints of scopes.
- Wijzigingen aan andere routes of sidebars.

---

## Build summary

- Nieuw gebouwd: route registratie + sidebar navigatie-item + route tests.
- Gewijzigd: `frontend/src/App.tsx`, `frontend/src/components/layout/BusinessSidebar.tsx`.
- Verwijderd: niets.
- Beinvloede bestaande flows: business-mode navigatie toont nu een Council link; `/council` is direct bereikbaar via URL.

---

## Frontend inventory

| ID          | Naam                      | Type          | Locatie                                                  | Nieuw/Wijziging | Gerelateerde flow         |
| ----------- | ------------------------- | ------------- | -------------------------------------------------------- | --------------- | ------------------------- |
| FE-PGS-015  | CouncilDashboard route    | Route / page  | `frontend/src/App.tsx`                                   | Nieuw           | Navigeren naar /council   |
| FE-FLW-015  | Open Council Dashboard    | Gebruikersflow| `frontend/src/App.tsx` + `BusinessSidebar.tsx`           | Nieuw           | Council openen            |
| --          | ProtectedRoute wrapper    | Security      | `frontend/src/App.tsx` (rond `/council`)                 | Hergebruik      | Autorisatie /council      |
| --          | LazyWrapper wrapper       | Layout        | `frontend/src/App.tsx` (rond `CouncilDashboard`)         | Hergebruik      | Code splitting            |
| --          | Council nav item          | Navigatie     | `frontend/src/components/layout/BusinessSidebar.tsx`     | Nieuw           | Sidebar navigatie         |

---

## Gebruikersflows

### Flow ID: FE-FLW-015

- Naam: Open Council Dashboard
- Startconditie: Gebruiker is ingelogd en bevindt zich in business-mode.
- Trigger: Gebruiker klikt op "Council" in de BusinessSidebar of navigeert naar `/council`.
- Hoofdstappen:
  1. `ProtectedRoute` controleert of de gebruiker is geauthenticeerd.
  2. `LazyWrapper` toont een loading fallback terwijl `CouncilDashboard` lazy wordt geladen.
  3. `CouncilDashboard` rendert en toont intern een `PermissionGate` met scopes `compliance:read` en `compliance:manage`.
  4. Bij ontbrekende permissies toont `PermissionGate` een overlay / forbidden state.
- Succespad: Gebruiker ziet het Council Dashboard.
- Foutpad: Niet ingelogd -> redirect naar login. Geen permissie -> forbidden overlay.
- Eindtoestand: Council Dashboard is zichtbaar of een auth/permissie foutstate wordt getoond.

---

## Detaildocumentatie per item

---

## [FE-PGS-015] CouncilDashboard route /council

### 1. Type

Top-level route registratie met lazy-loaded page component.

### 2. Locatie

`frontend/src/App.tsx` (regel ~91 lazy import, regels ~335-342 route definitie).

### 3. Gerelateerde flow

FE-FLW-015 -- Open Council Dashboard.

### 4. Doel

Maak het Council Dashboard bereikbaar via de URL `/council` en via de business-mode sidebar.

### 5. Functionele beschrijving

Wanneer een geauthenticeerde gebruiker navigeert naar `/council`, laadt de applicatie het `CouncilDashboard` component lazy. Tijdens het laden wordt een loading fallback getoond. Het route-pad is alleen toegankelijk voor ingelogde gebruikers via `ProtectedRoute`. Binnen het dashboard bepaalt `CouncilDashboard` zelf of de gebruiker de juiste compliance scopes heeft.

### 6. Technische beschrijving

- Lazy import:
  ```typescript
  const CouncilDashboard = React.lazy(() => import('./pages/redesign/CouncilDashboard'));
  ```
- Route definitie:
  ```tsx
  <Route
    path="/council"
    element={
      <ProtectedRoute>
        <LazyWrapper>
          <CouncilDashboard />
        </LazyWrapper>
      </ProtectedRoute>
    }
  />
  ```
- `ProtectedRoute` controleert authenticatie.
- `LazyWrapper` voorziet in code-splitting en loading state.
- `CouncilDashboard` bevat intern `PermissionGate requiredScope={['compliance:read', 'compliance:manage']}`.
- `BusinessSidebar` voegt een `NavLink` toe met `to: '/council'`, `label: 'Council'`, `icon: Scale`.

### 7. Zichtbaarheidsregels

- De route is altijd geregistreerd in de router.
- De sidebar link is altijd zichtbaar in business-mode (momenteel geen scope-guard op nav item zelf; autorisatie gebeurt op route- en dashboard-niveau).
- `CouncilDashboard` toont geen inhoud bij ontbrekende permissies.

### 8. States en gedrag

- Default: sidebar toont "Council" link.
- Hover: sidebar link krijgt hover-styling.
- Active: wanneer op `/council`, is de link visueel gemarkeerd als actief.
- Loading: `LazyWrapper` toont fallback tijdens chunk download.
- Permission denied: `PermissionGate` toont overlay.
- Error: `LazyWrapper` / router error boundary vangt lazy-load fouten.

### 9. Input

- Gebruikersnavigatie (klik op sidebar link of directe URL).
- Auth state (via `ProtectedRoute`).

### 10. Output

- Gerenderd `CouncilDashboard` component.
- URL wijzigt naar `/council`.

### 11. Validaties

- Geen formuliervalidatie.
- Authenticatie en autorisatie worden afgehandeld door `ProtectedRoute` en `PermissionGate`.

### 12. Business rules

- `/council` is een protected route; anonieme gebruikers worden doorgestuurd naar login.
- `CouncilDashboard` vereist `compliance:read` of `compliance:manage` scope.
- De sidebar link staat direct na "Compliance".

### 13. Afhankelijkheden

- `frontend/src/pages/redesign/CouncilDashboard.tsx`
- `frontend/src/components/auth/RouteGuards.tsx` (`ProtectedRoute`)
- `frontend/src/components/LazyWrapper.tsx`
- `frontend/src/components/layout/BusinessSidebar.tsx`
- `lucide-react` (`Scale` icoon)

### 14. Foutafhandeling

- Niet geauthenticeerd: redirect naar login.
- Geen permissie: `PermissionGate` overlay.
- Lazy-load fout: afgevangen door error boundary.

### 15. Telemetry / logging / analytics

- Geen telemetry in deze route zelf.

### 16. Accessibility-notities

- `BusinessSidebar` heeft `aria-label="Business navigation"`.
- `NavLink` component gebruikt standaard anchor-semantiek.
- `LazyWrapper` fallback bevat visuele loading indicator.

### 17. Acceptatiecriteria

- [ ] `/council` is geregistreerd als route in `App.tsx`.
- [ ] `CouncilDashboard` wordt lazy-geladen.
- [ ] Route is gewrapped in `ProtectedRoute` en `LazyWrapper`.
- [ ] `BusinessSidebar` toont een "Council" link met `Scale` icoon na "Compliance".
- [ ] Klikken op de link navigeert naar `/council`.
- [ ] Route-test `CouncilDashboard.route.test.tsx` slaagt.
- [ ] Geen non-ASCII in gewijzigde bestanden.

### 18. Gebruikersuitleg

- In de business-mode sidebar vind je een "Council" link onder "Compliance".
- Klik op "Council" om het Council Dashboard te openen.
- Je moet ingelogd zijn en voldoende compliance-rechten hebben om de inhoud te zien.

### 19. Trainingssamenvatting

- Actor: Geauthenticeerde business-mode gebruiker
- Voorwaarde: Gebruiker is ingelogd en heeft `compliance:read` of `compliance:manage` scope
- Actie: Klik op "Council" in de BusinessSidebar of navigeer naar `/council`
- Systeemreactie: `ProtectedRoute` valideert auth, `LazyWrapper` laadt `CouncilDashboard`, `PermissionGate` valideert scope
- Succesrespons: Council Dashboard wordt zichtbaar
- Foutrespons: Redirect naar login (niet ingelogd) of permissie-overlay (geen scope)
- Uitzonderingen: Lazy-load fouten worden door de error boundary afgevangen

---

## [FE-TAB-015a] Council nav item

### 1. Type

Sidebar navigatielink (`NavLink` van react-router-dom).

### 2. Locatie

`frontend/src/components/layout/BusinessSidebar.tsx` (regel 22 in `NAV_ITEMS`).

### 3. Gerelateerde flow

FE-FLW-015 -- Open Council Dashboard.

### 4. Doel

Gebruikers een snelle manier bieden om naar `/council` te navigeren vanuit de business-mode sidebar.

### 5. Functionele beschrijving

De sidebar toont een rij met icoon en label "Council". Bij klikken navigeert de gebruiker naar `/council`. De link reageert op hover en active state.

### 6. Technische beschrijving

- Data-object in `NAV_ITEMS` array:
  ```typescript
  { to: '/council', label: 'Council', icon: Scale }
  ```
- Gerenderd als `NavLink` met `buildBizUrl(to)` voor business-mode query parameters.
- Styling afhankelijk van `isActive`.

### 7. Zichtbaarheidsregels

- Altijd zichtbaar in business-mode sidebar.
- Geen scope-guard op het nav item zelf.

### 8. States en gedrag

- Default: niet-actief styling.
- Hover: lichte achtergrondverandering.
- Active: oranje/rode gradient achtergrond en border.

### 9. Input

- Gebruikersklik.

### 10. Output

- Router navigatie naar `/council`.

### 11. Validaties

- Geen.

### 12. Business rules

- Positie in sidebar: na "Compliance".

### 13. Afhankelijkheden

- `lucide-react` `Scale` icoon.
- `useBizSearchParam` hook.

### 14. Foutafhandeling

- Geen specifieke foutafhandeling op nav item niveau.

### 15. Telemetry / logging / analytics

- Geen.

### 16. Accessibility-notities

- Sidebar heeft `aria-label="Business navigation"`.
- `NavLink` rendert een anchor element.

### 17. Acceptatiecriteria

- [ ] "Council" link is zichtbaar in sidebar.
- [ ] Link gebruikt `Scale` icoon.
- [ ] Link navigeert naar `/council`.
- [ ] Link staat na "Compliance".

### 18. Gebruikersuitleg

- De "Council" link in de linker sidebar opent het Council Dashboard.

### 19. Trainingssamenvatting

- Actor: Business-mode gebruiker
- Voorwaarde: Sidebar is zichtbaar
- Actie: Klik op "Council" in de sidebar
- Systeemreactie: Navigatie naar `/council`
- Succesrespons: Council Dashboard wordt geladen
- Foutrespons: Geen specifieke fout op dit niveau
- Uitzonderingen: Geen

---

## Handleidingstekst

### Voor eindgebruikers

Om het Council Dashboard te openen, klik je in de linker sidebar op "Council". Deze link staat onder "Compliance". Je moet ingelogd zijn en de juiste compliance-rechten hebben om de inhoud te zien. Als je niet voldoende rechten hebt, zie je een toegangsmelding in plaats van het dashboard.

---

## Open aannames

- `ProtectedRoute` en `LazyWrapper` blijven bestaan en gedragen zich consistent met andere routes.
- `CouncilDashboard` blijft verantwoordelijk voor interne permissiechecks.
- De sidebar toont nav items zonder scope-guard; autorisatie gebeurt op pagina-niveau.

## Open vragen

- Moet het nav item zelf ook een scope-guard krijgen zodat gebruikers zonder compliance-rechten de link helemaal niet zien?

## Risico's

- Sidebar link is altijd zichtbaar, inclusief voor gebruikers zonder compliance-rechten. Dit kan verwarring veroorzaken totdat een scope-guard op nav-niveau wordt toegevoegd.

---

## QA-checks

- [x] Functioneel getest
- [x] UI states getest (active/hover visueel gecontroleerd)
- [ ] Error states getest (auth redirect handmatig gecontroleerd)
- [x] Accessibility gecontroleerd (aria-label, anchor elementen)
- [x] Responsive gecontroleerd (sidebar hidden op mobile)
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
