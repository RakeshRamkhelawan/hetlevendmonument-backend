# BE-RTR-013 — Agents Domain Migration naar v1/agents/ (SP-API-003 Dag 3)

**ID:** BE-RTR-013
**Sprint:** SP-API-003 Dag 3
**Datum:** 2026-06-04
**Type:** BE-RTR (router)
**ADR:** ADR-033

---

## Samenvatting

`src/core/api/agent_endpoints.py` (852 regels) is gemigreerd naar de drielaagse ADR-033
structuur onder `src/core/api/v1/agents/`. De routering-laag is gesplitst in drie thematische
sub-routers. De implementatielogica blijft in `agent_endpoints.py` wonen (te omvangrijk om te
dupliceren); sub-routers delegeren via lazy imports. `registries/agents.py` importeert nu de
`domain_router` uit `v1/agents/` in plaats van direct `agent_endpoints.router`.

---

## Nieuwe bestanden

| Bestand | Regels | Doel |
|---------|--------|------|
| `src/core/api/v1/agents/__init__.py` | 9 | Laag 2 domain_router export |
| `src/core/api/v1/agents/router.py` | 23 | Laag 1 composite — assembleert sub-routers in juiste volgorde |
| `src/core/api/v1/agents/dependencies.py` | 36 | Re-exports get_db, auth, AgentRegistry; houdt sub-routers import-clean |
| `src/core/api/v1/agents/agent_crud_router.py` | ~130 | POST /register, POST /, POST /agent/register, GET /, GET /{agent_id}, PATCH /{agent_id} |
| `src/core/api/v1/agents/agent_execution_router.py` | 68 | POST /execute, POST /agent/execute/{agent_id}, POST /execute/{agent_id} |
| `src/core/api/v1/agents/agent_management_router.py` | 75 | POST /collaborate, GET /stats, GET /health, GET /catalog |

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/registries/agents.py` | Importeert `domain_router` uit `v1/agents/` ipv `agent_endpoints.router` |
| `src/core/api/agent_endpoints.py` | `# orphan:exempt` commentaar toegevoegd |
| `tests/architecture/test_registry_equivalence.py` | `test_agents_flat_file_migrated_to_v1` toegevoegd |

---

## URL-contract (ongewijzigd, ADR-031 URL-freeze)

Alle URLs zijn identiek aan de originele `agent_endpoints.py`:

| Methode | Pad | Sub-router |
|---------|-----|-----------|
| POST | `/api/v1/agents/register` | agent_crud_router |
| POST | `/api/v1/agents/` | agent_crud_router |
| POST | `/api/v1/agents/agent/register` | agent_crud_router |
| GET | `/api/v1/agents/` | agent_crud_router |
| GET | `/api/v1/agents/{agent_id}` | agent_crud_router |
| PATCH | `/api/v1/agents/{agent_id}` | agent_crud_router |
| POST | `/api/v1/agents/execute` | agent_execution_router |
| POST | `/api/v1/agents/agent/execute/{agent_id}` | agent_execution_router |
| POST | `/api/v1/agents/execute/{agent_id}` | agent_execution_router (legacy) |
| POST | `/api/v1/agents/collaborate` | agent_management_router |
| GET | `/api/v1/agents/stats` | agent_management_router |
| GET | `/api/v1/agents/health` | agent_management_router |
| GET | `/api/v1/agents/catalog` | agent_management_router |

---

## Architectuur beslissingen

1. **Implementatie in agent_endpoints.py behouden** — de 852-regel flat file bevat complexe
   `list_agents` logica (EnterpriseCatalogLoader + ActivePieces integratie). Duplicatie zou
   meer risico introduceren dan de migratie oplost. Sub-routers delegeren via lazy imports.

2. **Route-volgorde in router.py** — management routes (geen path params) worden eerst
   geregistreerd, daarna execution, daarna CRUD (met `/{agent_id}`). Dit voorkomt dat het
   path-parameter patroon `/agents/{agent_id}` statische paden als `/agents/stats` opvangt.

3. **Lege-pad aliases verwijderd** — `@router.post("")` en `@router.get("")` waren
   `include_in_schema=False` intern-gebruik aliases in de originele flat router met prefix.
   FastAPI 0.121.1 verbiedt path="" zonder prefix op sub-router niveau. Ze zijn verwijderd;
   de `/` variants dekken hetzelfde gedrag.

---

## Trainingssamenvatting

### Flow 1: Agent registreren

| Stap | Detail |
|------|--------|
| Actor | API client (frontend of externe service) |
| Voorwaarde | Geldig JWT token met `agents:write` scope |
| Actie | `POST /api/v1/agents/` met `SimpleAgentRegistrationRequest` body |
| Systeemverwerking | `register_agent_minimal` in `agent_crud_router.py` delegeert naar `_perform_registration()` in `agent_endpoints.py`; slaat op in DB via `AgentRegistry` |
| Succesrespons | HTTP 201 `AgentRegistrationResponse` met gegenereerde `agent_id` |
| Foutrespons | HTTP 400/500 bij registry-fout; HTTP 401/403 bij auth-fout |
| Uitzonderingen | `AttributeError` → HTTP 503 "service unavailable" |

### Flow 2: Agenten oplijsten met filters

| Stap | Detail |
|------|--------|
| Actor | Frontend dashboard |
| Voorwaarde | Geldig JWT token met `agents:read` scope |
| Actie | `GET /api/v1/agents/?category=Technical&source=native` |
| Systeemverwerking | `list_agents` delegeert naar originele implementatie; laadt EnterpriseCatalogLoader (336 YAML agents) + ActivePieces integrations; past `_apply_agent_filters` toe |
| Succesrespons | HTTP 200 `AgentListResponse` met gefilterde agents en total_count |
| Foutrespons | HTTP 503 bij registry onbeschikbaar; HTTP 500 bij onverwachte fout |
| Uitzonderingen | ActivePieces timeout (5s) → graceful degradation, alleen native agents |

### Flow 3: Agent uitvoeren

| Stap | Detail |
|------|--------|
| Actor | Orchestration service of frontend |
| Voorwaarde | Geldig JWT token met `agents:write` scope; agent bestaat in registry |
| Actie | `POST /api/v1/agents/agent/execute/{agent_id}` met `AgentExecutionRequest` |
| Systeemverwerking | `execute_agent_primary` delegeert naar `execute_agent()` in `agent_endpoints.py`; haalt agent op uit registry; maakt `TaskData` aan; distribueert via `registry.distribute_task()` met configureerbare timeout |
| Succesrespons | HTTP 200 met `{agent_id, result, status, execution_time}` |
| Foutrespons | HTTP 404 agent niet gevonden; HTTP 504 timeout; HTTP 500 executiefout |
| Uitzonderingen | `execute_agent_dispatcher` (POST /execute) accepteert agent_id in body voor dispatcher pattern |
