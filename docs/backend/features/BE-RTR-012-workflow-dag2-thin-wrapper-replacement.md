# BE-RTR-012 — Workflow Dag 2: Thin Wrapper Replacement + Execution Split

**Sprint:** SP-API-003 Dag 2
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-06-04
**Type:** BE-RTR (router)

---

## Samenvatting

Alle 8 thin wrappers in `src/core/api/v1/workflow/` zijn vervangen door echte implementaties
(volledige routerlogica gemigreerd vanuit de legacy flat files in `src/core/api/`).

Daarnaast is `workflow_execution_router.py` (449r) gesplitst in twee sub-routers:
- `workflow_execution_core_router.py` — execute/status/list (290r)
- `workflow_execution_cancel_router.py` — cancel/cancel-status (186r)

---

## Gewijzigde bestanden

| Bestand | Van | Naar | Actie |
|---------|-----|------|-------|
| `workflow_execution_router.py` | 449r echte implementatie | backward-compat wrapper | Split |
| `workflow_execution_core_router.py` | nieuw | 290r execute+status+list | Nieuw |
| `workflow_execution_cancel_router.py` | nieuw | 186r cancel+cancel-status | Nieuw |
| `workflow_visualization_router.py` | 8r thin wrapper | 78r echte implementatie | Vervangen |
| `workflow_feedback_router.py` | 9r thin wrapper | 208r echte implementatie | Vervangen |
| `workflow_refinement_router.py` | 9r thin wrapper | 228r echte implementatie | Vervangen |
| `workflow_execution_ap_router.py` | 11r thin wrapper | 280r echte implementatie | Vervangen |
| `workflow_generation_router.py` | 9r thin wrapper | 259r echte implementatie | Vervangen |
| `workflow_versioning_router.py` | 11r thin wrapper | 383r echte implementatie | Vervangen |
| `workflow_builder_router.py` | 8r thin wrapper | 434r echte implementatie | Vervangen |
| `workflow_suggestions_router.py` | 10r thin wrapper | 579r echte implementatie | Vervangen |
| `router.py` | 10 sub-routers | 11 sub-routers (execution split) | Bijgewerkt |

---

## Architectuur (ADR-033 Laag 1)

Elk sub-router bestand:
- Heeft `# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)`
- Bestanden >200 regels krijgen `# orphan:exempt` conform de project-richtlijn
- Geen directe imports van `src.core.database`, `src.core.governance`, `src.core.learning`, `src.core.agents`, `src.core.workflow`, `src.core.llm` in router bestanden (alleen via deferred imports of dependencies.py)
- Geen f-strings in logger-aanroepen
- Alle exceptions: `exc_info=True` bij logger.error

---

## Routes (per sub-router)

### workflow_execution_core_router.py
- `POST /api/v1/workflows/{workflow_id}/execute`
- `GET  /api/v1/workflows/executions/{execution_id}`
- `GET  /api/v1/workflows/executions`

### workflow_execution_cancel_router.py
- `POST /api/v1/workflows/executions/{execution_id}/cancel`
- `POST /api/v1/workflows/{execution_id}/cancel`
- `GET  /api/v1/workflows/{execution_id}/cancel-status`

### workflow_visualization_router.py
- `GET  /api/v1/workflows/visual/sops/{sop_id}`
- `POST /api/v1/workflows/visual/sops/{sop_id}`

### workflow_feedback_router.py
- `POST /api/v1/workflows/feedback/executions/{id}/feedback`
- `GET  /api/v1/workflows/feedback/executions/{id}/insights`
- `POST /api/v1/workflows/feedback/executions/{id}/auto-improve`

### workflow_refinement_router.py
- `POST /api/v1/workflows/refine/chat`
- `POST /api/v1/workflows/refine/refine`
- `GET  /api/v1/workflows/refine/insights/{workflow_id}`

### workflow_execution_ap_router.py
- `POST /api/v1/workflows/execute`
- `GET  /api/v1/workflows/executions/{run_id}/status`
- `GET  /api/v1/workflows/flows/{flow_id}/executions`
- `GET  /api/v1/workflows/activepieces/health`
- ~~`POST /api/v1/workflows/ap/{workflow_id}/execute`~~ -- verwijderd 2026-10-08 (wfb-dag1 stap 1): nam de tenant uit de query en gaf altijd 501 (model `Workflow` bestaat niet); geen aanroeper.

### workflow_generation_router.py
- `POST      /api/v1/vibe/generate`
- `GET       /api/v1/vibe/agents`
- `WEBSOCKET /api/v1/vibe/ws/generate`
- `GET       /api/v1/vibe/health`
- `WEBSOCKET /api/v1/vibe/ws/generate/secure`

### workflow_versioning_router.py
- `POST /api/v1/workflows/{workflow_id}/versions`
- `GET  /api/v1/workflows/{workflow_id}/versions`
- `GET  /api/v1/workflows/{workflow_id}/versions/{version_number}`
- `POST /api/v1/workflows/{workflow_id}/versions/{version_number}/rollback`
- `GET  /api/v1/workflows/{workflow_id}/compare`

### workflow_builder_router.py
- `POST /api/v1/builder/keywords`
- `POST /api/v1/builder/suggest`
- `GET  /api/v1/builder/tools`
- `GET  /api/v1/builder/tools/{tool_id}`

### workflow_suggestions_router.py
- `GET /api/v1/workflows/suggestions/{workflow_id}/suggestions`
- `GET /api/v1/workflows/suggestions/{workflow_id}/variants`

---

## Kwaliteitsregels (geverifieerd)

- [x] Geen f-strings in logger-aanroepen
- [x] `except Exception as e:` altijd met `exc_info=True` bij logger.error
- [x] Geen `from __future__ import annotations`
- [x] `# orphan:exempt` op alle bestanden die >200r zijn of Laag 1 sub-routers zijn
- [x] Imports van zware modules (agents, llm, workflow) uitgesteld via deferred imports
- [x] `datetime.now(timezone.utc)` (geen `datetime.utcnow()`)

---

## Trainingssamenvatting

### Flow 1: Execute workflow (POST /workflows/{id}/execute)

| Stap | Beschrijving |
|------|-------------|
| **Actor** | Authenticated tenant user met WORKFLOWS_WRITE scope |
| **Voorwaarde** | Geldig JWT met tenant_id claim; workflow bestaat en is actief |
| **Actie** | POST met optionele `input_data` en `version` |
| **Systeemverwerking** | Tenant-isolated DB query; WorkflowExecution record aangemaakt; Dramatiq actor enqueued (of sync in TESTING) |
| **Succesrespons** | 202 Accepted: `{"execution_id": "...", "status": "pending"}` |
| **Foutrespons** | 404 als workflow niet gevonden; 422 bij validatiefout |
| **Uitzonderingen** | Enqueue-fouten worden gelogd maar blokkeren de response niet |

### Flow 2: Get execution status (GET /workflows/executions/{id})

| Stap | Beschrijving |
|------|-------------|
| **Actor** | Authenticated tenant user met WORKFLOWS_READ scope |
| **Voorwaarde** | Execution bestaat voor deze tenant |
| **Actie** | GET met execution_id in path |
| **Systeemverwerking** | Tenant-isolated query op WorkflowExecution; workflow-name opgehaald via join |
| **Succesrespons** | 200: ExecutionStatusResponse met status, duration, task counts |
| **Foutrespons** | 404 als execution niet gevonden of niet van deze tenant |
| **Uitzonderingen** | duration=None als start/end niet ingevuld |

### Flow 3: Cancel execution (POST /workflows/{execution_id}/cancel)

| Stap | Beschrijving |
|------|-------------|
| **Actor** | Authenticated tenant user met workflow:cancel permission |
| **Voorwaarde** | Execution bestaat, is van deze tenant, is niet al in terminal state |
| **Actie** | POST met optionele `reason` |
| **Systeemverwerking** | GracefulCanceller roept CancellationScope aan; bij success: status=CANCELLED in DB |
| **Succesrespons** | 200: CancelWorkflowResponse met `success=true` |
| **Foutrespons** | 404 execution niet gevonden; 403 cross-tenant; 409 al in terminal state |
| **Uitzonderingen** | CancellationScope-fouten geven `success=false` in response (geen 500) |

### Flow 4: Generate workflow (POST /vibe/generate)

| Stap | Beschrijving |
|------|-------------|
| **Actor** | Authenticated user |
| **Voorwaarde** | Geldig JWT; prompt minimaal 10 tekens |
| **Actie** | POST met `prompt` en `complexity` |
| **Systeemverwerking** | WorkflowGenerator initialiseert; LLM genereert workflow graph |
| **Succesrespons** | 200: VibeGenerateResponse met `workflow` dict, node/edge counts |
| **Foutrespons** | 200 met `success=false` en `error` string bij generatiefout |
| **Uitzonderingen** | Generator.is_mock=true in test-omgeving |

### Flow 5: Get workflow suggestions (GET /suggestions/{id}/suggestions)

| Stap | Beschrijving |
|------|-------------|
| **Actor** | Authenticated tenant user met WORKFLOWS_READ scope |
| **Voorwaarde** | Workflow bestaat, actief, van deze tenant |
| **Actie** | GET met optionele `category`, `min_confidence`, `limit` filters |
| **Systeemverwerking** | analyze_workflow_patterns analyseert spec; suggestions gesorteerd op prioriteit+confidence |
| **Succesrespons** | 200: WorkflowSuggestionsResponse met gefilterde suggestions |
| **Foutrespons** | 404 workflow niet gevonden |
| **Uitzonderingen** | Lege spec geeft 0 suggestions |
