# BE-UTL-005: ExecutionGuard Wiring in CopilotService (B-003)

## Build Summary

SP-H04 scope: verifiëren dat ExecutionGuard correct is gewired in CopilotService.
Audit beweerde dat ExecutionGuard "nergens werd aangeroepen" — code-archeologie toont aan dat de wiring AL BESTAAT en correct is:
- `ExecutionGuard` wordt geinjecteerd in `CopilotService` via `dependencies.py`
- `_execute_decision()` roept `start_execution()` / `finish_execution()` correct aan
- Redis `SET NX` garandeert atomiciteit

Nieuw geleverd: 7 unit tests die de wiring expliciet verifiëren.

## Backend Inventory

| Artefact | Type | Locatie | Wijziging |
|----------|------|---------|-----------|
| `CopilotService._execute_decision()` | Service-methode | `src/core/copilot/service.py` | Bestaand — geverifieerd |
| `CopilotService.__init__()` | Constructor | `src/core/copilot/service.py` | Bestaand — geverifieerd |
| `_build_copilot_service()` | Dependency factory | `src/core/copilot/dependencies.py` | Bestaand — geverifieerd |
| `ExecutionGuard` | Idempotency class | `src/core/copilot/execution/idempotency.py` | Bestaand — geverifieerd |
| `test_sp_h04_executionguard_wiring.py` | Unit tests | `tests/unit/test_sp_h04_executionguard_wiring.py` | Nieuw |

## Functionele specificatie

### ExecutionGuard flow
- **Trigger:** `CopilotService._execute_decision()` wordt aangeroepen met een APPROVED CouncilDecision
- **Voorwaarde:** `execution_guard` is geinjecteerd (niet None)
- **Actie 1:** `guard.start_execution(decision_id)` probeert een Redis NX lock te acquireren
- **Voorwaarde 2:** Als lock al actief is → executie wordt overgeslagen (geen dubbele tool call)
- **Actie 2:** Tool wordt uitgevoerd via ToolBroker
- **Actie 3a (succes):** `guard.finish_execution(decision_id, SUCCESS)` + audit binding
- **Actie 3b (fout):** `guard.finish_execution(decision_id, FAILED)` + audit binding + re-raise

## Technische specificatie

### Idempotency key
```python
key = f"copilot:exec:{decision_id}"  # decision_id is UUID
```

### Redis operaties
- `SET key "PROCESSING" EX 60 NX` — atomische lock-acquisitie
- `SET key "SUCCESS" EX 3600` — langdurige bescherming tegen re-runs
- `SET key "FAILED" EX 60` — korte TTL zodat retry mogelijk is

### Constructor injectie (dependencies.py)
```python
redis = await get_redis_client()
execution_guard = ExecutionGuard(redis)
return CopilotService(..., execution_guard=execution_guard)
```

## Trainingssamenvatting

| Stap | Beschrijving |
|------|-------------|
| Actor | Systeem (CopilotService._execute_decision) |
| Voorwaarde | Council heeft APPROVED verdict gegeven; execution_guard is geinjecteerd |
| Actie | Roep start_execution(decision_id) aan |
| Systeemreactie | Redis SET NX: True (lock acquired) of False (already processing) |
| Succesrespons | Tool executed; finish_execution(SUCCESS); result returned |
| Foutrespons | Tool failed; finish_execution(FAILED); exception re-raised; audit logged |
| Uitzonderingen | Lock already active → return None (skip execution) |

## Acceptatiecriteria

- [x] ExecutionGuard wordt geinjecteerd in CopilotService
- [x] `_execute_decision` roept `start_execution` vóór tool execution
- [x] `_execute_decision` roept `finish_execution(SUCCESS)` na succes
- [x] `_execute_decision` roept `finish_execution(FAILED)` na exception
- [x] Dubbele executie wordt geblokkeerd door Redis NX lock
- [x] Audit binding wordt aangeroepen bij zowel succes als falen
- [x] 7 unit tests pass, 0 regressies

## Open aannames

- `handle_turn` en `submit_proactive_proposal` callers vangen execution exceptions niet af — dit is een pre-existing design keuze buiten SP-H04 scope
- `_get_available_agents` filtert niet op tenant_id — pre-existing, buiten scope
