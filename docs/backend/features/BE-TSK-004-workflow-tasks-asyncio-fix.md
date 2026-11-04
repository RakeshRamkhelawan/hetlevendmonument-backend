# BE-TSK-004 — Workflow Tasks asyncio Fix (B-013)

**ID:** BE-TSK-004
**Sprint:** SP-W02
**Datum:** 2026-05-30
**Status:** APPROVED

---

## Samenvatting

Verwijdert het thread-unsafe `asyncio.new_event_loop()` patroon uit
`src/core/tasks/workflow_tasks.py` en vervangt het door het thread-veilige `asyncio.run()`.

---

## Bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/tasks/workflow_tasks.py` | `new_event_loop() / set_event_loop()` vervangen door `asyncio.run()` |

---

## Root Cause (B-013)

`workflow_tasks.py:26-27` maakte handmatig een nieuwe event loop per Dramatiq-bericht:

```python
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
result = loop.run_until_complete(agent.process_task(task))
```

`asyncio.set_event_loop()` is niet thread-safe. Dramatiq draait actors in een thread pool.
Bij gelijktijdige berichten konden workers elkaars event loop overschrijven, leidend tot
race conditions en ongedefinieerd gedrag.

---

## Implementatie

```python
@dramatiq.actor
def execute_workflow_step(task_data_dict: dict[str, Any]) -> dict[str, Any]:
    logger.info("Executing workflow step via Dramatiq: %s", task_data_dict.get("task_id"))
    agent = AutonomousAgent()
    try:
        task = TaskData(**task_data_dict)
        # asyncio.run() is thread-safe: creates a fresh event loop per call and tears it down.
        result = asyncio.run(agent.process_task(task))
        return result.model_dump()
    except Exception as e:
        logger.error("Error executing workflow step: %s", e, exc_info=True)
        raise
```

`asyncio.run()` maakt en verwijdert een event loop volledig per aanroep, thread-safe
per definitie in Python 3.10+.

`AutonomousAgent.__init__` is veilig synchroon aan te roepen (zet alleen `self.redis = None`).
De `initialize()` coroutine wordt door `asyncio.run()` correct afgehandeld via
`agent.process_task()`.

---

## Aanvullende kwaliteitsfixes

- `logger.info(f"...")` vervangen door `logger.info("...", ...)` (`%s` stijl, CLAUDE.md §10)
- `logger.error(f"...")` vervangen met `exc_info=True` toegevoegd

---

## Trainingssamenvatting

**Flow: Workflow step via Dramatiq uitvoeren**

| Veld | Waarde |
|------|--------|
| **Actor** | Dramatiq worker thread (sync actor) |
| **Voorwaarde** | `execute_workflow_step.send(task_data_dict)` aangeroepen door workflow engine |
| **Actie** | Worker roept `asyncio.run(agent.process_task(task))` aan |
| **Systeemreactie** | Verse event loop aangemaakt per taak; `AutonomousAgent.process_task()` uitgevoerd; loop opgeruimd |
| **Succesrespons** | `result.model_dump()` returned naar Dramatiq |
| **Foutrespons** | Exception gelogd met `exc_info=True` (volledige stacktrace), re-raised voor Dramatiq retry |
| **Uitzonderingen** | Bij simultane berichten: elke thread heeft eigen event loop (geen conflict) |

---

## DoD

- [x] `new_event_loop` niet meer aanwezig in `workflow_tasks.py`
- [x] `set_event_loop` niet meer aanwezig in `workflow_tasks.py`
- [x] `asyncio.run(` aanwezig in `workflow_tasks.py`
- [x] 6 unit tests groen (`test_sp_w02_cva_workflow_tasks.py`)
- [x] 488 regressietests groen
