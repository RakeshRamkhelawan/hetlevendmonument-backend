# BE-TSK-009 -- Dramatiq Actor Import Registration (NEW-WIRE-001)

**ID:** BE-TSK-009
**Sprint:** SP-WE-19
**Datum:** 2026-06-01
**Bron:** NEW-WIRE-001 (ISSUE-REGISTRY-L3-L4 2026-06-01)
**ADR:** ADR-006 (Dramatiq + Redis)

## Samenvatting

Drie critical Dramatiq actors waren niet traceerbaar via de worker-entrypoints:
`check_hash_chain_integrity_actor`, `process_cva_message` en `cleanup_council_decisions`.
Fix: side-effect imports toegevoegd aan `src/workers/actors.py` met `# noqa: F401`.
Calendar actors (sync_calendar_integration, refresh_expiring_webhooks) uitgesloten vanwege
transitieve DATABASE_URL afhankelijkheid via src/workers/__init__.py.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/workers/actors.py` | 3 side-effect imports toegevoegd met # noqa: F401 |
| `src/core/tasks/cva_tasks.py` | async def -> sync wrapper (ook NEW-WIRE-002) |
| `src/core/copilot/audit/integrity_check_actor.py` | async def -> sync wrapper |
| `src/core/governance/retention_cleanup.py` | async def -> sync wrapper |

## Trainingssamenvatting

### Flow 1: Actor registratie bij worker startup

- Actor: workflow-worker container (Dramatiq)
- Voorwaarde: worker opgestart, broker actief, actors.py geimporteerd
- Actie: worker start, Python importeert src.workers.actors als side-effect
- Systeemverwerking: @dramatiq.actor decorator registreert elke actor bij de broker bij module-import
- Succesrespons: dramatiq.get_broker().get_declared_actors() bevat check_hash_chain_integrity_actor, process_cva_message, cleanup_council_decisions
- Foutrespons: ImportError bij missing dependency -- worker start niet, log toont ModuleNotFoundError
- Uitzonderingen: Als een actor-module ImportError gooit, worden ALLE actors in actors.py na die import ook niet geregistreerd. Fix de ImportError eerst.
