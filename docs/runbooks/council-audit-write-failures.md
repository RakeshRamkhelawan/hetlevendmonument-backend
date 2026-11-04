# Runbook -- Council Audit Write Failures

**Alert:** CouncilAuditWriteFailing
**Severity:** CRITICAL
**Compliance impact:** AI-beslissingen worden geblokt (fail-secure), maar
oorzaak moet binnen 1 uur opgelost zijn anders functionele impact op
gebruikers.

## Triage (eerste 5 minuten)
1. Bekijk Grafana paneel "Audit write success rate" -- % succesvolle writes.
2. Check `copilot_audit_writes_total{status="failed"}` -- welke tenant?
3. Recente DB-events: connection pool exhaustion? Long-running query?
4. Check `governance_audit_log` table size + autovacuum status.

## Onderzoek
1. DB-connection pool: `SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'`.
2. Disk space op DB-host: `df -h`.
3. Recent migration die `governance_audit_log` heeft gewijzigd?
4. RLS-policy correct? `SELECT * FROM pg_policies WHERE tablename = 'governance_audit_log'`.

## Mitigatie
1. Bij DB-overload: throttle nieuwe Council deliberations via
   feature flag of rate-limit verlaging.
2. Bij connection pool exhaustion: restart workers, schaal pool size op.
3. Communiceer naar gebruikers: "AI-beslissingen tijdelijk onbeschikbaar".

## Permanente fix
- Root cause analyse + commit + regression test.
- Re-enable feature flag.
- Post-mortem.

## Niet doen
- [X] Audit-write `best_effort` maken -- dat ondermijnt fail-secure
  garantie en is een ADR-027 violation.
- [X] Audit-write skippen -- Council MOET fail-secure BLOCKED retourneren.
