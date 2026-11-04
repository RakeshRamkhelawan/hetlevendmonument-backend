# FE-CMP-038 -- CritiqueChart Telemetrie Component

## Metadata

- **Sprint**: SP-AGT-007, Dag 1 van 1
- **Status**: IMPLEMENTED
- **Datum**: 2026-06-27
- **Auteur**: Claude (SP-AGT-007 implementatie-agent)

---

## Samenvatting

Nieuw `CritiqueChart`-component (Recharts LineChart) dat hourly critique-scores ophaalt
via `/api/v1/orchestrate/telemetry`. Gemount als 5e tab ("Telemetrie") in `AgentDetailModal`.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `frontend/src/components/agents/CritiqueChart.tsx` | NIEUW -- CritiqueChart component |
| `frontend/src/components/AgentDetailModal.tsx` | Import CritiqueChart + 5e tab (grid-cols-4 -> grid-cols-5) |
| `frontend/src/components/agents/__tests__/CritiqueChart.test.tsx` | NIEUW -- 4 Vitest tests |

---

## Componentgedrag

| Toestand | Render |
|---|---|
| `isLoading: true` | `<div role="status">` met loading tekst |
| `data: []` (leeg) | Tekst "Geen telemetrie beschikbaar..." |
| `data: [...]` | Agentsnamen boven de grafiek + Recharts LineChart |

---

## Query

- `queryKey: ['/orchestrate/telemetry', hours]`
- `queryFn`: fetch `/api/v1/orchestrate/telemetry?hours={hours}`
- Default: `hours = 24`

---

## Trainingssamenvatting

**Actor**: Gebruiker in AgentDetailModal  
**Voorwaarde**: Agent is geselecteerd, "Telemetrie" tab is actief  
**Actie**: Tab wordt geopend  
**Systeemreactie**: CritiqueChart fetcht de laatste 24 uur critique-scores  
**Succes**: Lijndiagram met agentsnamen zichtbaar  
**Fout**: Geen data -> "Geen telemetrie beschikbaar" bericht  
**Uitzonderingen**: Tijdens laden: status-indicator zichtbaar

---

## Testbewijs

```
CritiqueChart > renders loading state when data is loading PASSED
CritiqueChart > renders chart when data is available PASSED
CritiqueChart > renders empty state when data is empty PASSED
CritiqueChart > calls useQuery with telemetry endpoint and hours parameter PASSED
```
