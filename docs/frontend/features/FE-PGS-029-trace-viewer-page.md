# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-029
- Feature naam: TraceViewerPage -- swap components/traces naar pages/TraceViewer
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 3
- Reviewer: code-reviewer + quality-reviewer (CHANGES_REQUESTED opgelost)
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces Dag 3
- Gerelateerde pagina / route: /trace/:executionId
- Gerelateerde backend endpoints: GET /v1/traces/:executionId
- Gerelateerde design componenten: N/A (swap van bestaande pagina)
- Versie: 1.0

---

## Doel en scope

### Doel

De route `/trace/:executionId` gebruikte eerder de named export `TraceViewer` uit
`components/traces/TraceViewer.tsx` (134 regels, geen data-testid op root). Dit is vervangen door
de volwaardige page-implementatie in `pages/TraceViewer.tsx` (646 regels, data-testid op root).

Voordelen van de swap:

- Consistente page/component scheiding (pages = gerouteerde views)
- `data-testid="trace-viewer-page"` op root beschikbaar voor targeted tests
- Volledige Trace Explorer feature set (filters, sidebar, toolbar) nu actief via route

### In scope

- App.tsx: lazy import gewijzigd van `components/traces/TraceViewer` naar `pages/TraceViewer`
- App.tsx: component hernoemed van `TraceViewer` naar `TraceViewerPage` in import en JSX

### Buiten scope

- `pages/TraceViewer.tsx` zelf is niet gewijzigd (646L, al stabiel)
- `components/traces/TraceViewer.tsx` blijft bestaan (134L, wordt elders gebruikt)

---

## Implementatie

### App.tsx -- voor

```typescript
const TraceViewer = React.lazy(() =>
  import('./components/traces/TraceViewer').then((m) => ({ default: m.TraceViewer }))
);

<Route path="/trace/:executionId" element={
  <ProtectedRoute>
    <LazyWrapper><TraceViewer /></LazyWrapper>
  </ProtectedRoute>
} />
```

### App.tsx -- na

```typescript
const TraceViewerPage = React.lazy(() => import('./pages/TraceViewer'));

<Route path="/trace/:executionId" element={
  <ProtectedRoute>
    <LazyWrapper><TraceViewerPage /></LazyWrapper>
  </ProtectedRoute>
} />
```

---

## Trainingssamenvatting

### Flow 1: Trace openen via route

- Actor: Gebruiker of intern systeem met trace-link
- Voorwaarde: Gebruiker is ingelogd; executionId is geldig
- Actie: Navigeert naar `/trace/<executionId>`
- Systeemreactie: pages/TraceViewer laadt met volledige Trace Explorer feature set
- Succes: Trace zichtbaar met filters, sidebar en toolbar; root heeft `data-testid="trace-viewer-page"`
- Fout: Ongeldig executionId toont error state van de pagina
- Uitzondering: N/A

### Flow 2: Architecture test (import-linter)

- Actor: CI / architecture test
- Voorwaarde: Wijziging in App.tsx
- Actie: CI draait `TraceViewer.route.test.tsx`
- Systeemreactie: Test verifieert dat App.tsx `import('./pages/TraceViewer')` bevat, niet de component-variant
- Succes: Test GROEN na swap
- Fout: Test ROOD als App.tsx nog de component-variant importeert
- Uitzondering: N/A
