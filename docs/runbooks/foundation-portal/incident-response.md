# Runbook: Incident Response

**Doel**: gestructureerd reageren op security-, data- en beschikbaarheidsincidenten.
**Eigenaar**: On-call platform-admin (rotatie per week).

## Severity-classificatie

| Severity | Definitie | Voorbeelden | Response-tijd |
| --- | --- | --- | --- |
| **P0 - Critical** | Data-lek, ransomware, fundamentele platform-down > 1u | DB compromised, ransomware, RCE in productie | 15 min |
| **P1 - High** | Significante downtime of degradatie, security-vulnerability bevestigd | Single tenant down, kritieke kwetsbaarheid pentest | 1 uur |
| **P2 - Medium** | Beperkte impact, workaround mogelijk | Slow API, degraded AI-tagging | 4 uur |
| **P3 - Low** | Cosmetisch, single user issue | UI-bug, individuele upload mislukt | 1 werkdag |

## Algemene flow

```
ALERT BINNEN
    |
    v
1. ACKNOWLEDGE binnen response-tijd
2. CLASSIFY severity
3. CONTAIN damage (isolate, lockdown indien nodig)
4. INVESTIGATE root cause (logs, audit-log, Azure Activity Log)
5. REMEDIATE (fix, hotfix, rollback)
6. COMMUNICATE (status-page, stakeholders)
7. POST-MORTEM (binnen 5 werkdagen na incident)
```

## P0 — data breach

### Containment (eerste 15 min)
1. **Stop bleeding**: lockdown affected component
   - DB compromised → revoke service-principal access
   - Account compromise → revoke alle JWT tokens (incrementeer secret rotation)
   - Blob compromise → revoke storage SAS tokens
2. **Preserve evidence**: snapshot DB, Azure Activity Log, audit-log, container logs
3. **PagerDuty escalate**: bestuur + juridisch contact

### Investigation (eerste uur)
- Welke `tenant_id`'s geraakt?
- Welke `PortalUser` records?
- Welke content (Privacy=PUBLIC vs COMMUNITY)?
- Tijdsvenster: van... tot...
- Aanvalsvector: log-analyse + Azure Sentinel

### Notificaties (binnen 72 uur — AVG art. 33)
- **Autoriteit Persoonsgegevens** via meldloket (`autoriteitpersoonsgegevens.nl`)
- **Affected portal users** per e-mail met:
  - Wat is gelekt
  - Welke maatregelen genomen
  - Wat zij kunnen doen (wachtwoord-reset niet relevant — magic-link, maar JWT revocation aanvragen)
- **UVB**: indien subsidie-gerelateerde data geraakt
- **Stichtings-besturen** van alle affected tenants

### Remediation
- Patch root cause
- Forensisch onderzoek (extern indien crimineel)
- Politie-aangifte
- Update security-controls
- Pentest na fix

### Post-mortem
Template `docs/operations/post-mortem-template.md`:
- Timeline (UTC)
- Detection method
- Containment actions
- Root cause
- What went well / poorly
- Action items met owner + deadline

## P1 — single tenant down

1. ACK in monitoring tool
2. Check Azure Container App status
3. Check tenant-specific config (Tenant.is_active, FoundationPortalSettings exists)
4. Check Traefik routing logs voor die slug
5. Check DB query latency
6. Hotfix of rollback
7. Statuspage update
8. Customer notify (curator-mail)

## P1 — security kwetsbaarheid bevestigd

1. **CVE-tracker check**: bestaat fix?
2. Check ADR-013 (secrets rotation) of Dependabot alert
3. Hotfix patch via develop-branch
4. CI groen
5. Tag patch-release (geen feature wijzigingen)
6. Deploy productie via pipeline
7. Verifieer fix
8. Public disclosure post-fix (90 dagen window)

## Communicatie-templates

### Status-page tijdens incident
```
[ONDERZOEK] We zijn op de hoogte van problemen met {component}.
Update volgt binnen 30 minuten.
```

### Customer-mail bij data breach
```
Onderwerp: Beveiligingsincident Levend Monument

Beste {naam},

Op {datum} hebben wij een beveiligingsincident geconstateerd dat mogelijk
gevolgen heeft voor uw account op {portal_url}.

Wat is er gebeurd: {beschrijving}
Welke gegevens: {opsomming}
Wat doen wij: {maatregelen}
Wat kunt u doen: {acties}

Voor vragen: {contact}.

Met vriendelijke groet,
{naam}
Platform-admin Levend Monument
```

## On-call rotatie

| Week | Primary | Secondary |
| --- | --- | --- |
| Even weken | Platform-admin A | Platform-admin B |
| Oneven weken | Platform-admin B | Platform-admin A |

Tot tweede admin: Rakesh primary 24/7 (eerste 6 maanden post-launch).

## Tools & toegang
- **Monitoring**: Sentry, Grafana, Azure Monitor
- **Alerting**: PagerDuty (P0/P1), Slack (P2/P3)
- **Logs**: Azure Log Analytics workspace `sanskritisetu-prod-logs`
- **Forensisch**: Azure Sentinel + Activity Log export

## Externe contacten
| Doel | Contact |
| --- | --- |
| Autoriteit Persoonsgegevens | https://www.autoriteitpersoonsgegevens.nl/melden-datalek |
| Politie cybercrime | 0900-8844 |
| Externe pentester | (in te vullen na keuze) |
| Juridisch (UVB-rapportage) | (in te vullen, externe juridische partner) |
