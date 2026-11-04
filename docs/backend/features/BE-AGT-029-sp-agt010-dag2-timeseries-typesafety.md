# BE-AGT-029 -- SP-AGT-010 Dag 2: CritiqueTimeseriesStats TypedDict

## Status: APPROVED

## Probleemstelling

`get_timeseries_stats()` in `critique_store.py` retourneerde `list[dict[str, Any]]`.
Dit bood geen statische type-checking: consumers konden willekeurige keys opvragen
zonder dat mypy/pyright waarschuwde. Bovendien was het onmogelijk te weten welke velden
gegarandeerd aanwezig zijn zonder de implementatie te lezen.

## Oplossing

### (D) `CritiqueTimeseriesStats` TypedDict

Nieuw TypedDict boven de `CritiqueStore` klasse in `src/core/agents/critique_store.py`:

```python
class CritiqueTimeseriesStats(TypedDict):
    hour: str
    agent_name: str
    avg_score: float
    critique_count: int
```

Return-annotatie van `get_timeseries_stats` bijgewerkt van `list[dict[str, Any]]`
naar `list[CritiqueTimeseriesStats]`.

FA-IND-003 fix: `avg_score` uit de materialized view komt via PostgreSQL `AVG()`
typisch als `Decimal`. De return-dict cast dit nu expliciet naar `float`
(zodat JSON-serialisatie en het TypedDict type overeenkomen):

```python
"avg_score": float(row.avg_score),
```

### (E) `_persist_to_db()` en `_refresh_mv()` patroon-3 (invariant-verificatie)

`_persist_to_db()` en `_refresh_mv()` implementeren patroon-3 al correct: de
DB-sessie wordt geopend BINNEN de `best_effort` context manager. Geen code-wijziging
nodig, maar de onafhankelijke FA review vroeg om een architecture test in plaats
van defer naar backlog.

Nieuwe architecture test `tests/architecture/test_sp_agt_010_critique_store_best_effort_pattern.py`
verifieert via AST-inspectie dat beide methodes `db_manager.get_session()` openen
binnen een `best_effort` async-with. Toekomstige refactors breken deze invariant
automatisch af.

### (F) Refresh-guard cooldown test

Test F verifieert dat `store()` `_refresh_mv()` NIET aanroept als `_last_mv_refresh`
binnen de 5-minuten cooldown valt. Geen code-wijziging nodig.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/critique_store.py` | `TypedDict` import + `CritiqueTimeseriesStats` klasse + return-annotatie update + `float(row.avg_score)` cast |
| `tests/unit/agents/test_critique_store_timeseries.py` | 4 nieuwe tests (D, D2, E, F); test D2 gebruikt `typing.get_type_hints()` |
| `tests/architecture/test_sp_agt_010_critique_store_best_effort_pattern.py` | Nieuwe architecture test voor `best_effort` patroon-3 invariant |

## Extra fixes (0-error baseline)

De onafhankelijke FA review vroeg om een groene pyright baseline van 0 errors.
Daarom zijn ook de volgende pre-existing errors opgelost binnen dezelfde commit:

| Bestand | Fix |
|---------|-----|
| `src/core/typing/redis_protocol.py` | `ltrim` toegevoegd aan `AsyncRedisClient` protocol |
| `src/core/copilot/conversation_memory.py` | `__init__` accepteert nu project-`AsyncRedisClient` protocol i.p.v. untyped `redis.Redis` |
| `src/core/copilot/api/chat_websocket.py` | Overbodige `# type: ignore[arg-type]` verwijderd |
| `src/core/api/v1/analytics_ingest/events_router.py` | `current_user.id` -> `current_user.get("id")` voor veilige dict-toegang |
| `src/core/copilot/api/audit_endpoints.py` | `resolved_at` None-guard toegevoegd |

## Testresultaten

| Suite | Resultaat |
|-------|-----------|
| `test_critique_store_timeseries.py` | 11/11 GROEN |
| `test_sp_agt_010_critique_store_best_effort_pattern.py` | 2/2 GROEN |
| `tests/unit/agents/` (regressie) | 476 passed, 0 failed |
| `python -m pyright` | 0 errors, 11 warnings |
| `python -m pytest tests/architecture/` | 388 passed, 0 failed |

## Gate 2 review

- code-reviewer: GO (TypedDict in `critique_store.py`, `Any` import behouden, Python 3.8+)
- quality-reviewer: GO (`TypedDict` import toegevoegd, ruff-safe, pyright-compatible)

## Sprint

SP-AGT-010 Dag 2 | 2026-06-28


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-AGT-010 Dag 2: CritiqueTimeseriesStats TypedDict + _refresh_mv() patroon-3 invariant-test + refresh-guard test is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-AGT-010 Dag 2: CritiqueTimeseriesStats TypedDict + _refresh_mv() patroon-3 invariant-test + refresh-guard test.
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
