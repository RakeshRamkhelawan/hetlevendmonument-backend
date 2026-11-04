# BE-SVC-054 — LLM-C7-005 BudgetManager Wiring in ExternalAgentService

**Sprint:** SP-SEC-002 Dag 1
**Datum:** 2026-07-01
**Status:** APPROVED

## Samenvatting

`ExternalAgentService.get_next_task()` roept nu `budget_manager.check_budget()` aan voor taak-uitgifte. Budget-overschrijding retourneert `None` (geen taak). `_NullBudgetManager` retourneert nu een typed `_NullBudgetResult` dataclass i.p.v. een dict, waardoor de call-site uniform `result.allowed` kan gebruiken.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/company/external_agent_router.py` | `_NullBudgetResult` dataclass + `_NullBudgetManager.check_budget()` retourneert typed object |
| `src/core/company/external_agent_service.py` | `logging` toegevoegd + budget-check in `get_next_task()` |
| `tests/unit/llm/test_budget_manager_enforcement.py` | Nieuw — 3 tests (called_once, returns_None, null_manager) |

## Implementatiedetail

```python
# external_agent_router.py
@dataclass
class _NullBudgetResult:
    allowed: bool = True
    remaining_tokens: int = 10_000_000
    ...

# external_agent_service.py (get_next_task, na agent-check)
if self.budget_manager is not None:
    budget_result = await self.budget_manager.check_budget(
        tenant_id=tenant_id,
        agent_id=str(agent_id),
        estimated_tokens=1,
    )
    if not budget_result.allowed:
        logger.warning("budget exceeded ...")
        return None
```

## ADR-compliance

- ADR-003: tenant_id uit context, niet uit body.
- ADR-033: geen directe domain-import vanuit agents-namespace in router (lokale `_NullBudgetResult` i.p.v. import vanuit `src.core.agents`).

## Bekende beperking

`NOTE in code`: wanneer de echte `BudgetManager` in de container wordt bewired, moet een factory-patroon gebruikt worden i.p.v. een singleton, zodat elke request een verse sessie krijgt. Dit is gedocumenteerd in de code als TODO voor de volgende sprint.

## Testbewijs

```
tests/unit/llm/test_budget_manager_enforcement.py — 3 passed
```

## Trainingssamenvatting

- Actor: Externe agent die communiceert via `X-API-Key: agent_id:api_key` header.
- Voorwaarde: Externe agent bestaat in de database; api_key is geldig; tenant context is opgelost.
- Actie (request): Verstuur `GET /api/v1/agents/{agent_id}/tasks/next` met geldige `X-API-Key` header.
- Systeemverwerking: `ExternalAgentService.get_next_task` haalt de agent op, verifieert optioneel de API key, roept `budget_manager.check_budget(tenant_id, agent_id=str(agent_id), estimated_tokens=1)` aan en retourneert `None` indien `result.allowed` False is; anders wordt de eerste pending task opgehaald en als `TaskNextResponse` teruggegeven.
- Succesrespons: HTTP 200 met `{"success": True, "data": <TaskNextResponse serialisatie>}` of `{"success": True, "data": null}` als er geen taak is.
- Foutrespons: HTTP 401/403/404 bij authenticatie- of agent-problemen; HTTP 502 `Workflow dispatch mislukt` bij runtime dispatch-fouten.
- Uitzonderingen: `_NullBudgetManager` is een fallback die altijd `allowed=True` retourneert; TODO in code merkt op dat een echte `BudgetManager` via een factory moet worden geinjecteerd.
