# ADR 016: ShadowCEO - Red Teaming and Adversarial Security

## Status
Accepted

## Context
Als een enterprise-grade AI orchestration platform, heeft SanskritiSetu te maken met:
- Complexe multi-agent workflows die fouten kunnen bevatten
- Mogelijke Byzantine faults (agents die incorrect of malafide gedrag vertonen)
- Security risks bij cross-department communicatie
- Failures die kunnen cascaden door het hele systeem

We hebben een mechanisme nodig dat continu het systeem analyseert op risico's voordat acties worden uitgevoerd.

## Decision
We implementeren een **ShadowCEO** component die als "red team" opereert:

1. **Parallel Risk Assessment**: ShadowCEO analyseert elke taak delegation parallel aan de normale flow
2. **Deterministische Risk Scoring**: Risico wordt berekend op basis van:
   - Task complexiteit (subtasks, dependencies)
   - Cross-department risico
   - Byzantine fault probability (historisch gedrag)
   - Cascade risk (impact op andere systemen)
3. **Veto Mechanisme**: ShadowCEO kan taken vetoen met verschillende risk levels:
   - `CRITICAL`: Altijd blokkeren, kan niet overridden worden
   - `HIGH`: Blokkeren, maar kan overridden worden met HITL
   - `MEDIUM/LOW`: Waarschuwing, maar doorlaten
4. **Threat Memory**: Leert van eerdere incidents en past risk thresholds aan

## Consequences

### Positive
- Proactieve risico detectie voordat schade wordt aangericht
- Audit trail van alle veto decisions
- Geautomatiseerde protectie tegen bekende threat patterns
- Transparantie in risk assessment (geen "black box")

### Negative
- Extra latency (~50-100ms) per taak delegation
- False positives kunnen legitime taken blokkeren
- Extra infrastructuur complexiteit

### Mitigations
- Veto override mogelijk voor HIGH risks (met HITL)
- Configurable risk thresholds per tenant
- Audit logging van alle veto decisions voor review

---

## Implementatiestatus Frontend

Geimplementeerd in SP-FE-2F (Dag 3+4, 2026-06-28/29).

| Component | Bestand | Status |
| --- | --- | --- |
| `ShadowCEOMonitor` pagina | `frontend/src/pages/redesign/ShadowCEOMonitor.tsx` | Geimplementeerd |
| `ShadowCEOAlertFeed` component | `frontend/src/components/prana/ShadowCEOAlertFeed.tsx` | Geimplementeerd |
| `useShadowCEOStore` (Zustand) | `frontend/src/lib/stores/useShadowCEOStore.ts` | Geimplementeerd |
| `governanceAlerts` types | `frontend/src/types/governanceAlerts.ts` | Geimplementeerd |

Route: `/shadow-ceo` onder `ProtectedRoute` + `PermissionGate requiredScope="governance:read"`.
Backend scope `GOVERNANCE_READ` geregistreerd in `src/core/auth/scopes.py` (SP-FE-2F Dag 4).
Feature spec: `docs/frontend/features/FE-PGS-026-shadow-ceo-monitor.md` (APPROVED).
User guide: `docs/user-guide/frontend/shadow-ceo-monitor.md`.

ShadowCEOAlertFeed toont severity-alerts met ADR-028 `status-*` tokens. `fetchAlerts()` roept `GET /api/v1/governance/alerts` aan -- volledig geimplementeerd (SP-FE-2F, commit 209ec8f1). Backend scope-enforcement via `require_scopes(OAuth2Scope.GOVERNANCE_READ)` toegevoegd aan alle 3 governance monitoring endpoints (2026-06-30). `governance:read` scope aanwezig in `user`-, `admin`- en `developer`-rol via `auth_service._get_role_scopes()`.
