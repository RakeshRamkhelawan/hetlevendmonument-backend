# Review BE-AGT-020 -- CritiqueStore Materialized View Telemetry

## Metadata

- **Sprint**: SP-AGT-006, Dag 3
- **Reviewer**: Claude (quality-reviewer agent)
- **Datum**: 2026-06-27
- **Verdict**: APPROVED WITH MINOR GAPS

---

## CRITICAL / HIGH bevindingen

Geen.

---

## MINOR bevindingen

| ID | Beschrijving | Categorie |
|----|-------------|-----------|
| BE-AGT-020-minor-1 | `get_timeseries_stats` retourneert `list[dict[str, Any]]` i.p.v. TypedDict -- pyright-safe maar minder expressief | Type-safety |
| BE-AGT-020-minor-2 | Refresh-guard unit test ontbreekt (5-min cooldown-gedrag niet getest) | Test-coverage |
| BE-AGT-020-minor-3 | `_refresh_mv()` opent sessie BUITEN `best_effort` context -- bij crash na execute maar voor commit wordt `best_effort` niet aangesproken voor rollback | Patroon-consistency |

---

## Bevestigingen (PASS)

| Check | Resultaat |
|-------|-----------|
| ADR-033: geen directe agents-import in router | PASS -- `CritiqueStore` via `dependencies.py` facade |
| ADR-003: tenant_id via JWT | PASS -- `critic.tenant_id`, nooit uit request body |
| SQL injection | PASS -- geparameteriseerde query (`:tenant_id`, `:cutoff`) |
| Input validatie `hours` | PASS -- `Query(ge=1, le=168)` via FastAPI |
| Route-volgorde | PASS -- `/telemetry` geregistreerd VOOR `/{agent_name}/...` |
| Alembic heads = 1 | PASS -- `20260627_critique_hourly_stats_mv` is de enige head |
| `downgrade()` werkend | PASS -- index + view in omgekeerde volgorde gedropped |
| `datetime.now(timezone.utc)` | PASS -- correct gebruik in refresh guard en `get_timeseries_stats` |
| ASCII-only in code/comments | PASS |
| Race condition refresh guard | PASS -- `_last_mv_refresh` atomisch binnen `asyncio.Lock` (FA-002 fix) |
| 6/6 tests groen | PASS |
| Pyright 0 errors | PASS |

---

## Toelichting minors

**BE-AGT-020-minor-3**: In `_refresh_mv()`:
```python
async with best_effort("critique_hourly_stats mv refresh"):
    async with db_manager.get_session() as db:
        await db.execute(...)
        await db.commit()
```
De sessie is context-managed (`__aexit__` rolt terug bij exception), dus data-integriteit
is gewaarborgd. `best_effort` vangt de exception op en logt -- geen 500. Het patroon wijkt
licht af van backend-patterns.md patroon 3 (dat `db_session=db` verwacht), maar is correct
voor het use-case waarbij de sessie intern wordt aangemaakt. Acceptabel als minor.

---

## Eindoordeel

**APPROVED WITH MINOR GAPS** -- 3 minors, geen CRITICAL of HIGH.
Alle minors zijn gedocumenteerd als backlog-items in de feature spec.
Dag 3 kan worden geclosed.
