# BE-RTR-020 — Autonomous Domain Migration naar v1/autonomous/

**Sprint:** SP-API-004 Dag 5
**Datum:** 2026-06-04
**ADR:** ADR-033
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

`autonomous_endpoints.py` (861r, prefix `/api/v1/autonomous`, 15 routes) gemigreerd naar
`src/core/api/v1/autonomous/` via 4 Laag-1 sub-routers (ADR-033 Strangler Fig patroon).
`router.py` en `progress_ws.py` zijn bewust NIET opgenomen in `domain_router` — deze zijn
al geregistreerd via `registries/agentic.py`.

---

## Nieuwe bestanden

| Bestand | Regels | Routes |
| ------- | ------ | ------ |
| `v1/autonomous/__init__.py` | 19r | domain_router compositie |
| `v1/autonomous/agents_router.py` | ~230r | POST /agents/create, GET/POST /agents/templates, GET /agents/factory/metrics, GET /status, GET /health |
| `v1/autonomous/healing_router.py` | ~120r | POST /healing/report-failure, GET /healing/status, POST /healing/execute-repair/{id} |
| `v1/autonomous/code_router.py` | ~90r | POST /code/generate, GET /code/templates, GET /code/metrics |
| `v1/autonomous/emergence_router.py` | ~90r | POST /emergence/facilitate, GET /emergence/behaviors, GET /emergence/intelligence-levels |

## Gewijzigde bestanden

| Bestand | Wijziging |
| ------- | --------- |
| `registries/optional.py` | `autonomous_endpoints.router` vervangen door `v1/autonomous.domain_router` |
| `autonomous_endpoints.py` | `# orphan:exempt` header toegevoegd; modellen/helpers behouden voor hergebruik door sub-routers |

---

## Architectuurbeslissingen

- Sub-routers importeren Pydantic-modellen en helpers uit `autonomous_endpoints.py` (geen duplicatie)
- `domain_router` in `__init__.py` heeft geen prefix — sub-routers dragen zelf `/api/v1/autonomous` prefix
- `router.py` (exec endpoints) en `progress_ws.py` (WebSocket) zijn buiten scope: al via `agentic.py` geregistreerd
- Geen `getattr(user, "tenant_id", None)` patroon gevonden in `autonomous_endpoints.py` — blocker was niet van toepassing

---

## Trainingssamenvatting

### Flow 1: Agent aanmaken via API

| Stap | Beschrijving |
| ---- | ------------ |
| **Actor** | Authenticated API client met scope `AGENTS_WRITE` |
| **Voorwaarde** | Geldige JWT + agent factory beschikbaar |
| **Actie** | `POST /api/v1/autonomous/agents/create` met `AgentCreationRequest` body |
| **Systeemverwerking** | `agents_router.create_autonomous_agent()` → `get_agent_factory()` → `request_agent_generation()` + `create_agent()` |
| **Succesrespons** | HTTP 200 `{"success": true, "agent_id": "...", "workflow_type": "hybrid_immediate_and_autonomous"}` |
| **Foutrespons** | HTTP 400 (ongeldig archetype), 503 (factory niet beschikbaar), 500 (onverwachte fout) |
| **Uitzonderingen** | HTTPException wordt direct re-raised; andere exceptions worden gelogd met `exc_info=True` en omgezet naar 500 |

### Flow 2: Systeem failure rapporteren

| Stap | Beschrijving |
| ---- | ------------ |
| **Actor** | Authenticated API client met scope `AGENTS_WRITE` |
| **Voorwaarde** | Self-healing system beschikbaar |
| **Actie** | `POST /api/v1/autonomous/healing/report-failure` met `FailureReportModel` |
| **Systeemverwerking** | `healing_router.report_system_failure()` → `detect_and_diagnose_failure()` + optioneel `execute_repair_plan()` |
| **Succesrespons** | HTTP 200 met `failure_id`, `repair_plan`, `auto_repaired` status |
| **Foutrespons** | HTTP 500 bij systeem-fout |
| **Uitzonderingen** | `auto_repair=false` → repair plan wordt teruggegeven maar niet uitgevoerd |

### Flow 3: Structurele migratie (intern, geen user-impact)

| Stap | Beschrijving |
| ---- | ------------ |
| **Actor** | API router stack (FastAPI lifespan) |
| **Voorwaarde** | `optional.py` registreert `domain_router` |
| **Actie** | App start, `register()` in `optional.py` wordt aangeroepen |
| **Systeemverwerking** | `domain_router` include `agents_router` + `healing_router` + `code_router` + `emergence_router` |
| **Succesrespons** | Alle 15 routes beschikbaar op `/api/v1/autonomous/*` |
| **Foutrespons** | Import-fout → logger.warning, count niet verhoogd (graceful degradation) |
| **Uitzonderingen** | `router.py` en `progress_ws.py` NIET in `domain_router` (dubbele registratie voorkomen) |
