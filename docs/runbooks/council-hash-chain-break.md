# Runbook -- Council Hash Chain Break

**Alert:** CouncilHashChainBreak
**Severity:** CRITICAL
**Compliance impact:** AI Act tamper-evident audit-trail geschonden.

## Triage (eerste 5 minuten)
1. Bekijk de alert payload: welke tenant + welke decision_id?
2. Check Grafana paneel "Hash chain breaks (MUST be 0)" -- staat counter > 0?
3. Run als tenant-admin: `GET /api/v1/copilot/audit/verify`. Bekijk
   `broken_links` array -- exacte decision_id's.

## Onderzoek (eerste 30 minuten)
1. SSH naar DB-host. Inspecteer `council_decisions` tabel rond timestamp
   van de break. Zoek dubbele writes of out-of-order timestamps.
2. Check Postgres logs op `pg_advisory_xact_lock` warnings.
3. Check `governance_audit_log` voor recente DDL-changes (migration die
   per ongeluk een row update?).
4. Was er een recente deploy / migration op de affected tijd?

## Mitigatie
1. **STOP nieuwe writes** indien onderzoek nog loopt: zet feature flag
   `COUNCIL_AUDIT_WRITE_ENABLED=false` -> Council retourneert BLOCKED voor
   alle nieuwe proposals.
2. Documenteer de break in `docs/incidents/` met timestamp, betrokken
   tenant, vermoedelijke oorzaak.
3. Bij wettelijke verplichting: notificeer DPO binnen 72 uur (GDPR art. 33).

## Permanente fix
- Identificeer root cause (race condition? bypass van advisory lock?
  externe SQL update?).
- Implementeer regressie-test (`tests/security/copilot/`).
- Re-enable feature flag.
- Post-mortem in `docs/incidents/`.

## Niet doen
- [X] Niet de chain "repairen" door previous_decision_hash handmatig te
  fixen -- dat verbergt het lek.
- [X] Niet retroactief DELETE -- audit-rows zijn immutable.
