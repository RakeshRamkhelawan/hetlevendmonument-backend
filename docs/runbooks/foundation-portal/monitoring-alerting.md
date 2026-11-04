# Runbook: Monitoring & Alerting

**Doel**: vroegtijdig problemen detecteren; alert-fatigue voorkomen.
**Stack**: OpenTelemetry + Jaeger + Prometheus + Grafana + Sentry (ADR-014).

## Dashboards

### Foundation Portal — Health (Grafana)

Url: `https://grafana.sanskritisetu.org/d/foundation-portal-health`

Panels:
1. **API request rate** — per endpoint per tenant (5 min window)
2. **Error rate** — % HTTP 5xx per endpoint
3. **P95 latency** — per endpoint
4. **Active uploads** — concurrent file-streams
5. **AI-tagging queue depth** — Dramatiq pending jobs
6. **Magic-link mail rate** — sent / bounced / delivered
7. **Cert-expiry per subdomain** — dagen tot vervaltijd

### Foundation Portal — Business (Grafana)

Url: `https://grafana.sanskritisetu.org/d/foundation-portal-business`

Panels per tenant:
- Aantal APPROVED items / dag
- Aantal PENDING items (curator backlog)
- Aantal nieuwe PortalUsers / week
- Top-10 thema-tags
- Newsletter-aanmeldingen / week

## Alerting-regels

### Severity P0 (PagerDuty)

| Alert | Trigger | Action |
| --- | --- | --- |
| Container down | health check fail > 1 min | Auto-restart + page on-call |
| DB unreachable | conn pool > 90% wait > 30s | Page DBA |
| Cert renewal failed | < 7 dagen tot expiry | Page on-call |
| Audit-log hash chain broken | hash mismatch detected | Page on-call + lockdown writes |

### Severity P1 (Slack #alerts + e-mail)

| Alert | Trigger | Action |
| --- | --- | --- |
| API error rate > 1% | 5 min window | Investigate logs |
| AI-tagging failure > 10% | 1u window | Check Ollama health |
| Magic-link bounce rate > 5% | 1u window | Check Brevo/SPF |
| Blob upload failures > 5 | 5 min window | Check Azure Blob status |
| Container memory > 90% sustained 5 min | gauge | Scale up replica |
| Dramatiq queue depth > 100 | 5 min | Add worker |

### Severity P2 (Slack #alerts daily digest)

| Alert | Trigger |
| --- | --- |
| Curator-backlog > 20 PENDING items | per tenant |
| Slow queries > 1s | top-10 |
| Storage approaching limit (80%) | per tenant |
| TLS cert expires in 14-30 dagen | per subdomain |

### Severity P3 (weekly report)

- Sentry top-10 errors
- Lighthouse score per tenant (a11y, perf, SEO)
- Test coverage trend
- Uptime per tenant (SLA tracking)

## Sentry configuratie

### Backend (FastAPI)
```python
# src/core/observability/sentry.py
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN_BACKEND"),
    traces_sample_rate=0.1,
    profiles_sample_rate=0.1,
    environment=os.getenv("APP_ENV"),
    before_send=_strip_pii,  # filter e-mails, tokens uit context
)
```

### Frontend (Next.js)
```typescript
// sentry.client.config.ts
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.1,
  beforeSend(event) {
    // strip URL query params met tokens
    if (event.request?.url) {
      event.request.url = event.request.url.split('?')[0]
    }
    return event
  }
})
```

### Alert-routing
- Critical errors (server crashes) → PagerDuty
- High-volume warnings → Slack #sentry
- Frontend errors → e-mail digest

## Custom metrics

### Backend Prometheus
```python
# src/core/observability/foundation_metrics.py
foundation_uploads_total = Counter(
    "foundation_uploads_total",
    "Total content uploads",
    ["tenant_id", "type", "status"],
)
foundation_ai_tagging_duration = Histogram(
    "foundation_ai_tagging_duration_seconds",
    "AI tagging duration",
    ["model", "content_type"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
foundation_curation_lag = Gauge(
    "foundation_curation_lag_hours",
    "Hours since oldest PENDING item",
    ["tenant_id"],
)
```

## Logging-checks

Per endpoint MOET aanwezig zijn (CLAUDE.md backend regel 11):
- `tenant_id`
- `tenant_slug`
- `portal_user_id` (indien geauthenticeerd)
- `request_id`
- bij errors: `exc_info=True`, `type(e).__name__`

Audit via grep:
```bash
grep -rE 'logger\.(info|error)' src/core/api/foundation_*.py | \
  grep -v 'tenant_id\|tenant_slug'
# verwacht: leeg
```

## Synthetic monitoring

### Externe checker (UptimeRobot of Statuspage)

Per 5 min:
- `GET https://ketikoti.levend-monument.nl/` → 200
- `GET https://api.sanskritisetu.org/health` → 200
- TLS handshake < 500ms

Bij 2 opeenvolgende failures: P1 alert.

### Smoke tests in CI
Nightly run via GitHub Actions:
- Magic-link request flow (zonder echte mail)
- Upload + curation flow (test-tenant)
- Public listing endpoints

## Cost monitoring

Azure Cost Management alerts:
- Monthly budget € 200 voor Foundation Portal infra
- 80% threshold → e-mail
- 100% threshold → Slack alert + investigate

## On-call playbook

Eerste actie bij elke alert:
1. Open Grafana dashboard van het component
2. Check Sentry voor recente errors
3. Check Azure Activity Log voor infra-changes laatste 30 min
4. Check GitHub recent deploys
5. Bij P0: PagerDuty + bestuur-alert
6. Documenteer in `docs/operations/incidents/{datum}-{slug}.md`
