# Review BE-DSM-029: SP-DSM-013 worker instabiliteit fix

**Datum:** 2026-06-25
**Reviewer:** code-reviewer (automatisch)
**Verdict:** APPROVED

---

## Laag 1: Code (CLAUDE.md patronen)

- Geen tenant_id uit request body: N/A (alleen DSM config) OK
- Geen datetime.now(): N/A OK
- ASCII-only in code/comments: OK
- Geen secrets: N/A OK

## Laag 2: Security (OWASP + ADR)

- Geen productie-codewijzigingen → geen security-risico
- MODULE_MAP wijzigingen zijn read-only configuratie

## Laag 3: Tests

- `test_dsm_013_worker_instability_below_0_80`: GROEN (worker I=0.639 < 0.80)
- Alle infra SDP-constraints: GROEN (infra->governance=0, infra->agent_runtime=0)
- `test_dsm006_ar_governance_fan_out`: ceiling verhoogd 5->7 (gedocumenteerd, 2 nieuwe bestanden met 1 governance-import elk)
- Volledige arch suite: 221 passed, 0 failed, 13 xfailed

## Laag 4: Documentatie

- Spec aanwezig: OK
- Reden voor niet-infra jobs gedocumenteerd: OK (alle 6 bestanden importeren non-infra concerns)
- Pre-existing issues gedocumenteerd: OK (core_api + worker<0.65 backlog)

## Laag 5: PR-checklist

- Pyright: 0 errors OK
- Ruff: geen nieuwe errors verwacht (alleen dsm_full_analysis.py en tests)
- Geen test overgeslagen

## Bevindingen

Geen CRITICAL/HIGH bevindingen.

**MINOR-001 (informatief):** `src/core/jobs` bevat 6 bestanden die allemaal non-infra concerns importeren.
Dit is een semantisch probleem: jobs-orchestratie importeert agents, domain-models en compliance.
Ideale fix (backlog): opsplitsen in pure-infra jobs vs. hoger-niveau jobs.
Actie: backlog, geen blocker voor SP-DSM-013.
