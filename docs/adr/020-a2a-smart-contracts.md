# ADR 020: A2A Smart Contracts - Agent-to-Agent Agreements

## Status
Accepted

## Context
Agents moeten met elkaar kunnen samenwerken zonder centrale coordinator:
- Autonome onderhandeling van taken
- Garantie van uitbetaling (Prana tokens)
- Duidelijke afspraken over deadlines en deliverables
- Mogelijkheid tot disputes en retries

We hebben een "smart contract" systeem nodig voor agents.

## Decision
We implementeren **A2A Smart Contracts** met:

1. **Contract States**: HARD state machine met transitions:
   ```
   PROPOSED → AGREED → EXECUTING → SETTLED
      ↓           ↓         ↓
   REJECTED   COUNTERED   FAILED → RETRYING
   ```

2. **Schema Registry**: Geverifieerde data schemas met semver:
   - Schema hash (SHA-256) voor integriteit
   - Backward compatibility checks
   - Domain-based namespacing (finance.invoice@1.2.0)

3. **Settlement Engine**: Automatische Prana transfer bij contract completion:
   - Escrow tijdens execution
   - Release bij SETTLED
   - Refund bij FAILED (na max retries)

4. **State Machine Rules**:
   - Alleen bepaalde actors mogen transitions triggeren
   - PROPOSED → EXECUTING is NOOIT toegestaan (moet via AGREED)
   - Max 3 retries voor FAILED contracts

## Consequences

### Positive
- Autonome agent samenwerking zonder single point of failure
- Duidelijke afspraken en enforcement
- Automatische settlement (geen disputes)
- Audit trail van alle contract interacties

### Negative
- Complex state machine logic
- Risico van "stuck" contracts (bijv. in COUNTERED state)
- Prana escrow locks resources tijdens execution

### Mitigations
- Timeout mechanismes (auto-fail na deadline)
- Circuit breaker voor hanging contracts
- ShadowCEO review voor high-value contracts

---

## Implementatiestatus Frontend

Geimplementeerd in SP-FE-2F (Dag 2+4, 2026-06-28/29).

| Component | Bestand | Status |
| --- | --- | --- |
| `A2AContracts` pagina | `frontend/src/pages/redesign/A2AContracts.tsx` | Geimplementeerd |
| `A2AContractFlow` component (XYFlow) | `frontend/src/components/prana/A2AContractFlow.tsx` | Geimplementeerd |

Route: `/prana/contracts` onder `ProtectedRoute` + `PermissionGate requiredScope="prana:read"`.
Backend scope `PRANA_READ` geregistreerd in `src/core/auth/scopes.py` (SP-FE-2F Dag 4).
Feature spec: `docs/frontend/features/FE-PGS-025-a2a-contracts.md` (APPROVED).

A2AContractFlow visualiseert de state machine (PROPOSED -> AGREED -> EXECUTING -> SETTLED -> FAILED) als XYFlow-diagram. Contract-nodes tonen Prana-escrow bedragen en deadlines.
