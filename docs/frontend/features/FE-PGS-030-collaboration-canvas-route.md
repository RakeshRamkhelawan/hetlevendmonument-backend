# FE-PGS-030 -- FE-001 CollaborationCanvas Route

**Sprint:** SP-SEC-002 Dag 1
**Datum:** 2026-07-01
**Status:** APPROVED

## Samenvatting

Route `/collaboration` toegevoegd aan `App.tsx` als lazy-loaded `ProtectedRoute`. Sidebar-link toegevoegd aan `BusinessSidebar.tsx` met `Users` icon. Pagina-component `CollaborationCanvas.tsx` bestond al.

## Trainingssamenvatting

- Actor: ingelogde gebruiker in business-mode
- Voorwaarde: gebruiker is geauthenticeerd; `App.tsx` bevat de `/collaboration` route; `BusinessSidebar.tsx` bevat het Collaboration navigatie-item
- Actie: klik op **Collaboration** in de linker sidebar of navigeer rechtstreeks naar `/collaboration`
- Systeemreactie: `App.tsx` rendert de lazy-loaded `CollaborationCanvas` pagina binnen een `ProtectedRoute` en `LazyWrapper`
- Succesrespons: de Collaboration Canvas pagina wordt geladen en getoond; de route-test rapporteert `3 passed`
- Foutrespons: niet ingelogd: doorsturen naar `/login`; route niet aanwezig: 404 pagina
- Uitzonderingen: de `CollaborationCanvas` pagina-component bestond al; deze feature voegt alleen de route en de sidebar-link toe

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `frontend/src/App.tsx` | Lazy import `CollaborationCanvas` + `<Route path="/collaboration">` |
| `frontend/src/components/layout/BusinessSidebar.tsx` | `Users` import + nav-item `{ to: '/collaboration', label: 'Collaboration', icon: Users }` |
| `frontend/src/pages/__tests__/CollaborationCanvas.route.test.tsx` | Nieuw -- 3 route-aanwezigheidstests |

## Implementatiedetail

```tsx
// App.tsx
const CollaborationCanvas = React.lazy(() => import('./pages/CollaborationCanvas'));
// Route:
<Route path="/collaboration" element={<ProtectedRoute><LazyWrapper><CollaborationCanvas /></LazyWrapper></ProtectedRoute>} />

// BusinessSidebar.tsx
{ to: '/collaboration', label: 'Collaboration', icon: Users }
```

## ADR-compliance

- CLAUDE.md copilot surface rule: `CollaborationCanvas` is een page, geen copilot overlay. Geen conflict.
- Pattern: identiek aan `ToolBrokerRegistry`, `HITLQueueRedesign`, `ToolAuditLogs`.

## Testbewijs

```
CollaborationCanvas.route.test.tsx -- 3 passed
```
