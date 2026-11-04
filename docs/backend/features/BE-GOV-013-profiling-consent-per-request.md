# BE-GOV-013: Per-request Profiling Consent in process_task() (GDPR-009)

**Sprint:** SP-DLP-003 Dag 2
**Status:** APPROVED
**Datum:** 2026-06-26

## Probleem

`_profiling_opted_out` was een instance-level stub (`bool = False`) toegevoegd in SP-DLP-002 Dag 4.
Dit is NIET per-user: dezelfde waarde gold voor alle taken op dezelfde agent-instantie.
GDPR Art. 21 vereist een per-request check op basis van de werkelijke gebruiker in `task.metadata`.

De falende arch test `tests/architecture/test_gdpr_009_profiling_guard.py` blokte CI tot
deze implementatie klaar was (bewust rood gelaten in SP-DLP-002).

## Implementatie

`process_task()` in `src/core/agents/base_agent.py` wired een DB-check via
`AITransparencyService.check_profiling_opt_out()` in, direct na `validate_task()` en
voor het bijhouden van concurrente taken in `_current_tasks`.

Patroon:
```python
_user_id_profiling = (
    str(task.metadata.get("user_id", ""))
    if task.metadata
    else ""
)
self._profiling_opted_out = False  # reset per-request
if _user_id_profiling and self.memory_store and isinstance(self.memory_store, dict):
    _sf = self.memory_store.get("session_factory")
    if _sf is not None:
        try:
            async with _sf as _db:
                from src.core.governance.ai_transparency_service import (
                    AITransparencyService, ProfilingType,
                )
                self._profiling_opted_out = await AITransparencyService(
                    db=_db
                ).check_profiling_opt_out(
                    user_id=_user_id_profiling,
                    tenant_id=self.tenant_id,
                    profiling_type=ProfilingType.BEHAVIORAL,
                )
        except Exception as _e:
            logger.warning("Profiling opt-out check failed (fail-closed): %s: %s", ...)
            self._profiling_opted_out = True

if self._profiling_opted_out:
    return ExecutionResult(success=False, error_message="Profiling has been disabled ...")
```

## Fail-semantics

| Situatie | Gedrag |
|----------|--------|
| `user_id` aanwezig, opted out | Fail-closed: taak geblokkeerd |
| `user_id` aanwezig, niet opted out | Doorgaan |
| Geen `user_id` in `task.metadata` | Fail-open: doorgaan (geen identiteit = geen opt-out) |
| DB-fout | Fail-closed: taak geblokkeerd, `logger.warning` met stacktrace |
| Geen `session_factory` | Fail-open: doorgaan |

## Tests

3 tests GROEN:
- `tests/unit/governance/test_profiling_consent_per_request.py::test_process_task_gates_on_profiling_opted_out`
- `tests/unit/governance/test_profiling_consent_per_request.py::test_process_task_has_profiling_opt_out_db_check`
- `tests/architecture/test_gdpr_009_profiling_guard.py::test_gdpr_009_process_task_gates_on_profiling_flag`

## ADR-compliance

- ADR-034: function-local import (`# noqa: PLC0415`) van `governance.ai_transparency_service`.
  Contract 7 (`agent_runtime_no_db`) verbiedt alleen `src.core.agents` -> `src.core.database`,
  niet -> `src.core.governance`. Geen contract-schending.
- ADR-015 (ToolBroker allowlist + HITL gate): niet van toepassing op deze check.
- GDPR Art. 21: taak wordt geweigerd als gebruiker actief profiling heeft uitgezet.


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-DLP-003 Dag 2: GDPR-009 per-request profiling consent -- AITransparencyService.check_profiling_opt_out() wired in process_task() na validate_task(). Reset per-request, fail-closed op DB-fout, fail-open zonder user_id. 5 tests GROEN (3 TDD + 2 bestaand). Falende arch test test_gdpr_009 nu GROEN. pyright 0 errors. ruff clean. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-DLP-003 Dag 2: GDPR-009 per-request profiling consent -- AITransparencyService.check_profiling_opt_out() wired in process_task() na validate_task(). Reset per-request, fail-closed op DB-fout, fail-open zonder user_id. 5 tests GROEN (3 TDD + 2 bestaand). Falende arch test test_gdpr_009 nu GROEN. pyright 0 errors. ruff clean..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
