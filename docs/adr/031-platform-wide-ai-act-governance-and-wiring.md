# ADR-031: Platform-Wide AI Act Governance and Wiring

## Status

Accepted -- 2026-05-26

### Status History
- 2026-05-26: Proposed (initial governance contract and route inventory)
- 2026-05-26: Accepted (after 6-sprint implementation, 30 evidence records, 40/40 matrix closure, all P0 gaps resolved)

### Sprint Completion Summary

| Sprint | Domain | Status | Key Deliverables |
|--------|--------|--------|------------------|
| Sprint 1 | Platform Baseline | DONE | Canonical governance contract, route inventory freeze (43 routes), deprecation policy, evidence model v1 |
| Sprint 2 | CVA | DONE | CVA ingress governance design, chat/stream route wiring, legacy sunset controls |
| Sprint 3 | Focus Builder | DONE | Embedded policy gap scan, AI suggest/generate governance hooks, remote parity contract, proxy compliance checks |
| Sprint 4 | ALS | DONE | ALS risk analysis, /als/tasks gate integration, /als/broadcast gate enforcement with role restrictions, evidence standardization |
| Sprint 5 | Agentic | DONE | Tenant authority hardening (auth-context-only), /agentic/generate governance, WS builder sequence-safe governance, security hardening tests |
| Sprint 6 | Audit Readiness | DONE | Matrix closure pass (40/40 routes), governance monitoring/red-team validation, final evidence bundle (30 records), program GO |

## Context

ADR-027 established a strong Co-Pilot governance model (Agent Council with officer-based
deliberation, hash-chain audit, HITL escalation). That implementation is robust for Co-Pilot
surfaces, but SanskritiSetu exposes additional AI execution surfaces (CVA, Focus Builder,
ALS, Agentic endpoints, WebSockets) that are not uniformly routed through the same
decision pipeline.

This creates a control asymmetry:

1. Some pathways already apply deterministic governance checks.
2. Some pathways rely on legacy or partial checks.
3. Some pathways can execute meaningful AI actions without Council-grade deliberation,
   unified audit semantics, and standardized transparency behavior.

For EU AI Act readiness, this asymmetry is a platform risk, even when individual modules are
well implemented. We need one platform decision that defines mandatory governance controls
for every AI execution surface, regardless of product area.

### External guidance used

This ADR aligns with:

- EU AI Act risk-based obligations (transparency, traceability, human oversight, robustness)
  as summarized by the European Commission policy pages.
- Enterprise agent governance guidance from Turbotic (autonomy ladder, agent contract,
  approval controls, tool mediation, auditability, phased rollout).
- NIST AI RMF operating model (Govern, Map, Measure, Manage) as a practical structure for
  continuous risk control.
- ADR best practices (single decision record with explicit context, trade-offs, and
  consequences).

## Decision

We adopt a mandatory platform governance contract for all AI entrypoints.

### 1. Canonical governance pipeline

Every AI action proposal that can influence business state, user guidance, or external
communication MUST flow through:

1. Identity and tenant resolution (JWT/context only; no client tenant authority)
2. Proposal normalization (action type, params, risk metadata, model metadata)
3. Policy and safety checks (deterministic)
4. Council or Gatekeeper-level decision (allow/modify/hitl/defer/block)
5. Tamper-evident audit write
6. Controlled execution or deferral
7. User-facing transparency artifacts (AI origin, rationale, contestability where relevant)

### 2. Autonomy ladder as deployment control

All AI capabilities are classified by autonomy level:

- L1 Assistant: read/draft/recommend only, no side effects
- L2 Copilot: proposes actions, explicit human approval for side effects
- L3 Controlled Agent: low-risk bounded autonomy under strict thresholds
- L4 Autonomous Agent: end-to-end automation with rollback and continuous monitoring

No surface may move to a higher level without explicit approval criteria: eval suite pass,
red-team pass, observability coverage, rollback path, and owner sign-off.

### 3. Agent contract required per execution surface

Each AI route family MUST define and maintain an "agent contract" that includes:

- allowed inputs and outputs
- allowed tools and forbidden tools
- actions requiring approval
- never-allowed actions
- data classification scope
- audit fields and retention policy
- escalation owner and incident owner

### 4. Platform wiring policy

- New AI endpoints are not production-eligible unless they use the canonical governance
  pipeline.
- Legacy/deprecated endpoints can remain temporarily only if marked and monitored, with an
  explicit sunset plan.
- Remote/proxy modes (for example Focus Builder remote mode) are only compliant when the
  downstream service enforces equivalent controls and emits auditable evidence.

### 5. Minimal evidence package for compliance review

Every AI surface must produce evidence for:

- traceability (who, when, model, tool calls, decision, outcome)
- human oversight behavior (where required)
- transparency behavior (user informed about AI interaction/output origin)
- post-deploy monitoring (safety, quality, latency, cost, policy violations)

## Current State Audit (Wiring Snapshot)

This snapshot is based on direct route and service inspection.

Companion detailed matrix:

- docs/audits/ai-route-compliance-matrix-2026-05-26.md

### A. Copilot surfaces

Status: Wired (primary paths); Context Engine gedefinieerd 2026-05-27, implementatie pending

- `/api/v1/copilot/turn` routes through `CopilotService.handle_turn()` and Council deliberation.
- `/ws/copilot/chat` uses canonical Co-Pilot WS service path.
- Right-to-explanation and audit endpoints are present under `/api/v1/copilot/audit`.
- **Context Engine retrieval audit** (ADR-027 §11, ADR-019 §2026-05-27): gedefinieerd maar nog niet geïmplementeerd; vereist `RETRIEVAL_PERFORMED` logging en `CROSS_TENANT_LEAKAGE_DETECTED` monitoring

Residual risk:

- Deprecated Copilot surfaces still exist (intent parser and legacy ai-copilot suggest endpoint).
  They must remain non-authoritative and sunset by policy date.
- Context Engine is niet yet live; Council deliberates zonder retrieved context tot Fase 1 (ADR-027 §15) is voltooid

### B. Focus Builder surfaces

Status: Partially wired

- Embedded v1 execute flow path includes Council deliberation before execution.
- Proxy mode can forward to remote Focus Builder service; compliance then depends on remote
  service parity.

Residual risk:

- Remote mode parity controls are not proven by this code path alone.

### C. CVA surfaces

Status: Wired (fixed 2026-05-26)

- Primary mounted CVA router exposes `/api/v1/cva/*` endpoints.
- CVA chat implementation routes through `AgentCouncil.deliberate()` via
  `require_council_approval()` helper (replaced legacy `OversightGate`).

Residual risk:

- None critical. Legacy `cva_chat.py` OversightGate path removed from active flow.

### D. ALS surfaces

Status: Wired (fixed 2026-05-26)

- ALS API exists (`/api/v1/als/*`) with tenant-scoped orchestrator and signal bus patterns.
- `/als/tasks` and `/als/broadcast` now enforce `AgentCouncil.deliberate()` via
  `require_council_approval()` before orchestrator delegation.
- ALS enterprise Gatekeeper remains as downstream component; Council gate sits at ingress.

Residual risk:

- Policy enforcement depends on downstream usage patterns, not guaranteed at ingress.

### E. Agentic flow surfaces

Status: Partially wired (improved 2026-05-26)

- Agentic `/generate` now enforces `AgentCouncil.deliberate()` via
  `require_council_approval()` before LLM execution.
- Agentic WS `/builder` tenant authority fixed: `tenant_id` comes from auth context ONLY;
  client payload fallback removed.

Residual risk:

- WS message-level Council deliberation not yet implemented (P2 enhancement).

## Consequences

### Positive

- One enforceable governance standard across all AI surfaces.
- Clear migration target from partial/legacy wiring to uniform compliance behavior.
- Stronger audit posture for EU AI Act, GDPR explanation rights, and enterprise due diligence.

### Negative

- Additional integration work to normalize CVA, ALS, and Agentic pathways.
- Possible latency overhead where governance checks are introduced on hot paths.
- Requires disciplined deprecation management to remove bypass-prone legacy routes.

## Migration Plan

### Phase 1 (Immediate hardening) — COMPLETED 2026-05-26

1. ✅ Declare canonical AI entrypoints per domain (Copilot, CVA, Focus Builder, ALS, Agentic).
2. ✅ Freeze creation of new non-canonical AI routes.
3. ✅ Add explicit compliance notes on all deprecated AI endpoints with sunset dates.

### Phase 2 (Wiring normalization) — COMPLETED 2026-05-26

1. ✅ CVA: route mounted chat path through canonical governance pipeline.
2. ✅ ALS: enforce deterministic policy decision at API ingress (Gatekeeper/Council bridge).
3. ✅ Agentic flows: add proposal normalization plus governance gate before tool-capable actions.
4. ✅ Focus Builder remote mode: define and verify remote parity contract.

### Phase 4 (Context Engine Governance) — Gedefinieerd 2026-05-27

De Context Engine (ADR-027 §11-15) introduceert een nieuw AI oppervlak dat
retrieval-augmented generation uitvoert voordat de Council wordt geraadpleegd.
Dit vereist aanvullende governance:

1. **Retrieval audit verplicht**: Elke turn produceert `RETRIEVAL_PERFORMED` audit event (ADR-019 §2026-05-27)
2. **Cross-tenant leakage detectie**: `CROSS_TENANT_LEAKAGE_DETECTED` is severity CRITICAL; PrivacyOfficer valideert retrieved context (ADR-027 §11.5)
3. **Capability Registry governance**: `UnifiedCapabilityRegistry` changes triggeren Council cache flush; agent discovery is niet meer hardcoded (ADR-027 §12)
4. **Multi-surface uniformiteit**: Focus Builder, CVA, en Agentic gebruiken dezelfde `AIContextEngine` en vallen onder identieke retrieval audit (ADR-027 §14)
5. **Evidence**: Nieuwe evidence records voor Context Engine compliance
   - `EVID-20260527-context-engine-audit` — retrieval events traceerbaar
   - `EVID-20260527-ucr-governance` — UnifiedCapabilityRegistry change audit
   - `EVID-20260527-cross-tenant-negative` — 24u monitoring zonder leakage detectie

### Phase 3 (Evidence and operations) — COMPLETED 2026-05-26

1. ✅ Add per-surface compliance dashboards: approvals, blocks, deferrals, policy violations.
2. ✅ Add regression test matrix by surface: happy path, unsafe prompt injection, approval
   required action, cross-tenant isolation.
3. ✅ Add periodic governance drift audit (scheduled) with route-level wiring report.

### Evidence Package

All evidence is registered in `docs/Aiact 2026/evidence/EVIDENCE_INDEX.md`:

- 30 evidence records across 6 sprints
- All records at status READY_FOR_REVIEW or higher
- Cross-referenced with compliance matrix rows
- Evidence validity rule: (1) exists in evidence/, (2) registered in index, (3) matrix references same ID

### Program Closure Criteria (All Met)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| All 40 matrix routes have required gate documented | ✅ | Matrix closure pass (EVID-20260526-matrix-closure-pass) |
| All P0 gaps closed in code | ✅ | CVA normalized, Agentic tenant_id removed, Focus Builder parity enforced |
| Automated tests cover all governed paths | ✅ | 42 unit tests + 4 integration tests PASS |
| Audit evidence emitted and queryable | ✅ | Hash chain + council_decisions + officer_verdicts tables |
| Owner sign-off recorded | ✅ | Laag A/B reviews APPROVED for all sprint days |
| Red-team validation complete | ✅ | EVID-20260526-red-team-robustness |
| Final evidence bundle ready | ✅ | EVID-20260526-final-evidence-bundle |

## Related ADRs

- ADR-003 Tenant boundary via JWT
- ADR-005 Database hardening (RLS + search index tenant isolation)
- ADR-014 Observability (Context Engine metrics)
- ADR-015 Agent/tool execution safety (capability discovery interface)
- ADR-017 Deterministic Gatekeeper
- ADR-019 Audit logging and hash chain (retrieval audit events)
- ADR-022 Agent learning (retrieval optimization learning loop)
- ADR-023 Agent orchestration (Unified Capability Registry integration)
- ADR-025 Digital Twin architecture (Twin-Copilot context interface)
- ADR-026 Digital Twin production hardening
- ADR-027 Copilot Agent Council (Context Engine, Capability Registry, Multi-Surface Contract)

## Bekende implementatiebug (GS-FE-1) — vastgesteld 2026-05-28

**Bestand:** `frontend/src/lib/hooks/useExplainability.ts`

**Probleem:** De echte API-call naar `/api/v1/council/explain/{decisionId}` (de
right-to-explanation endpoint die in dit ADR als §S6-evidence is gedocumenteerd) is
volledig uitgecommentarieerd. De hook gebruikt uitsluitend:

```typescript
await new Promise(resolve => setTimeout(resolve, 500))  // gesimuleerde netwerkvertraging
return generateMockExplainability()                     // vaste template-tekst, geen echte data
```

`generateMockExplainability()` retourneert altijd dezelfde hardcoded uitleg, ongeacht
welke beslissing de gebruiker opvraagt.

**Gevolgen:**
- AI Act Art. 13 (transparantie over geautomatiseerde beslissingen) is onmogelijk
  aan te tonen: de uitleg is nep
- Het Sprint S6 "audit readiness" programma dat dit ADR markeert als GO voor
  2 augustus 2026 is hiermee incomplete
- Bewijsrecord #28 ("right-to-explanation API operational") klopt niet voor de
  frontend-surface

**Vereiste fix:**

```typescript
// frontend/src/lib/hooks/useExplainability.ts
export async function fetchExplainability(decisionId: string): Promise<ExplainabilityData> {
  const response = await fetch(
    `/api/v1/council/explain/${decisionId}`,
    { credentials: "include" }
  )
  if (!response.ok) {
    throw new Error(`Explainability API failed: ${response.status}`)
  }
  return await response.json() as ExplainabilityData
}
```

Verwijder `generateMockExplainability()` en de `setTimeout` simulatie volledig.

**Prioriteit:** P0 (GS-FE-1) — AI Act Art. 13 compliance is niet aantoonbaar zonder
deze fix.

Volledig fix-plan: `docs/frontend/pages/22-platform-p0-blockers-scope.md` (GS-FE-1).

---

## Implementatie-bevindingen -- Architectuur Audit 2026-05-31

### WE-014 [HIGH] Notification REST router niet geregistreerd in productie router_registry

**Situatie:** Het platform beschikt over een `NotificationDispatcher` en `WSPusher`.
Frontend roept `/api/v1/notifications/*` aan voor notificatiebeheer.
**Werkelijkheid:** `src/core/api/router_registry.py` (de hoofd-productieregistry gebruikt door
`src/main.py`) bevat geen import of `include_router` aanroep voor een notification router.
Alle frontend aanroepen naar `/api/v1/notifications`, `/api/v1/notifications/mark-all-read`
etc. retourneren 404.
**Bewijs:** grep op `notification` in `router_registry.py`: geen resultaat.
`frontend/src/lib/api/notifications.ts`: roept `/api/v1/notifications` aan.
**Impact:** Notificatiemanagement-UI volledig non-functioneel in productie.
AI Act Art. 13 transparantie-notificaties bereiken de gebruiker niet.
**Sprint:** SP-WE-02

### WE-015 [MEDIUM] Pack feedback endpoints alleen geregistreerd in setup-mode registry

**Situatie:** Pack feedback endpoints zijn geimplementeerd in SP-A02 (CLOSED 2026-05-28).
**Werkelijkheid:** `pack_feedback_endpoints.py` is geimporteerd in
`src/core/api/setup/router_registry.py` (setup-mode, gated achter `APP_SETUP_MODE=true`)
maar NIET in `src/core/api/router_registry.py` (productie). Alle frontend WAVE_B_PATHS
pack feedback aanroepen retourneren 404 in productie.
**Bewijs:** `src/core/api/setup/router_registry.py` (bevat pack_feedback import),
`src/core/api/router_registry.py` (geen pack_feedback import).
**Impact:** Pack feedback functionaliteit is volledig geimplementeerd maar niet bereikbaar
in productie. SP-A02 is incorrect als CLOSED geclassificeerd.
**Sprint:** SP-WE-09

---

## Changelog

| Date | Version | Change |
| --- | --- | --- |
| 2026-05-26 | 1.0 | Initial acceptance; 6 sprints, 30 evidence records, 40/40 matrix closure |
| 2026-05-27 | 1.1 | Phase 4 (Context Engine Governance) toegevoegd; Copilot surfaces status bijgewerkt; Related ADRs uitgebreid |
| **2026-05-28** | **1.2** | **GS-FE-1 bug gedocumenteerd: useExplainability.ts echte API-call uitgecommentarieerd; mock als enige pad; AI Act Art. 13 compliance onmogelijk; fix-patroon vastgelegd** |
| **2026-05-31** | **1.3** | **WE-014/015 gedocumenteerd: notification router niet in productie, pack feedback router verkeerd geregistreerd. Fix in SP-WE-02 en SP-WE-09.** |
