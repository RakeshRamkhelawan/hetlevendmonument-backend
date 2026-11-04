# BE-SVC-068: AgenticOrchestrationService (ADR-033 S5 -- DB-14a)

## Overzicht

Nieuwe service-laag voor agentic workflow orchestratie. Voldoet aan ADR-033: de
composite `agentic/router.py` delegeert alle DB-operaties aan `AgenticOrchestrationService`
via `Depends(get_agentic_orchestration_service)`.

## Sprint

AUDIT-SINGLE-TENANT-DB01 S5

## Datum

2026-07-01

## Nieuwe bestanden

| Bestand | Rol |
|---------|-----|
| `src/core/api/v1/agentic/orchestration_service.py` | `AgenticOrchestrationService` + `AgenticWorkflowConfig` |
| `src/core/api/v1/agentic/workflow_router.py` | 4 endpoints (ADR-033 Laag 1, geen DB-imports) |

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/agentic/dependencies.py` | `get_agentic_orchestration_service` factory toegevoegd |
| `src/core/api/v1/agentic/router.py` | `workflow_router` opgenomen in composite |

## Endpoints

| Methode | Path | Omschrijving |
|---------|------|--------------|
| POST | `/api/v1/agentic/workflow/start` | Workflow dispatchen (TI-004: tenant_id vereist) |
| GET | `/api/v1/agentic/workflow/{task_id}/status` | Status opvragen (tenant-gefilterd) |
| POST | `/api/v1/agentic/workflow/{task_id}/step` | Volgende stap activeren |
| DELETE | `/api/v1/agentic/workflow/{task_id}` | Workflow annuleren |

## ADR-conformiteit

- **ADR-033**: `workflow_router.py` bevat geen `get_db`/`AsyncSession`/`select`/`update`/`delete` imports
- **ADR-003**: `tenant_id` via `Depends(require_tenant_id)`, nooit uit request body
- **TI-004**: `start_workflow` gooit `ValueError` als `tenant_id == 0`
- **ADR-010**: Dramatiq dispatch via bestaande `execute_workflow_step` actor (geen nieuwe actor nodig)

## Tests

| Test | Type | Status |
|------|------|--------|
| `test_agentic_workflow_router_exists` | architecture | GROEN |
| `test_agentic_workflow_router_no_direct_db_imports` | architecture | GROEN |
| `test_agentic_workflow_router_included_in_composite` | architecture | GROEN |
| `test_agentic_orchestration_service_importable` | unit | GROEN |
| `test_agentic_orchestration_service_accepts_db_and_tenant_id` | unit | GROEN |
| `test_start_workflow_dispatches_with_tenant_id` | unit | GROEN |
| `test_start_workflow_raises_on_missing_tenant_id` | unit | GROEN |

## Trainingssamenvatting

- Actor: Geauthenticeerde client met geldige JWT waarin een tenant_id is opgenomen.
- Voorwaarde: `workflow_router` is opgenomen in de agentic composite router; `get_agentic_orchestration_service` is beschikbaar in `src/core/api/v1/agentic/dependencies.py`.
- Actie (request): Verstuur `POST /api/v1/agentic/workflow/start` met body `{"name": "...", "steps": [...], "metadata": {...}}`.
- Systeemverwerking: De dependency factory maakt `AgenticOrchestrationService(db=db, tenant_id=tenant_id)`; `start_workflow` valideert dat `tenant_id` niet 0 is en stuurt een Dramatiq-bericht via `execute_workflow_step.send({...})`.
- Succesrespons: HTTP 200 met body `{"success": True, "data": {"status": "dispatched", "name": "..."}}`.
- Foutrespons: HTTP 502 `Workflow dispatch mislukt` bij `RuntimeError`; HTTP 401/403/422 indien de tenant niet is opgelost.
- Uitzonderingen: `GET /{task_id}/status`, `POST /{task_id}/step` en `DELETE /{task_id}` zijn stubs die direct een success-wrapped dictionary retourneren.
