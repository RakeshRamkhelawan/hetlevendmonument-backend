# Frontend Feature Specification

## Metadata

- Feature ID: FE-PGS-028
- Feature naam: Digital Twin route wiring, ADR-026 consent gate en dynamische OODA fase
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 3
- Reviewer: code-reviewer + quality-reviewer (CHANGES_REQUESTED opgelost)
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces Dag 3
- Gerelateerde pagina / route: /digital-twin
- Gerelateerde backend endpoints:
  - GET /v1/digital-twin/profile
  - GET /v1/digital-twin/ooda-metrics
  - GET /v1/digital-twin/consent (useTwinConsent)
  - POST /v1/digital-twin/consent
  - DELETE /v1/digital-twin/profile
- Gerelateerde design componenten: OODATimeline (FE-CMP-042), GDPRConsentPanel, PermissionGate
- Versie: 1.0

---

## Doel en scope

### Doel

Drie gerelateerde verbeteringen aan de DigitalTwin pagina:

1. Route wiring: /digital-twin als top-level route met PermissionGate (twin:read scope) en BusinessSidebar nav-item
2. ADR-026 consent gate: twin-profile-card alleen zichtbaar als consent_status === 'active'; GDPRConsentPanel + OODATimeline + portability altijd zichtbaar
3. Dynamische OODA fase: computeActivePhase berekent de actieve fase op basis van de OODAPhaseMetric met de hoogste frictionScore

### In scope

- App.tsx: lazy import + ProtectedRoute + PermissionGate route voor /digital-twin
- BusinessSidebar.tsx: Brain icon + Digital Twin nav-item (15 items totaal)
- DigitalTwin.tsx: useTwinConsent import, consent gate JSX, computeActivePhase functie, loading guard
- BusinessSidebar.test.tsx: update 14 -> 15 nav items
- DigitalTwin.test.tsx + DigitalTwin.dark.test.tsx: consent mock branch toegevoegd

### Buiten scope

- Backend consent API (al beschikbaar)
- ErasureModal, MetricBar, SyncStateBadge (ongewijzigd)

---

## Implementatie

### Route (App.tsx)

```typescript
const DigitalTwin = React.lazy(() => import('./pages/DigitalTwin'));

<Route path="/digital-twin" element={
  <ProtectedRoute>
    <PermissionGate requiredScope="twin:read" fallback={<Navigate to="/dashboard" replace />}>
      <LazyWrapper><DigitalTwin /></LazyWrapper>
    </PermissionGate>
  </ProtectedRoute>
} />
```

### BusinessSidebar NAV_ITEMS

```typescript
{ to: '/digital-twin', label: 'Digital Twin', icon: Brain },
```

### ADR-026 consent gate (DigitalTwin.tsx)

```typescript
const consentQuery = useTwinConsent();
const consentStatus = consentQuery.data?.status;

if (profileQuery.isLoading || oodaQuery.isLoading || consentQuery.isLoading) { ... }

{profile && (
  <div className="grid ...">
    {consentStatus === 'active' ? (
      <div data-testid="twin-profile-card">...</div>
    ) : (
      <div data-testid="consent-required-prompt">...</div>
    )}
    <div data-testid="twin-consent-card"><GDPRConsentPanel ... /></div>
  </div>
)}
```

### computeActivePhase (DigitalTwin.tsx)

```typescript
function computeActivePhase(metrics: OODAPhaseMetric[]): OODATimelinePhase {
  if (!metrics || metrics.length === 0) return "Observe";
  const winner = metrics.reduce(
    (max, m) => (m.frictionScore > max.frictionScore ? m : max),
    metrics[0],
  );
  const MAP: Record<string, OODATimelinePhase> = {
    OBSERVE: "Observe",
    ORIENT: "Orient",
    DECIDE: "Decide",
    ACT: "Act",
  };
  return MAP[winner.phaseName] ?? "Observe";
}
```

---

## Trainingssamenvatting

### Flow 1: Navigeren naar Digital Twin

- Actor: Ingelogde gebruiker met twin:read scope
- Voorwaarde: Gebruiker is ingelogd, heeft twin:read in JWT claims
- Actie: Klikt op "Digital Twin" in de BusinessSidebar
- Systeemreactie: Navigeert naar /digital-twin, laadt DigitalTwin pagina
- Succes: Digital Twin Dashboard gerenderd met profiel, consent controls, OODA indicator
- Fout: Zonder twin:read scope wordt geredirect naar /dashboard
- Uitzondering: N/A

### Flow 2: Consent gate actief

- Actor: Gebruiker met niet-actieve consent
- Voorwaarde: useTwinConsent retourneert status !== 'active'
- Actie: Gebruiker opent /digital-twin
- Systeemreactie: twin-profile-card verborgen, consent-required-prompt getoond; GDPRConsentPanel + OODATimeline altijd zichtbaar
- Succes: Gebruiker ziet hint om consent in te schakelen
- Fout: N/A
- Uitzondering: Bij consent loading toont pagina laad-spinner

### Flow 3: Dynamische OODA fase

- Actor: System (backend data)
- Voorwaarde: GET /v1/digital-twin/ooda-metrics retourneert OODAPhaseMetric[] met frictionScore waarden
- Actie: Component rendert na data-fetch
- Systeemreactie: computeActivePhase berekent fase met hoogste frictionScore; OODATimeline toont actieve fase
- Succes: OODATimeline.activePhase = fase met hoogste frictionScore (Title Case)
- Fout: Lege metrics -> fallback activePhase="Observe"
- Uitzondering: Onbekende phaseName -> fallback 'Observe'
