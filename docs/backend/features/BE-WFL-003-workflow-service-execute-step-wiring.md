# BE-WFL-003 -- WorkflowService._execute_step() RouterAgentService Wiring

**Status:** APPROVED
**Sprint:** SP-ADR023-DAG1
**ADR:** ADR-023 P0-4

---

## Probleemstelling

`WorkflowService._execute_step()` in `src/domains/workflows/services.py` was een actieve stub
die altijd `{"status": "not_implemented"}` retourneerde. Alle workflow-stap-uitvoering via de
`WorkflowService` was nep. `execute_workflow()` detecteerde de stub-status en markeerde
workflows direct als FAILED, waardoor workflow-automatisering volledig onbruikbaar was.

---

## Implementatie

**Bestand:** `src/domains/workflows/services.py`

### Constructor (nieuw)

```python
from src.core.agents.router_agent_service import RouterAgentService

class WorkflowService:
    def __init__(self, router: RouterAgentService | None = None) -> None:
        self._router = router
```

Backward-compatible: `WorkflowService()` zonder args werkt nog steeds.

### `_execute_step()` (herschreven)

```python
async def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
    if self._router is None:
        logger.warning(
            "WorkflowService._execute_step: no router configured -- step skipped",
            extra={"step_id": step.id, "step_name": step.name},
        )
        return {"step_id": step.id, "step_name": step.name, "status": "skipped"}

    query = step.config.get("description", step.name)
    try:
        result = await self._router.execute_request(query)
        return {
            "step_id": step.id,
            "step_name": step.name,
            "status": "completed",
            "output": result,
        }
    except Exception as exc:
        logger.opt(exception=True).error(
            "WorkflowService._execute_step failed: {}: {}",
            type(exc).__name__,
            exc,
        )
        return {
            "step_id": step.id,
            "step_name": step.name,
            "status": "failed",
            "error": str(exc),
        }
```

### `execute_workflow()` (bijgewerkt)

`"skipped"` en `"failed"` step-statussen worden beide als mislukt behandeld.
Een workflow met skipped steps rapporteert `status="failed"` (niet `"completed"`).

```python
if any(r.get("status") in ("not_implemented", "skipped", "failed") for r in results):
    workflow.fail("One or more steps did not complete successfully")
    return {"status": "failed", "error": "Step execution incomplete"}
```

### get_master_orchestrator() (MINOR, meegelift)

`threading.Lock` toegevoegd voor thread-safe singleton constructie, consistent met
`AgentRouterAgent` en `AgentHealthMonitorAgent`.

---

## Bewuste keuzen

- **`router=None` → `"skipped"`**: backward-compatible. Bestaande code die `WorkflowService()` aanroept zonder args crasht niet.
- **`query = step.config.get("description", step.name)`**: gebruikt rijkere context als aanwezig in step-config.
- **Loguru `logger.opt(exception=True).error()`**: correcte loguru-pattern voor exception logging (niet `exc_info=True`).
- **`RouterAgentService.execute_request()`**: doet routing + executie in één call; past bij het 5-tier model van ADR-023 zonder extra abstractielaag.

---

## Tests

**Nieuw:** `tests/unit/domains/workflows/test_workflow_service_execute_step.py` (5 tests)

| Test | Scenario |
|------|----------|
| `test_execute_step_with_router_returns_completed` | Router aanwezig -- status completed, output aanwezig |
| `test_execute_step_uses_config_description_as_query` | step.config.description gebruikt als query |
| `test_execute_step_without_router_returns_skipped` | Geen router -- status skipped, geen exception |
| `test_execute_step_router_failure_returns_failed` | Router raise -- status failed, error aanwezig |
| `test_execute_workflow_without_router_returns_failed` | execute_workflow zonder router -- FAILED, niet COMPLETED |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: ADR-023 P0-4: WorkflowService._execute_step() gewired naar RouterAgentService -- constructor + skipped/failed guard + threading.Lock in get_master_orchestrator() is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt ADR-023 P0-4: WorkflowService._execute_step() gewired naar RouterAgentService -- constructor + skipped/failed guard + threading.Lock in get_master_orchestrator().
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
