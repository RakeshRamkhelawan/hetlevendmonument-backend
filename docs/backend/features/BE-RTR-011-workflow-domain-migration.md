# BE-RTR-011 — Workflow Domain Migration naar v1/workflow/ (SP-API-003 Dag 1)

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-RTR-011 |
| Sprint | SP-API-003 Dag 1 |
| Datum | 2026-06-03 |
| ADR | ADR-033 (Strangler Fig, Laag 2) |
| Status | DONE |

## Samenvatting

9 workflow flat bestanden (`src/core/api/workflow_*.py`) zijn gemigreerd naar een
domeinpakket `src/core/api/v1/workflow/` conform ADR-033 drie-laags compositie.

De flat bestanden blijven bestaan als re-exports (legacy shim) totdat de hard cutover
in week 8 plaatsvindt.

## Nieuwe Bestanden

| Bestand | Regels | Rol |
|---------|--------|-----|
| `src/core/api/v1/workflow/__init__.py` | 14 | Laag 2: exporteert `domain_router` |
| `src/core/api/v1/workflow/router.py` | 36 | Laag 2: composite router (include_router per sub) |
| `src/core/api/v1/workflow/dependencies.py` | 11 | Gedeelde dependencies (get_db, require_scopes) |
| `src/core/api/v1/workflow/workflow_crud_router.py` | ~200 | Laag 1: CRUD endpoints |
| `src/core/api/v1/workflow/workflow_execution_router.py` | ~200 | Laag 1: execution + cancel endpoints |
| `src/core/api/v1/workflow/workflow_suggestions_router.py` | 10 | Laag 1: re-export suggestions |
| `src/core/api/v1/workflow/workflow_builder_router.py` | 10 | Laag 1: re-export builder |
| `src/core/api/v1/workflow/workflow_versioning_router.py` | 10 | Laag 1: re-export versioning |
| `src/core/api/v1/workflow/workflow_generation_router.py` | 10 | Laag 1: re-export vibe/generation |
| `src/core/api/v1/workflow/workflow_execution_ap_router.py` | 10 | Laag 1: re-export AP execution |
| `src/core/api/v1/workflow/workflow_refinement_router.py` | 10 | Laag 1: re-export refinement |
| `src/core/api/v1/workflow/workflow_feedback_router.py` | 10 | Laag 1: re-export feedback |
| `src/core/api/v1/workflow/workflow_visualization_router.py` | 10 | Laag 1: re-export visualization |

## Gewijzigde Bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/registries/workflows.py` | Importeert nu `domain_router` i.p.v. 9 flat imports (66r, was 74r) |
| `src/core/api/workflow_endpoints.py` | Re-export van `workflow_crud_router.router` |
| `src/core/api/workflow_suggestions_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_builder_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_versioning_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_generation_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_execution_ap_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_refinement_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_execution_feedback_endpoints.py` | `# orphan:exempt` toegevoegd |
| `src/core/api/workflow_visualization_endpoints.py` | `# orphan:exempt` toegevoegd |
| `tests/architecture/test_registry_equivalence.py` | `test_workflow_flat_files_migrated_to_v1` toegevoegd |

## Routes (volledig behouden)

### /api/v1/workflows (CRUD)
- `POST /` — workflow aanmaken
- `GET /` — lijst met paginering
- `GET /stats` — statistieken
- `GET /{workflow_id}` — opvragen
- `PUT /{workflow_id}` — updaten (nieuwe versie)
- `DELETE /{workflow_id}` — soft-delete

### /api/v1/workflows (Execution)
- `POST /{workflow_id}/execute` — starten
- `GET /executions/{execution_id}` — status
- `GET /executions` — lijst
- `POST /executions/{execution_id}/cancel` — annuleren (scoped)
- `POST /{execution_id}/cancel` — annuleren (rbac)
- `GET /{execution_id}/cancel-status` — cancel-status

### Overige prefixes (via re-exports)
- `/api/v1/workflows/suggestions/*` — AI-suggesties
- `/api/v1/builder/*` — workflow builder
- `/api/v1/workflows/versions/*` — versioning
- `/api/v1/vibe/*` — VIBE generatie
- `/api/v1/workflows/execute`, `/executions/*` — ActivePieces
- `/api/v1/workflows/refine/*` — refinement
- `/api/v1/workflows/feedback/*` — feedback
- `/api/v1/workflows/visual/*` — visualisatie

## Trainingssamenvatting

### Flow 1: Workflow aanmaken via API

| Stap | Detail |
|------|--------|
| Actor | Authenticated API client |
| Voorwaarde | JWT met `workflows:write` scope en `tenant_id` claim |
| Actie | `POST /api/v1/workflows/` met `WorkflowCreateRequest` body |
| Systeemverwerking | `workflow_crud_router` valideert tenant via `get_tenant()`, roept `WorkflowService.create_workflow()` aan, persist naar PostgreSQL |
| Succesrespons | HTTP 201 `{"workflow_id": "...", "version": 1, "status": "created", ...}` |
| Foutrespons | HTTP 400 bij ontbrekende tenant context; HTTP 403 bij ontbrekende scope |
| Uitzonderingen | `WorkflowService` kan `raise_validation_error` gooien bij dubbele `workflow_id` |

### Flow 2: Workflow executie starten

| Stap | Detail |
|------|--------|
| Actor | Authenticated API client |
| Voorwaarde | JWT met `workflows:write` scope; workflow bestaat en is actief |
| Actie | `POST /api/v1/workflows/{workflow_id}/execute` |
| Systeemverwerking | `workflow_execution_router` maakt `WorkflowExecution` record aan, zet status `PENDING`, stuurt in productie naar Dramatiq actor; in TESTING mode inline sync uitvoering |
| Succesrespons | HTTP 202 `{"execution_id": "exec_...", "status": "pending", ...}` |
| Foutrespons | HTTP 404 als workflow niet gevonden; HTTP 403 bij ontbrekende scope |
| Uitzonderingen | Worker niet beschikbaar: executie blijft op `PENDING`, log error, request slaagt toch |

### Flow 3: Workflow domain router registratie

| Stap | Detail |
|------|--------|
| Actor | FastAPI startup (`create_app()`) |
| Voorwaarde | `registries/workflows.py` geregistreerd in `router_registry.py` |
| Actie | `register(app)` aangeroepen synchroon vóór lifespan |
| Systeemverwerking | `domain_router` van `v1/workflow/__init__.py` bevat alle sub-routers via lazy import |
| Succesrespons | Alle workflow routes beschikbaar; count = 1 (domain_router) + overige |
| Foutrespons | ImportError bij kapotte sub-router: wordt gelogd, app start niet |
| Uitzonderingen | Sync-routers worden via `try/except` geladen met fallback-logging |
