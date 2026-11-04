# Review BE-SVC-040: CVA Council Gate

**Sprint:** SP-CVA-SEC dag 1
**Reviewer:** code-reviewer + security-reviewer subagents
**Datum:** 2026-06-20
**Status:** APPROVED WITH MINOR ISSUES

---

## Oordeel: APPROVED WITH MINOR ISSUES

Geen CRITICAL of HIGH bevindingen. Twee minors zijn opgelost voor de commit.

---

## Bevindingen

### FA-001 (MINOR -- opgelost)
**Laag:** 1 - Code
**Bevinding:** Bestaande tests in test_sp_cva_comp_audit.py en test_sp_cva_comp_metadata.py
hadden geen mock voor build_council/require_council_approval, wat de echte council activeerde.
**Actie:** Mocks toegevoegd aan 5 bestaande tests. Regressie opgelost.

### FA-002 (MINOR -- opgelost)
**Laag:** 2 - Security
**Bevinding:** TypeScript CopilotMessage.decision_id was `string` maar moet `string | null`
zijn om te matchen met de Pydantic default (None serialiseert naar null in JSON).
**Actie:** Gewijzigd naar `decision_id?: string | null`.

### FA-003 (MINOR -- documentatie)
**Laag:** 2 - Security
**Bevinding:** Fail-open degraded mode: als council crasht gaat chat door zonder governance.
**Actie:** Audit event emitted via best_effort in degraded mode path. ADR-031 §3 legt
degraded mode vast als bewust ontwerp. Toekomstig: CVA_GOVERNANCE_FAIL_SECURE feature flag.

### FA-004 (MINOR -- backlog)
**Laag:** 1 - Code
**Bevinding:** HTTPException import in service layer koppelt service aan HTTP transport.
**Actie:** Functioneel correct. Architectureel refactor (GovernanceVetoError domain exception)
staat in backlog. Geen impact op correctheid of security.

### FA-005 (MINOR -- documentatie)
**Laag:** 4 - Documentatie
**Bevinding:** window.open() opent /api/v1/missions/explain raw API endpoint.
**Actie:** Gedocumenteerd als minor gap. Frontend route voor Right-to-Explanation
pagina staat in backlog (SP-CVA-SEC dag 2 of later).

---

## ADR-033 check

PASS: chat_router.py bevat geen imports uit src.core.copilot.council.
De council gate zit uitsluitend in cva_service.py (service laag). Geverifieerd
via grep: `grep "copilot.council" src/core/api/v1/cva/chat_router.py` = leeg.

## OWASP checks

| Check | Status |
|-------|--------|
| A01 tenant_id uit JWT | PASS |
| A03 message[:500] injection | PASS |
| A05 decision_id disclosure | PASS (UUID, per-tenant gefilterd) |

## Pyright

0 errors (baseline gehandhaafd).

---

*Review uitgevoerd door: code-reviewer + security-reviewer subagents (2026-06-20)*
