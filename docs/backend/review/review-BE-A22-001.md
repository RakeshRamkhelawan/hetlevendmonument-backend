# Review -- BE-A22-001 (Contest admin-flow)

> Reviewers: Gate-2 code-reviewer + security-reviewer (subagents)
> Datum: 2026-07-13
> Spec: `docs/backend/features/BE-A22-001-contest-admin-flow.md`
> Diff: commits `8b5d1301` + `17fa1e5e` op `iter/dag7-gdpr`

## Eindoordeel

**APPROVED**

Security-reviewer APPROVED. Code-reviewer gaf initieel CHANGES_REQUESTED met 1 BLOCKER: de
resolve-audit ging via een raw INSERT die `audit_hash` NULL liet (buiten de ADR-019 hash-chain).
Opgelost in `17fa1e5e`: resolve schrijft nu via `AuditService.log_action` (tamper-evident), test
scherpt aan dat de audit via AuditService loopt. Geen open BLOCKER/CRITICAL/HIGH.

## Geverifieerd

- Tenant-isolatie: queue/resolve filteren `DecisionContestRow.tenant_id`; resolve fetch op
  `contest_id AND tenant_id` (tenant uit JWT).
- IDOR/enumeratie: cross-tenant -> identieke 404; 409 pas na tenant-match.
- Authz: `_is_tenant_admin` = rolcheck (geen scope-only); 403 voor niet-admin vóór DB-toegang.
- Notify: echte `Notification`-insert voor de indiener (geen stub) via best_effort.
- Audit: `AuditService.log_action` (ADR-019 hash-chain).
- CLAUDE.md: datetime tz-aware, geen tenant_id uit body, CSRF op resolve, rate-limits correct, ASCII-only.

## Follow-up (bewust, gedocumenteerd)

Create-path admin-fan-out (`contest_service.py` dramatiq-stub) niet omgezet -- vereist bevestiging van
het `User.roles`-query-mechanisme; niet gegokt.

Geschikt voor implementatie/QA/LLM-training: ja.
