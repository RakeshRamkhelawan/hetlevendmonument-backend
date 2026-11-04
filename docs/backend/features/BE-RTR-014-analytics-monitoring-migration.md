# BE-RTR-014 — Analytics + Monitoring Domain Migration naar v1/ (SP-API-003 Dag 4)

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-RTR-014 |
| Sprint | SP-API-003 Dag 4 |
| Datum | 2026-06-04 |
| Status | IMPLEMENTED |
| ADR | ADR-033 (API Layer Strangler Fig) |

## Samenvatting

Migratie van twee grote flat bestanden naar ADR-033 drie-laags structuur:

- `analytics_endpoints.py` (1159r, prefix `/api/analytics`) → `src/core/api/v1/analytics_ingest/`
- `monitoring_endpoints.py` (933r, prefix `/monitoring`) + `monitoring_dashboard_endpoints.py` (711r, geen prefix) → `src/core/api/v1/monitoring_v1/`

Registries/analytics.py bijgewerkt met lazy domain router imports.

## Nieuwe bestanden

### analytics_ingest domain

| Bestand | Regels | Rol |
|---------|--------|-----|
| `v1/analytics_ingest/__init__.py` | 12 | domain_router export |
| `v1/analytics_ingest/router.py` | 18 | Composite router (prefix /analytics) |
| `v1/analytics_ingest/events_router.py` | ~220 | POST /events, GET /metrics, GET /sessions/{id}, GET /health |
| `v1/analytics_ingest/gdpr_router.py` | ~110 | POST /events/export, DELETE /events/user |
| `v1/analytics_ingest/dashboard_router.py` | ~120 | GET /dashboard (stats) |
| `v1/analytics_ingest/schemas.py` | ~200 | Alle Pydantic schemas (events, metrics, dashboard) |
| `v1/analytics_ingest/dependencies.py` | 15 | get_db, get_current_user, tenant_id re-exports |

### monitoring_v1 domain

| Bestand | Regels | Rol |
|---------|--------|-----|
| `v1/monitoring_v1/__init__.py` | 12 | domain_router export |
| `v1/monitoring_v1/router.py` | 18 | Composite router (prefix /monitoring) |
| `v1/monitoring_v1/health_router.py` | ~130 | GET /live, GET /ready, GET /health |
| `v1/monitoring_v1/metrics_router.py` | ~200 | GET /metrics (JSON+Prometheus), GET /metrics/prometheus, GET /performance, GET /logs/analysis |
| `v1/monitoring_v1/alerts_router.py` | ~270 | GET /alerts, POST /trigger_alert, GET /alert/{id}, profiler endpoints, mock-usage endpoints, GET /system/status |
| `v1/monitoring_v1/dashboard_router.py` | ~310 | Dashboard REST + WebSocket + HTML endpoints |
| `v1/monitoring_v1/dependencies.py` | 12 | UserResponse, get_current_user, require_scopes, OAuth2Scope re-exports |

## Kwaliteitsregels nageleefd

- Geen f-strings in logger — `%s` formatting gebruikt
- `except Exception as e:` altijd met `exc_info=True`
- Geen `from __future__ import annotations`
- `"/"` niet `""` als leeg route-pad
- Geen directe imports van `src.core.database`, `src.core.governance` in router bestanden

## Testresultaten

- 132 tests PASS (130 baseline + 2 nieuwe architecture tests)
- `test_analytics_flat_file_migrated_to_v1` GROEN
- `test_monitoring_flat_files_migrated_to_v1` GROEN
- `python scripts/validate_feature_docs.py` — PASS (177 IDs complete)

## Trainingssamenvatting

### Flow 1: Analytics event batch submit

| Stap | Detail |
|------|--------|
| Actor | Frontend applicatie of API client |
| Voorwaarde | Geldige JWT, tenant_id uit context, niet-lege events lijst (max 1000) |
| Actie | POST /api/v1/analytics/events met EventBatchRequest body |
| Systeemverwerking | Tenant ID uit JWT, elke event opgeslagen als DBAnalyticsEvent, batch gecommit bij processed_count > 0 |
| Succesrespons | HTTP 202 met EventBatchResponse (batchId, eventsProcessed, eventsRejected) |
| Foutrespons | 400 bij validatiefout, 500 bij DB-fout (rollback uitgevoerd) |
| Uitzonderingen | Individuele event-fouten worden gelogd als warning maar blokkeren de rest van de batch niet |

### Flow 2: Monitoring liveness probe

| Stap | Detail |
|------|--------|
| Actor | Kubernetes / load balancer |
| Voorwaarde | Geen authenticatie vereist |
| Actie | GET /api/v1/monitoring/live |
| Systeemverwerking | get_health_checker().liveness_check() aangeroepen |
| Succesrespons | HTTP 200 met LivenessResponse (status, uptime_seconds, timestamp) |
| Foutrespons | HTTP 500 bij interne fout |
| Uitzonderingen | Geen auth check — bewust publiek voor k8s probes |

### Flow 3: Dashboard WebSocket verbinding

| Stap | Detail |
|------|--------|
| Actor | Browser met geldige JWT |
| Voorwaarde | AGENTS_READ scope vereist, tenant_id uit user |
| Actie | WS /api/v1/monitoring/ws/dashboard |
| Systeemverwerking | set_tenant_id() gezet, ConnectionManager.connect() aangeroepen, initieel system_overview gestuurd, daarna iedere 5s update |
| Succesrespons | Initieel `{type: "initial_data", data: ...}`, dan periodiek `{type: "update", ...}` |
| Foutrespons | WebSocketDisconnect gelogd, disconnect() opgeroepen in finally-blok |
| Uitzonderingen | mountedRef-equivalent via ConnectionManager._tenant_of map; disconnect cleanup altijd in finally |

### Flow 4: GDPR data export

| Stap | Detail |
|------|--------|
| Actor | Ingelogde gebruiker |
| Voorwaarde | Geldige JWT, user_id uit JWT sub-claim |
| Actie | POST /api/v1/analytics/events/export |
| Systeemverwerking | Query alle events + sessions voor user_id+tenant_id, bouw export_data dict |
| Succesrespons | HTTP 200 met export_data (events, sessions, summary) |
| Foutrespons | HTTP 500 bij DB-fout |
| Uitzonderingen | Tenant-isolatie via tenant_id uit JWT (nooit uit body) |
