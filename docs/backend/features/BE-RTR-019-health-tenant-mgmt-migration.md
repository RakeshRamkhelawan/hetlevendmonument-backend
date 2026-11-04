# BE-RTR-019 — Health + Tenant Management Domain Migration naar v1/

**ID:** BE-RTR-019
**Sprint:** SP-API-004 Dag 4
**Datum:** 2026-06-04
**Status:** DONE
**Prefix:** BE-RTR (router)

---

## Samenvatting

`health_endpoints.py` (747r) en `tenant_management_endpoints.py` (707r) zijn gemigreerd
naar de drie-laags ADR-033 structuur onder `src/core/api/v1/health/` en
`src/core/api/v1/tenant_management/`.

De health-migratie vereist dual-registration: zonder prefix in `analytics.py`
(liveness/readiness op root) en met prefix `/api/v1/agents` in `agents.py` (diagnostics).
Beide registraties gebruiken nu `domain_router` uit `v1/health/__init__.py`.

---

## Gewijzigde bestanden

| Bestand | Type | Actie |
|---------|------|-------|
| `src/core/api/v1/health/__init__.py` | Nieuw | domain_router ZONDER prefix (dual-registration) |
| `src/core/api/v1/health/router.py` | Nieuw | Composite router |
| `src/core/api/v1/health/checks_router.py` | Nieuw | GET /health, /health/ready, /health/db, /ready (deprecated), /health/deep, /health/paperclip |
| `src/core/api/v1/health/llm_router.py` | Nieuw | GET /llm |
| `src/core/api/v1/health/dependencies.py` | Nieuw | verify_token re-export |
| `src/core/api/v1/tenant_management/__init__.py` | Nieuw | domain_router met prefix /api/v1 |
| `src/core/api/v1/tenant_management/router.py` | Nieuw | Composite router, prefix /tenants |
| `src/core/api/v1/tenant_management/crud_router.py` | Nieuw | POST /, GET /, GET /{tenant_id}, PUT /{tenant_id}, DELETE /{tenant_id} |
| `src/core/api/v1/tenant_management/dependencies.py` | Nieuw | require_admin re-export |
| `src/core/api/registries/analytics.py` | Gewijzigd | health_endpoints -> v1/health domain_router |
| `src/core/api/registries/agents.py` | Gewijzigd | health_endpoints diagnostics -> v1/health domain_router |
| `src/core/app_factory.py` | Gewijzigd | tenant_management_endpoints -> v1/tenant_management domain_router |
| `src/main.py` | Gewijzigd | tenant_management_endpoints module string -> v1/tenant_management |
| `src/core/api/health_endpoints.py` | Gewijzigd | orphan:exempt comment toegevoegd |
| `tests/architecture/test_registry_equivalence.py` | Gewijzigd | 2 equivalentietests toegevoegd (RED -> GREEN) |

---

## Architectuurbeslissingen

### Health dual-registration

`domain_router` in `v1/health/__init__.py` heeft GEEN prefix. Dit is verplicht omdat:
1. `analytics.py` registreert zonder extra prefix (routes op root: `/health`, `/ready`, `/llm`)
2. `agents.py` registreert met `prefix="/api/v1/agents"` (diagnostics sub-routes)

Een prefix in `domain_router` zou de root-routes breken.

### GET /ready deprecated=True bewaard

`checks_router.py` declareert `@router.get("/ready", deprecated=True)`. De deprecated flag
is behouden conform de originele `health_endpoints.py` implementatie.

### Tenant management: geen getattr fail-secure probleem

`get_tenant()` in `crud_router.py` gebruikt `current_user.tenant_id` — een getypeerd veld
op `UserResponse`, geen `getattr(..., None)` fallback. Niet-admin toegang tot een andere
tenant resulteert in HTTP 403 (fail-secure gedrag).

---

## Trainingssamenvatting

### Flow 1: Liveness probe via v1/health

**Actor:** Kubernetes liveness probe  
**Voorwaarde:** Backend container draait  
**Actie:** GET /health  
**Systeemverwerking:** `checks_router.health_check()` delegeert naar `health_endpoints.health_check()`; geen DB/Redis-check (ADR-012)  
**Succesrespons:** HTTP 200 `{"status": "ok", "timestamp": "..."}`  
**Foutrespons:** N.v.t. — geen externe dependencies  
**Uitzonderingen:** N.v.t.

### Flow 2: Readiness probe via v1/health

**Actor:** Kubernetes readiness probe  
**Voorwaarde:** Backend container UP, DB en Redis bereikbaar  
**Actie:** GET /health/ready  
**Systeemverwerking:** `checks_router.readiness_check()` delegeert naar `health_endpoints.readiness_check()`; DB check (300ms timeout), Redis check (100ms timeout)  
**Succesrespons:** HTTP 200 `{"status": "ready", "dependencies": {...}}`  
**Foutrespons:** HTTP 503 als DB of Redis down; `{"status": "not_ready", "reason": "...", "dependencies": {...}}`  
**Uitzonderingen:** `{"status": "degraded"}` bij trage maar functionele dependencies

### Flow 3: Tenant aanmaken via v1/tenant_management

**Actor:** Admin gebruiker  
**Voorwaarde:** Geldig JWT met admin-rol  
**Actie:** POST /api/v1/tenants/  
**Systeemverwerking:** `crud_router.create_tenant()` -> `require_admin()` check -> `tenant_management_endpoints.create_tenant()` -> DB insert + audit log  
**Succesrespons:** HTTP 201 `TenantResponse`  
**Foutrespons:** HTTP 403 als geen admin; HTTP 400 als tenant naam/slug al bestaat  
**Uitzonderingen:** HTTP 500 bij DB fout (exc_info=True gelogd)

### Flow 4: Tenant opvragen als niet-admin

**Actor:** Reguliere gebruiker  
**Voorwaarde:** Geldig JWT, tenant_id in token  
**Actie:** GET /api/v1/tenants/{tenant_id}  
**Systeemverwerking:** `crud_router.get_tenant()` -> check `current_user.tenant_id != tenant_id` -> HTTP 403 als mismatch (fail-secure)  
**Succesrespons:** HTTP 200 `TenantResponse` van eigen tenant  
**Foutrespons:** HTTP 403 als poging tot andere tenant; HTTP 404 als tenant niet bestaat  
**Uitzonderingen:** Admin bypassed via `TenantFilterBypass()` context manager
