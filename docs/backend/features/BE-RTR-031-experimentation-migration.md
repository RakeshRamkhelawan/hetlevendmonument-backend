# BE-RTR-031 — Experimentation Domain Migration naar v1/experimentation/

**ID:** BE-RTR-031
**Sprint:** SP-API-007 Dag 1
**Datum:** 2026-06-05
**Status:** DONE
**Commit:** 16a3d7f5

---

## Samenvatting

`experimentation_endpoints.py` (582r, 9 routes) gemigreerd naar `src/core/api/v1/experimentation/`
conform ADR-033 drie-laags structuur. Legacy flat file vervangen door re-export shim.

---

## Bestanden

| Bestand | Regels | Rol |
|---------|--------|-----|
| `src/core/api/v1/experimentation/__init__.py` | 10 | Laag 2: domain_router export |
| `src/core/api/v1/experimentation/router.py` | 10 | Laag 2: composite router, prefix /api/v1/experiments |
| `src/core/api/v1/experimentation/experiments_router.py` | 534 | Laag 1: 9 routes, orphan:exempt regel 1 |
| `src/core/api/v1/experimentation/dependencies.py` | 6 | Domein-dependencies |
| `src/core/api/experimentation_endpoints.py` | 2 | Re-export shim (orphan:exempt) |
| `src/core/api/registries/analytics.py` | 76 | Laag 3: lazy import exp_domain_router toegevoegd |
| `src/core/api/setup/router_registry.py` | — | Legacy import vervangen door migratie-comment |

---

## Routes (9 totaal)

| Methode | Pad | Scope |
|---------|-----|-------|
| POST | /api/v1/experiments/create | ADMIN_ALL |
| GET | /api/v1/experiments/{experiment_id} | AGENTS_READ |
| POST | /api/v1/experiments/{experiment_id}/start | ADMIN_ALL |
| POST | /api/v1/experiments/{experiment_id}/pause | ADMIN_ALL |
| POST | /api/v1/experiments/{experiment_id}/stop | ADMIN_ALL |
| POST | /api/v1/experiments/{experiment_id}/assign | AGENTS_WRITE |
| GET | /api/v1/experiments/{experiment_id}/metrics | AGENTS_READ |
| POST | /api/v1/experiments/{experiment_id}/results | AGENTS_READ |
| GET | /api/v1/experiments/active | AGENTS_READ |

---

## Pre-existing Issues Gevonden en Gefixed

| Issue | Locatie | Actie |
|-------|---------|-------|
| f-string logger calls (11x) | experimentation_endpoints.py | Gefixed in nieuwe experiments_router.py: %s formatting |

---

## Trainingssamenvatting

### Flow 1: Experiment aanmaken (POST /api/v1/experiments/create)

- **Actor:** Authenticated admin user
- **Voorwaarde:** Geldige JWT met ADMIN_ALL scope; minimaal 2 varianten
- **Actie:** POST /api/v1/experiments/create met CreateExperimentRequest body
- **Systeemverwerking:** Valideer request; ExperimentManager.create_experiment(); log audit trail
- **Succesrespons:** HTTP 201 met experiment_id, name, status=DRAFT, message
- **Foutrespons:** HTTP 400 bij < 2 varianten of validatiefout; HTTP 500 bij interne fout
- **Uitzonderingen:** ImportError op ExperimentManager leidt tot HTTP 500

### Flow 2: Experiment lifecycle (start/pause/stop)

- **Actor:** Authenticated admin user
- **Voorwaarde:** Geldige JWT met ADMIN_ALL scope; experiment bestaat en is in juiste status
- **Actie:** POST /api/v1/experiments/{experiment_id}/start|pause|stop
- **Systeemverwerking:** ExperimentManager.start_experiment() / pause / stop; status update
- **Succesrespons:** HTTP 200 met experiment_id, nieuwe status, message
- **Foutrespons:** HTTP 400 bij ongeldige statusovergang (ValueError); HTTP 500 bij interne fout
- **Uitzonderingen:** UUID parsing faalt -> HTTP 422 (FastAPI validatie)

### Flow 3: Variant toewijzen (POST /api/v1/experiments/{experiment_id}/assign)

- **Actor:** Authenticated user met AGENTS_WRITE scope
- **Voorwaarde:** Experiment is actief; experience_id >= 1
- **Actie:** POST /api/v1/experiments/{experiment_id}/assign met AssignVariantRequest
- **Systeemverwerking:** ExperimentManager.assign_variant() met optionele stratificatie-key
- **Succesrespons:** HTTP 200 met experiment_id, experience_id, variant naam, assigned_at (UTC)
- **Foutrespons:** HTTP 400 bij experience_id < 1 of ongeldige assignment; HTTP 500 bij interne fout
- **Uitzonderingen:** Geen actief experiment -> HTTP 400 (ValueError)

### Flow 4: Statistieken ophalen (GET /metrics, POST /results, GET /active)

- **Actor:** Authenticated user met AGENTS_READ scope
- **Voorwaarde:** Geldige JWT; experiment bestaat
- **Actie:** GET /{id}/metrics of POST /{id}/results of GET /active
- **Systeemverwerking:** ExperimentManager.get_variant_metrics() / calculate_significance() / list_experiments()
- **Succesrespons:** HTTP 200 met metrics dict / significance list / experiment list
- **Foutrespons:** HTTP 400 bij ongeldige confidence_level; HTTP 500 bij interne fout
- **Uitzonderingen:** Lege resultatenset -> lege dict/list retourneren (geen fout)
