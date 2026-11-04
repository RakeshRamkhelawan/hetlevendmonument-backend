# BE-CFG-007 -- Dramatiq Async Actor sync Wrapper Conversie (NEW-WIRE-002)

**ID:** BE-CFG-007
**Sprint:** SP-WE-19
**Datum:** 2026-06-01
**Bron:** NEW-WIRE-002 (ISSUE-REGISTRY-L3-L4 2026-06-01)
**ADR:** ADR-006 (Dramatiq + Redis)

## Samenvatting

Drie async def Dramatiq actors zijn omgezet naar sync wrappers met asyncio.run():
`process_cva_message`, `check_hash_chain_integrity_actor` en `cleanup_council_decisions`.
Async actors zonder AsyncIO() middleware worden door Dramatiq aangeroepen maar niet awaited --
de actor body wordt nooit uitgevoerd (stille data loss). Sync wrapper met asyncio.run() is
thread-safe en vereist geen middleware.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/tasks/cva_tasks.py` | async def process_cva_message -> def + asyncio.run(_async) |
| `src/core/copilot/audit/integrity_check_actor.py` | async def check_hash_chain_integrity_actor -> def + asyncio.run |
| `src/core/governance/retention_cleanup.py` | async def cleanup_council_decisions -> def + asyncio.run |

## Trainingssamenvatting

### Flow 1: Actor body executie via sync wrapper

- Actor: Dramatiq worker thread (thread pool)
- Voorwaarde: broker ontvangt bericht op cva_queue, maintenance of cleanup queue
- Actie: worker thread roept de sync actor functie aan
- Systeemverwerking: sync wrapper roept asyncio.run(_async_impl(...)) aan; asyncio.run() maakt fresh event loop per aanroep (thread-safe); geen asyncio.new_event_loop()+set_event_loop() (CLAUDE.md valkuil)
- Succesrespons: actor body uitgevoerd, taak gemarkeerd als SUCCESS
- Foutrespons: Exception in async impl -> asyncio.run() propagateert exception -> Dramatiq markeert taak als FAILED -> retry na backoff
- Uitzonderingen: asyncio.run() is niet reentrant -- aanroepen vanuit een draaiende event loop (bijv. tests met pytest-asyncio) gooit RuntimeError. Fix in tests: patch asyncio.run of gebruik nest_asyncio.
