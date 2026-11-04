# BE-AGT-002: CriticAgent Wiring in MasterOrchestratorAgent (CG-006)

**Sprint:** SP-WE-11
**ADR:** ADR-023 (5-tier agent routing + CriticAgent quality gate)
**Bevinding:** CG-006
**Status:** IMPLEMENTED
**Datum:** 2026-06-01

---

## Samenvatting

`MasterOrchestratorAgent._delegate_sub_task()` roept nu `self.post_process_task()` aan
via `CriticMixin` na elke succesvolle subtaak-uitvoering. De eerdere implementatie gebruikte
`cast(Any, self._critic)` (Any-antipatroon) en constructor-injectie -- beide vervangen door
het bestaande CriticMixin-patroon dat al gebruikt wordt door `AgentHealthMonitorAgent`,
`AgentRouterAgent` en `CodeAgent`.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/master_orchestrator_agent.py` | Verwijderd: `critic` constructor-param, `self._critic`, `cast(Any, ...)` blok; toegevoegd: `post_process_task()` aanroep met best_effort wrapper; docstring gecorrigeerd SILENT->ADVISORY |
| `tests/unit/test_sp_we_11_critic_orchestrator_wiring.py` | 8 TDD tests (nieuw) |
| `tests/unit/test_sp_we_11_critic_injection.py` | Vervangen door redirect-comment naar nieuw testbestand |

---

## Architectuurbeslissingen

### A: CriticMixin.post_process_task() hergebruiken

`MasterOrchestratorAgent` erft al van `CriticMixin` met `CriticMode.ADVISORY`. De aanroep
`self.post_process_task(result, task_id=sub_task.sub_task_id)` volgt het bestaande patroon
van de drie andere agents. Directe `CriticAgent`-aanroep via constructor-injectie is verwijderd.

### B: Best_effort wrapper in _delegate_sub_task

`post_process_task()` heeft ingebouwde exception-handling (critic_mixin.py:193-198) maar de
mock in tests kan de echte implementatie overrulen. Een extra try/except in `_delegate_sub_task`
garandeert dat critic-fouten het primaire `ExecutionResult` nooit vernietigen.

### C: Geen aanroep in except-pad

Gefaalde delegaties (router crash) produceren een fallback `ExecutionResult(success=False)`
zonder zinvolle output. `post_process_task()` wordt NIET aangeroepen in het except-pad.

---

## Trainingssamenvatting

### Flow 1: Subtaak-evaluatie via CriticAgent in MasterOrchestratorAgent

| Attribuut | Waarde |
|---|---|
| Actor | `MasterOrchestratorAgent._delegate_sub_task()` (via CriticMixin) |
| Voorwaarde | `route_and_execute()` heeft een `ExecutionResult` teruggegeven; `sub_task.result` en `sub_task.status` zijn al gezet; CriticMixin geinitialiseerd met `CriticMode.ADVISORY` en `score_threshold=0.60` |
| Actie | `result = await self.post_process_task(result, task_id=sub_task.sub_task_id)` aangeroepen; gewrapped in try/except (best_effort) |
| Systeemverwerking | `CriticMixin.post_process_task()` haalt `CriticAgent` op via `get_critic_agent(tenant_id=self.tenant_id)`; `critique_task()` wordt aangeroepen met agent_name en task_id; critique asynchroon opgeslagen in CritiqueStore |
| Succesrespons | `ExecutionResult` (identiek aan input) teruggegeven; Critique in CritiqueStore voor latere analyse |
| Foutrespons | Bij exception in `post_process_task()`: WARNING gelogd met `type(exc).__name__` en `exc_info=True`; primaire `result` teruggegeven ongewijzigd |
| Uitzonderingen | (1) Router crash -> except-pad -> geen `post_process_task` aanroep; (2) `CriticAgent` per-tenant singleton via `critic_agent.py:106-111`; (3) ADVISORY mode blokkeert caller niet |

### Flow 2: Verwijdering constructor-injectie antipatroon

| Attribuut | Waarde |
|---|---|
| Actor | Codebase (statisch) |
| Voorwaarde | `critic: CriticAgent | None = None` parameter en `self._critic = critic` aanwezig; `cast(Any, self._critic)` gebruikt (Any-antipatroon) |
| Actie | Parameter, opslag en cast-blok verwijderd; TYPE_CHECKING import voor CriticAgent verwijderd |
| Systeemverwerking | CriticMixin lazy-load via `get_critic_agent()` per aanroep in `post_process_task()` |
| Succesrespons | mypy 0 errors; geen `Any` cast; geen externe constructor-afhankelijkheid |
| Foutrespons | N.v.t. (statische verwijdering) |
| Uitzonderingen | Bestaande code die `MasterOrchestratorAgent(critic=...)` aanroept breekt; grep bevestigt 0 externe callsites buiten de verwijderde test |

---

## Tests

| Test | Status |
|------|--------|
| `test_post_process_task_called_on_success` | PASS |
| `test_post_process_task_called_with_correct_task_id` | PASS |
| `test_post_process_task_not_called_on_delegation_exception` | PASS |
| `test_critic_failure_does_not_destroy_primary_result` | PASS |
| `test_no_constructor_critic_parameter` | PASS |
| `test_failed_subtask_also_goes_through_post_process` | PASS |
| `test_tenant_isolation_separate_critics` | PASS |
| `test_existing_process_task_flow_unbroken` | PASS |
