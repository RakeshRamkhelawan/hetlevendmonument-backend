# BE-WFL-005 -- WorkflowService AuditService Integratie

## Metadata

- Feature ID: BE-WFL-005
- Feature naam: WorkflowService AuditService Integratie
- Status: GEREED
- Auteur: Rakesh Ramkhelawan
- Reviewer: self-review (< 50 regels, 1 bestand)
- Datum: 2026-06-30
- Gerelateerde user story / ticket: SP-ADR023 fase-2 open items
- Gerelateerde router / module: `src/domains/workflows/services.py`
- Gerelateerde database tabellen: `audit_logs` (indirect via AuditService, geen sessie)
- Versie: 1.0

---

## Doel en scope

### Doel

WorkflowService logt executieresultaten naar de ADR-019 audit trail zodat workflow-executies
traceerbaar zijn in het auditlog (WORKFLOW_EXECUTED / WORKFLOW_FAILED).

### In scope

- `AuditService` optioneel injecteren via `WorkflowService.__init__(audit_service=...)`
- `best_effort` audit-call na geslaagde workflow-executie (action=WORKFLOW_EXECUTED)
- `best_effort` audit-call na gefaalde workflow-executie, zowel via step-failures als uncaught exceptions (action=WORKFLOW_FAILED)
- Geen AsyncSession injectie -- log_action wordt zonder session aangeroepen (system-logger fallback)

### Out of scope

- AsyncSession injectie in WorkflowService (fase 2, vereist DI-refactor)
- DB-persistentie van auditlog in deze fase (zonder session: alleen system-log)
- LLMProviderFactory wiring (BE-WFL-006)

---

## Build summary

- Nieuw gebouwd: --
- Gewijzigd: `src/domains/workflows/services.py` (imports + __init__ + 3 best_effort blokken)
- Verwijderd: --
- Beinvloede bestaande flows: WorkflowService.execute_workflow() -- geen gedragswijziging voor callers zonder audit_service

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SVC-WFL-005a | WorkflowService.__init__ audit_service param | Service-wijziging | `src/domains/workflows/services.py` | Wijziging | BE-WFL-005 |
| BE-SVC-WFL-005b | execute_workflow success-pad audit | Service-wijziging | `src/domains/workflows/services.py` | Wijziging | BE-WFL-005 |
| BE-SVC-WFL-005c | execute_workflow failed-pad audit | Service-wijziging | `src/domains/workflows/services.py` | Wijziging | BE-WFL-005 |

---

## API-flows

### Flow: WorkflowService.execute_workflow() met AuditService

- Naam: Workflow executie met audit logging
- Trigger: `await workflow_service.execute_workflow(workflow)`
- Voorwaarden: `audit_service` aanwezig in `WorkflowService`
- Service-stappen:
  1. `workflow.start()` -- status = RUNNING
  2. Itereer over steps via `_execute_step()`
  3a. Succes: `workflow.complete(...)` -> `best_effort` -> `AuditService.log_action(action=WORKFLOW_EXECUTED)`
  3b. Step-failure: `workflow.fail(...)` -> `best_effort` -> `AuditService.log_action(action=WORKFLOW_FAILED)`
  3c. Uncaught exception: `workflow.fail(...)` -> `best_effort` -> `AuditService.log_action(action=WORKFLOW_FAILED)`
- DB-operaties: geen (log_action zonder session = system-log only)
- Successtatus: `{"status": "completed", "results": [...]}`
- Foutpaden: `{"status": "failed", "error": "..."}` -- audit-call nooit blocking
- Eindtoestand: auditlog in system-logger, workflow.status = COMPLETED of FAILED

---

## Detaildocumentatie per artefact

---

## [BE-SVC-WFL-005a] WorkflowService.__init__ audit_service param

### 1. Type

Service-constructor uitbreiding

### 2. Locatie

- Bestandspad: `src/domains/workflows/services.py`
- Klasse / functie: `WorkflowService.__init__`

### 3. Gerelateerde flow

BE-WFL-005

### 4. Doel

AuditService optioneel injecteren voor testbaarheid en loose coupling.

### 5. Functionele beschrijving

De WorkflowService accepteert nu een optionele `audit_service` parameter. Als deze None is,
wordt er geen audit-aanroep gedaan en crasht de service niet.

### 6. Technische beschrijving

```python
def __init__(
    self,
    router: RouterAgentService | None = None,
    audit_service: AuditService | None = None,
) -> None:
    self._router = router
    self._audit_service = audit_service
```

Imports toegevoegd:
- `from src.core.governance.audit import AuditService`
- `from src.core.utils.best_effort import best_effort`

### 7. Zichtbaarheids- en toegangsregels

- Geen authenticatie vereist (interne service)
- Tenant-isolatie: `workflow.tenant_id` wordt doorgegeven aan audit_service
- Feature flag: geen

### 8. Request-specificatie

n.v.t. (service-laag, geen HTTP-endpoint)

### 9. Response-specificatie

n.v.t.

### 10. Validaties en constraints

- `audit_service` mag None zijn; dit is het standaardgeval
- `type: ignore[arg-type]` gebruikt omdat `AuditService.log_action(tenant_id: int)` maar `workflow.tenant_id` is `str`

### 11. Business rules

- Audit-aanroep mag executie nooit blokkeren of laten crashen (best_effort wrapper)
- Zonder session logt AuditService naar system-logger (geen DB-persistentie) -- acceptabel fase 1

### 12. Afhankelijkheden

- `src/core/governance/audit.py` -- AuditService
- `src/core/utils/best_effort.py` -- best_effort context manager

### 13. Foutafhandeling

- Alle exceptions in best_effort worden gelogd op ERROR-niveau en niet gere-raised

### 14. Transacties en dataïntegriteit

- Primaire workflow-state wordt voor de best_effort audit-aanroep gecommit
- Audit-aanroep zonder session heeft geen DB-transactie

### 15. Telemetry / logging / tracing

- best_effort logt bij faal op ERROR met exc_info=True
- AuditService logt waarschuwing als er geen session is

### 16. Caching

- Gecached: nee

### 17. Acceptatiecriteria

- Gegeven een WorkflowService met audit_service, na succesvolle executie: log_action(action=WORKFLOW_EXECUTED) aangeroepen met tenant_id en resource=workflow:{id}
- Gegeven een WorkflowService met audit_service, na step-failure: log_action(action=WORKFLOW_FAILED) aangeroepen
- Gegeven een WorkflowService zonder audit_service: execute_workflow voltooit zonder crash

### 18. Integratoruitleg

- Injecteer AuditService bij constructie: `WorkflowService(router=router, audit_service=audit_svc)`
- Zonder audit_service: geen auditlog maar ook geen fout
- Audit-aanroepen zijn fire-and-forget via best_effort

### 19. Trainingssamenvatting

- Actor: WorkflowService
- Voorwaarde: workflow wordt geexecuteerd; audit_service optioneel aanwezig
- Actie: execute_workflow() aanroep
- Systeemverwerking: steps uitvoeren, daarna best_effort audit-aanroep
- Succesrespons: {"status": "completed", ...}; audit WORKFLOW_EXECUTED gelogd
- Foutrespons: {"status": "failed", ...}; audit WORKFLOW_FAILED gelogd
- Uitzonderingen: audit-aanroep faalt stil via best_effort; workflow-resultaat onaangetast

---

## Integratorhandleiding

### Voor interne service-consumenten

- Injecteer `AuditService` bij het aanmaken van WorkflowService voor productie-gebruik
- Zonder injectie werkt de service identiek maar zonder auditlog
- Audit-aanroepen blokkeren de workflow-response nooit

---

## Open aannames

- Fase 1: audit zonder DB-persistentie is acceptabel (CopilotService-precedent)
- Fase 2: AsyncSession-injectie toevoegen voor volledige ADR-019 compliance

## Open vragen

- --

## Risico's

- Lage prioriteit: auditlog is niet persistent in fase 1 zonder session

---

## QA-checks

- [x] Service functioneel getest (happy path)
- [x] Audit-aanroep getest bij step-failure
- [x] Geen crash zonder audit_service getest
- [x] best_effort swallows exceptions -- gevalideerd via unit tests
- [ ] DB-persistentie van auditlog (fase 2)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle services geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar en groen
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
