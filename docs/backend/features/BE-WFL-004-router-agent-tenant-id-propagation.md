# BE-WFL-004 -- RouterAgentService tenant_id propagatie

**Sprint:** SP-ADR023-DAG2
**Datum:** 2026-06-27
**Status:** APPROVED

---

## Samenvatting

`RouterAgentService.execute_request()` en `WorkflowService._execute_step()` accepteren en propageren
nu een optionele `tenant_id: str | None` parameter. `execute_workflow()` threadt
`workflow.tenant_id` automatisch door naar elke step-aanroep.

---

## Scope

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/router_agent_service.py` | `execute_request(query, tenant_id=None)` + `"tenant_id"` in return-dict |
| `src/domains/workflows/services.py` | `_execute_step(step, tenant_id=None)` + `execute_workflow` threadt `workflow.tenant_id` |

---

## Technische beslissingen

- `tenant_id: str | None = None` (optioneel) -- backward-compatible; geen bestaande callers gebroken.
- Type `str` i.p.v. `int`: DDD domain model `Workflow.tenant_id` is `str`. Geen conversie nodig zolang
  `execute_request` niet de systeem-brede `ContextVar[int]` raakt.
- Return-dict uitbreiding met `"tenant_id": tenant_id` is additief -- geen downstream consumer breekt.
- Per-tenant LLM-credentials en `AuditService.log_action()` integratie vallen buiten scope (aparte sprint).

---

## Tests

- `test_execute_step_passes_tenant_id_to_router` -- `tenant_id` via kwarg doorgegeven aan `execute_request`
- `test_execute_workflow_threads_tenant_id_to_steps` -- `workflow.tenant_id` bereikt `execute_request`
- Beide tests waren RED voor de fix (commit `4821c115`), GROEN na de fix.
- 8 tests totaal in `tests/unit/domains/workflows/test_workflow_service_execute_step.py` -- allemaal GROEN.
- Regressiecheck: 384 tests in `tests/unit/agents/` -- 0 nieuwe failures.

---

## Niet in scope (bewuste keuze)

- Per-tenant `RouterAgentService` singleton
- `GeminiProvider` per-tenant credentials
- `AuditService.log_action()` tenant_id logging
- `None`-forwarding contract test -- toegevoegd als FA-003 minor fix na FA review (commit los van de fix)


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: ADR-023 DAG2: tenant_id propagatie -- RouterAgentService.execute_request(tenant_id=None) + WorkflowService threadt workflow.tenant_id naar elke step is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt ADR-023 DAG2: tenant_id propagatie -- RouterAgentService.execute_request(tenant_id=None) + WorkflowService threadt workflow.tenant_id naar elke step.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
