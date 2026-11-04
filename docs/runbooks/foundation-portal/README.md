# Foundation Portal — Runbooks

Operationele runbooks voor het Levend Monument multi-tenant Foundation Portal.

## Inhoud

| Runbook | Doel |
| --- | --- |
| [onboard-tenant.md](onboard-tenant.md) | Nieuwe stichting toevoegen (DNS, tenant, branding, eerste curator) |
| [deprovision-tenant.md](deprovision-tenant.md) | Tenant offboarden met AVG-export en data-retentie |
| [backup-restore.md](backup-restore.md) | Database + Blob backup-strategie + disaster recovery |
| [incident-response.md](incident-response.md) | Wat doen bij security-, data- of beschikbaarheidsincident |
| [content-takedown.md](content-takedown.md) | NTD-procedure conform art. 6:196c BW |
| [monitoring-alerting.md](monitoring-alerting.md) | Metrics, dashboards, alert-regels, escalatiepad |
| [release-checklist.md](release-checklist.md) | Kwaliteitsgate vóór elke release naar productie |

## Cross-references

- Architectuur: [ADR-029](../../adr/029-foundation-portal-architecture.md)
- Design spec: [docs/superpowers/specs/2026-04-26-levend-monument-foundation-portal-design.md](../../superpowers/specs/2026-04-26-levend-monument-foundation-portal-design.md)
- Implementatie-plan: `docs/superpowers/plans/2026-04-26-levend-monument-foundation-portal-plan.md`

## On-call

| Rotatie | Primary | Secondary |
| --- | --- | --- |
| Eerste 6 maanden post-launch | Rakesh Ramkhelawan | TBD |
| Daarna | Wisselend per week | Wisselend per week |

Escalatie:
1. Primary on-call (Slack DM + PagerDuty)
2. Secondary on-call (na 15 min geen ack)
3. Bestuur Ketikotivlaardingen (P0 incidenten)
4. Externe pentester / juridisch contact (P0 security/legal)

## Audit-trail

Alle operationele acties loggen in `docs/operations/`:
- `tenant-onboardings.md`
- `tenant-deprovisionings.md`
- `restore-events.md`
- `incidents/{datum}-{slug}.md`
- `releases.md`
