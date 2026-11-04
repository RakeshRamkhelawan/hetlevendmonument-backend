# ADR 021: Prana Economy - Token-based Resource Management

## Status
Accepted

## Context
We hebben een mechanisme nodig om:
- Resource usage te limiteren (prevent abuse)
- Prioriteit te geven aan belangrijke taken
- Cross-department resource allocation te managen
- Budgettering per tenant/department te ondersteunen

We introduceren een intern "token" systeem genaamd **Prana**.

## Decision
We implementeren een **Prana Economy**:

1. **Prana als Resource Token**:
   - 10,000 Prana per department per tenant
   - Non-transferable (binnen department)
   - Geen externe value (intern systeem only)

2. **Cost Structure**:
   | Agent Type | Cost per Execution |
   |------------|-------------------|
   | ml | 10 Prana |
   | llm | 50 Prana |
   | vision | 100 Prana |
   | hybrid | 75 Prana |

3. **Budget Management**:
   - Real-time tracking per department
   - Alerts bij < 10% remaining
   - Auto-blocking bij 0 Prana

4. **Recharge Mechanisme**:
   - Dagelijkse reset naar 10,000 (time-based)
   - Of op basis van tenant subscription level
   - ChiefOrchestrator kan emergency allocations doen

## Consequences

### Positive
- Voorspelbare resource usage
- Fair sharing tussen departments
- Automated throttling bij high load
- Cost attribution voor reporting

### Negative
- Complexiteit van token economie
- Risk van "starvation" (department zonder Prana kan niets doen)
- Niet alle taken zijn gelijk qua resource usage (moeilijk te schatten)

### Mitigations
- Grace period (negatieve balans toegestaan korte tijd)
- Emergency Prana allocatie door admins
- Cost estimation vooraf (voorspelling)
- Tenant-level Prana purchasing (upsell mogelijkheid)

---

## Implementatiestatus Frontend

Geimplementeerd in SP-FE-2F (Dag 1+4, 2026-06-28/29).

| Component | Bestand | Status |
| --- | --- | --- |
| `PranaDashboard` pagina | `frontend/src/pages/redesign/PranaDashboard.tsx` | Geimplementeerd |
| `PranaGauge` component (Recharts RadialBarChart) | `frontend/src/components/prana/PranaGauge.tsx` | Geimplementeerd |

Route: `/prana` onder `ProtectedRoute` + `PermissionGate requiredScope="prana:read"`.
Backend scopes `PRANA_READ`, `PRANA_MANAGE` geregistreerd in `src/core/auth/scopes.py` (SP-FE-2F Dag 4).
Feature spec: `docs/frontend/features/FE-PGS-024-prana-dashboard.md` (APPROVED).
User guide: `docs/user-guide/frontend/prana-dashboard.md`.

PranaDashboard toont live token balances per department, allocatie-overzicht, alerts bij < 10% en de emergency-allocatie actie. PranaGauge gebruikt Recharts RadialBarChart met ADR-028 dark-mode tokens (`bg-slate-900`, `text-slate-100`).
