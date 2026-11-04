# Frontend Feature Specification

## Metadata

- Feature ID: FE-TAUD-001
- Feature naam: ToolAuditLogs gekoppeld aan de DB-backed tool-audit read-route (BPA-009)
- Status: Implemented
- Auteur: Implementatie-agent (Dag 7)
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/frontend/review/review-FE-TAUD-001.md`
- Datum: 2026-07-13
- Gerelateerde pagina / route: `/tool-audit-logs` (ToolAuditLogs)
- Gerelateerde backend endpoints: `GET /api/v1/tool-audit-logs` (BE-TAUD-001)
- Versie: 1.0

## Doel en scope

### Doel

`ToolAuditLogs.tsx` las een lege lokale zustand-store i.p.v. echte data. Deze feature koppelt het
scherm aan de nieuwe DB-backed read-route zodat de tenant-audit-logs echt getoond worden.

### In scope

- `useToolAuditLogs` hook (apiClient GET `/api/v1/tool-audit-logs`, abortable).
- `ToolAuditLogs.tsx` hydrateert de store uit de API + loading/error-states.

### Out of scope

- Write-kant (al DB-backed). Server-side paginering (client-side filter/paging blijft).

## Frontend inventory

| ID | Naam | Type | Locatie | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| FE-TAUD-001 | ToolAuditLogs API-koppeling | Flow | `frontend/src/pages/redesign/ToolAuditLogs.tsx` | Wijziging | FE-TAUD-001 |
| FE-HK-060 | useToolAuditLogs hook | React hook | `frontend/src/hooks/useToolAuditLogs.ts` | Nieuw | FE-TAUD-001 |

## Detaildocumentatie

### [FE-HK-060] useToolAuditLogs

- Type: React hook (data-fetch). Locatie: `frontend/src/hooks/useToolAuditLogs.ts`.
- Technisch: `apiClient.get<ToolAuditResponse>("/api/v1/tool-audit-logs?limit=&offset=")`, AbortController-
  cleanup, retourneert `{data, total, isLoading, error}`.
- States: loading / error / success / empty.

### [FE-TAUD-001] ToolAuditLogs koppeling

- Locatie: `frontend/src/pages/redesign/ToolAuditLogs.tsx`.
- Technisch: hydrateert de integrations-store (`setAuditLogs`) met de gemapte API-rijen; rendering,
  filter, paginering en selectie blijven op de store. Loading-state (`loading-state`) en fout-state
  (`fetch-error-state`, `role="alert"`) toegevoegd.
- Statusmapping: `success` -> `SUCCESS`, anders `FAILED` (store-union is tweewaardig; rijkere statussen
  vergen een union-verbreding -- gedocumenteerde follow-up, display-only).

## Acceptatiecriteria

- Bij data toont het scherm de tenant-audit-rijen (via de store, gehydrateerd uit de API).
- Tijdens laden verschijnt de loading-state; bij een fetch-fout de fout-state (geen crash).
- Geen data -> bestaande empty-state.

## Trainingssamenvatting

### Flow 1: Tool-audit-logs bekijken

- Actor: ingelogde tenant-admin op `/tool-audit-logs`.
- Voorwaarde: geauthenticeerd; backend-route beschikbaar.
- Actie: opent de pagina.
- Systeemreactie: `useToolAuditLogs` haalt de logs op; de store wordt gehydrateerd; de tabel rendert.
- Succesrespons: audit-rijen zichtbaar met filter/paginering.
- Foutrespons: fetch-fout -> `fetch-error-state` (nette melding, geen crash); leeg -> empty-state.
- Uitzonderingen: alleen lezen; write-kant ongemoeid.

## Handleidingstekst

Zie `docs/user-guide/frontend/tool-audit-logs-wiring.md`.

## Definition of Done

- [x] Feature gebouwd; hook + koppeling + loading/error
- [x] vitest 37 passed + tsc type-check clean (na npm ci in de worktree)
- [x] Trainingssamenvatting aanwezig; review APPROVED; user-guide aanwezig
