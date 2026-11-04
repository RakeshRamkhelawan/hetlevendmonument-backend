# BE-AUTH-001: trace:read + twin:read formaliseren in OAuth2Scope, rollen en PermissionGate

## Status

APPROVED

## Sprint

SP-FE-2G backlog cleanup (2026-06-30)

## Probleemstelling

Na SP-FE-2G waren `trace:read` en `twin:read` alleen als TypeScript-types gedefinieerd
in `authStore.ts`, maar ontbraken ze in de backend `OAuth2Scope` enum en in de
rol-scope toewijzing. Bovendien miste `/trace/:executionId` een `PermissionGate` in
`App.tsx`, terwijl `/digital-twin` (hetzelfde sprint) wel `PermissionGate(requiredScope="twin:read")`
had. Inconsistentie met `governance:read`, `prana:read` en andere scopes die in beide
lagen geregistreerd zijn.

## Wijzigingen

### Backend

**`src/core/auth/scopes.py`**
- `TRACE_READ = "trace:read"` toegevoegd aan `OAuth2Scope` enum
- `TWIN_READ = "twin:read"` toegevoegd aan `OAuth2Scope` enum

**`src/core/auth/auth_service.py`**
- `trace:read` en `twin:read` toegevoegd aan `admin`, `user`, `developer` rollen
- `viewer` uitgesteld (viewer heeft ook geen `governance:read` -- consistent patroon)

### Frontend

**`frontend/src/App.tsx`**
- `/trace/:executionId` route geWrapped met
  `PermissionGate(requiredScope="trace:read", fallback={<Navigate to="/dashboard" replace />})`
- Identiek patroon als `/digital-twin` (PermissionGate binnen ProtectedRoute)

## Verificatie

- `python -m pyright src/core/auth/` -- 0 errors
- `ruff check src/core/auth/scopes.py src/core/auth/auth_service.py` -- clean
- `cd frontend && npm run type-check` -- 0 errors
- Commit: `26ee2af5`

## Niet in scope

- Backend API-endpoints achter `require_scopes(TRACE_READ)` plaatsen
- `viewer` krijgt geen `trace:read` (bewuste keuze, consistent met `governance:read`)

## Trainingssamenvatting

- Actor: geauthenticeerde gebruiker met rol admin, user of developer (viewer is uitgesloten) die de route /trace/:executionId of /digital-twin opent.
- Voorwaarde: de gebruiker is ingelogd; OAuth2Scope enum bevat TRACE_READ ("trace:read") en TWIN_READ ("twin:read"); de rol-scope mapping in AuthService kent deze scopes toe aan admin, user en developer.
- Actie (request): de gebruiker navigeert naar /trace/:executionId of /digital-twin.
- Systeemverwerking: de PermissionGate in App.tsx controleert requiredScope ("trace:read" of "twin:read") tegen de scopes van de ingelogde gebruiker.
- Succesrespons: de TraceViewer- of DigitalTwin-pagina wordt gerenderd.
- Foutrespons: de PermissionGate fallback stuurt de gebruiker terug naar /dashboard.
- Uitzonderingen: backend API-endpoints achter require_scopes(TRACE_READ) plaatsen is bewust niet in scope; viewer heeft bewust geen toegang, consistent met governance:read.
