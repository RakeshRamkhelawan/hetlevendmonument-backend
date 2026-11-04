# Frontend Feature Specification

## Metadata

- Feature ID: FE-CMP-043
- Feature naam: TraceStepList -- uitklapbare stap-lijst met status-\* tokens
- Status: Implemented
- Auteur: Implementatie-agent SP-FE-2G Dag 3
- Reviewer: code-reviewer + quality-reviewer (CHANGES_REQUESTED opgelost)
- Datum: 2026-06-29
- Gerelateerde user story / ticket: SP-FE-2G Digital Twin & Traces Dag 3
- Gerelateerde pagina / route: Herbruikbaar component (gebruik in trace-viewer context)
- Gerelateerde backend endpoints: N/A (puur stateless component)
- Gerelateerde design componenten: ADR-028 status-\* tokens, cn() utility
- Versie: 1.0

---

## Doel en scope

### Doel

Stateless herbruikbare component die een lijst van trace-stappen toont met:

- ADR-028 status tokens (success/error/pending)
- Uitklapbare detail-sectie per stap (toggle via click + keyboard)
- Hash-badge (afgekorte eerste 8 tekens)
- Unieke data-testid per stap en per hash-badge

### In scope

- `frontend/src/components/twin/TraceStepList.tsx` (nieuw)
- `frontend/src/components/twin/__tests__/TraceStepList.test.tsx` (nieuw, 6 unit tests)

### Buiten scope

- Backend trace API integratie
- Paginering

---

## Implementatie

### Interface

```typescript
export interface TraceStep {
  id: string;
  label: string;
  status: "success" | "error" | "pending";
  hash?: string;
  detail?: string;
}
```

### Status tokens (ADR-028)

| Status  | Klassen                                    |
| ------- | ------------------------------------------ |
| success | `bg-status-success/20 text-status-success` |
| error   | `bg-status-error/20 text-status-error`     |
| pending | `bg-status-info/20 text-status-info`       |

### Toegankelijkheid

- Uitklapbare stap: `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space)
- cn() gebruikt voor klasse-conflict-resolving (bg-\* merging)
- Unieke testids: `data-testid={`trace-step-${step.id}`}` en `data-testid={`hash-badge-${step.id}`}`

---

## Trainingssamenvatting

### Flow 1: Stap bekijken

- Actor: Gebruiker die een trace raadpleegt
- Voorwaarde: TraceStepList is gemonteerd met een array van TraceStep objecten
- Actie: Gebruiker ziet de lijst van stappen
- Systeemreactie: Elke stap toont label en status-kleur; hash-badge zichtbaar als step.hash aanwezig
- Succes: Alle stap-labels zichtbaar, status-tokens correct toegepast
- Fout: Lege array -> lege lijst (geen error)
- Uitzondering: N/A

### Flow 2: Detail uitklappen via klik

- Actor: Gebruiker
- Voorwaarde: Stap heeft `detail` veld ingevuld
- Actie: Klikt op de stap
- Systeemreactie: Detail-sectie toont de tekst van step.detail
- Succes: Detail zichtbaar na klik; tweede klik verbergt detail
- Fout: N/A
- Uitzondering: Stap zonder detail is niet klikbaar (geen role="button")

### Flow 3: Detail uitklappen via toetsenbord

- Actor: Toetsenbordgebruiker
- Voorwaarde: Stap heeft `detail` veld; element heeft focus via Tab
- Actie: Drukt Enter of Space
- Systeemreactie: Detail-sectie toggelt (zelfde gedrag als klik)
- Succes: Keyboard-toegankelijk conform WCAG 2.1 SC 2.1.1
- Fout: N/A
- Uitzondering: N/A
