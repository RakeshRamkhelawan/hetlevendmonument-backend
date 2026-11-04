# BE-RTR-024 — Tool Broker + Governance Admin Migration naar v1/

**Sprint:** SP-API-005 Dag 4
**Datum:** 2026-06-05
**Status:** DONE
**ADR:** ADR-033

---

## Samenvatting

`tool_broker_endpoints.py` (648r) en `governance_endpoints.py` (591r) gemigreerd naar het
drie-laags ADR-033 patroon:

- `src/core/api/v1/tool_broker/` (crud_router + execution_router + management_router)
- `src/core/api/v1/governance_admin/` (router.py met # orphan:exempt)

Registries bijgewerkt: `registries/optional.py` en `registries/core_api.py`.
Legacy flat files zijn re-export shims.

---

## Nieuwe bestanden

| Bestand | Regels | Doel |
|---------|--------|------|
| `v1/tool_broker/__init__.py` | 9 | domain_router Laag 2 |
| `v1/tool_broker/router.py` | 13 | composite Laag 1 |
| `v1/tool_broker/crud_router.py` | 85 | POST / + GET / |
| `v1/tool_broker/execution_router.py` | 155 | POST /execute + GET /history + GET /history/recent |
| `v1/tool_broker/management_router.py` | 125 | GET /list + GET /{name}/status + POST /{name}/enable + POST /{name}/disable |
| `v1/tool_broker/dependencies.py` | 20 | ToolBrokerService factory |
| `v1/tool_broker_shared.py` | 116 | Pydantic schemas + in-memory state |
| `v1/governance_admin/__init__.py` | 9 | domain_router Laag 2 |
| `v1/governance_admin/router.py` | 514 | GET /anomalies + GET /risks/{mission_id} (# orphan:exempt) |

---

## Routes

### Tool Broker (`/api/v1/tools`)

| Method | Path | Scope | Module |
|--------|------|-------|--------|
| POST | `/` | AGENTS_WRITE | crud_router |
| GET | `/` | — | crud_router |
| POST | `/execute` | AGENTS_WRITE | execution_router |
| GET | `/list` | AGENTS_READ | management_router |
| GET | `/{tool_name}/status` | AGENTS_READ | management_router |
| GET | `/history` | AGENTS_READ | execution_router |
| POST | `/{tool_name}/enable` | ADMIN_ALL | management_router |
| POST | `/{tool_name}/disable` | ADMIN_ALL | management_router |
| GET | `/history/recent` | AGENTS_READ | execution_router |

### Governance Admin (`/api/v1/governance`)

| Method | Path | Scope | Module |
|--------|------|-------|--------|
| GET | `/anomalies` | AUDIT_READ | governance_admin/router |
| GET | `/risks/{mission_id}` | AUDIT_READ | governance_admin/router |

---

## ADR-015 ToolBroker Allowlist

ADR-015 ToolBroker allowlist-logica (execute via `ToolBrokerService`) is intact in
`execution_router.py`. De `SerenaClient` + `SequentialThinkingClient` worden via de
service-laag aangestuurd, niet rechtstreeks vanuit de route-handler.

---

## Trainingssamenvatting

### Flow 1: Tool registreren (POST /api/v1/tools/)

| Stap | Detail |
|------|--------|
| Actor | Beheerder met AGENTS_WRITE scope |
| Voorwaarde | Geldig JWT met `agents:write` claim |
| Actie | POST /api/v1/tools/ met ToolCreate payload (name, category, capabilities) |
| Systeemverwerking | Sla op in `available_tools` dict; tenant_id uit JWT via `current_user.tenant_id` |
| Succesrespons | HTTP 201 ToolResponse met gegenereerd UUID |
| Foutrespons | 401 bij ontbrekend JWT, 403 bij verkeerde scope |
| Uitzonderingen | Bestaande tool wordt overschreven (update-semantiek) |

### Flow 2: Tool uitvoeren (POST /api/v1/tools/execute)

| Stap | Detail |
|------|--------|
| Actor | Agent of gebruiker met AGENTS_WRITE scope |
| Voorwaarde | Tool moet bestaan in `available_tools` |
| Actie | POST /api/v1/tools/execute met {tool_name, payload} |
| Systeemverwerking | `ToolBrokerService.execute_tool()` aanroepen; resultaat opslaan in history |
| Succesrespons | HTTP 200 ToolExecutionResponse met result + execution_time_ms |
| Foutrespons | 400 bij onbekende tool, 500 bij executie-fout |
| Uitzonderingen | History altijd bijgewerkt (ook bij failure, via finally-blok) |

### Flow 3: Anomalieen ophalen (GET /api/v1/governance/anomalies)

| Stap | Detail |
|------|--------|
| Actor | Auditor met AUDIT_READ scope |
| Voorwaarde | Tenant-context aanwezig in JWT |
| Actie | GET /api/v1/governance/anomalies?days=7&limit=20 |
| Systeemverwerking | `generate_sample_anomalies()` gefilterd op tenant; statistieken berekend |
| Succesrespons | HTTP 200 AnomaliesResponse met anomalies + stats + period |
| Foutrespons | 400 bij ontbrekende tenant-context, 403 bij verkeerde scope |
| Uitzonderingen | Productie: query uit DB; nu: deterministische sample-data |
