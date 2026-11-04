# BE-AGT-015: CritiqueStore -> PostgreSQL Persistentie (SP-AGT-005 Dag 1)

## Status: APPROVED

## Samenvatting

Voegt PostgreSQL als secondary write toe aan `CritiqueStore`. In-memory store blijft primary
(geen breaking changes). DB-write is best-effort: fouten worden gelogd en nooit naar de caller
gepropageerd. Retention lifecycle via nieuw Dramatiq actor `cleanup_agent_critiques`.

## Context

`CritiqueStore` (singleton, asyncio.Lock, FIFO op 10.000 per tenant) verloor alle data bij herstart.
SP-AGT-005 Dag 1 borgt persistentie zonder interface-wijzigingen.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/models/critique_models.py` | NIEUW -- `CritiqueRecord` ORM model (agent_critiques tabel) |
| `src/alembic/versions/e4f5c648cf94_add_agent_critiques_table.py` | NIEUW -- Alembic migratie + RLS |
| `src/core/agents/critique_store.py` | GEWIJZIGD -- `_persist_to_db()` + store() wrapping |
| `src/core/governance/retention_cleanup.py` | GEWIJZIGD -- `cleanup_agent_critiques` actor + RETENTION_ALLOWED |
| `src/core/database/import_all_models.py` | GEWIJZIGD -- `critique_models` import toegevoegd |
| `.importlinter` | GEWIJZIGD -- Cat B ignore_import voor critique_store -> database |
| `tests/unit/agents/test_critique_store_db_persist.py` | NIEUW -- 4 unit tests |

## Design beslissingen

### Secondary write met lazy import
`_persist_to_db()` gebruikt function-local imports om circulaire dep bij module-load te vermijden.
Import-linter `.importlinter` bevat Cat B goedkeuring voor `src.core.agents.critique_store -> src.core.database.database`.

### Lock-buiten patroon
In-memory operaties staan BINNEN `async with self._lock:`. DB-write staat BUITEN de lock.
Voorkomt lock contention als PostgreSQL traag is.

### Dubbele exception wrapping
`_persist_to_db()` heeft interne try/except. `store()` heeft extra wrapping voor als test doubles
of externe code de methode overschrijven. In-memory store faalt nooit door DB.

### Retention actor
`cleanup_agent_critiques` Dramatiq actor met `asyncio.run()` sync wrapper.
`TenantFilterBypass()` voor cross-tenant cleanup. Batch delete van 1000 per iteratie.
Retentieperiode: 180 dagen.

## Alembic verificatie

```
alembic -c src/alembic.ini heads  -> e4f5c648cf94 (1 head, GROEN)
```

## Test verificatie

```
tests/unit/agents/test_critique_store_db_persist.py -- 4/4 PASSED
tests/unit/agents/ -- 924 passed, 0 failed
tests/unit/governance/ -- onderdeel van bovenstaande run
```

## pyright / ruff

```
python -m pyright  -> 0 errors, 55 warnings (pre-existing)
ruff check <gewijzigde bestanden>  -> All checks passed
```


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-AGT-005 Dag 1: CritiqueStore -> PostgreSQL secondary write -- CritiqueRecord ORM + Alembic migratie + persist_to_db() best-effort + cleanup_agent_critiques actor is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-AGT-005 Dag 1: CritiqueStore -> PostgreSQL secondary write -- CritiqueRecord ORM + Alembic migratie + persist_to_db() best-effort + cleanup_agent_critiques actor.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
