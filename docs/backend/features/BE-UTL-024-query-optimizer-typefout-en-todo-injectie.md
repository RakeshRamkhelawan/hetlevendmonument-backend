# BE-UTL-024 — query_optimizer Typefout Fix + Resterende TODO Injectie

**ID:** BE-UTL-024
**Sprint:** Post-SP-TYPE type-safety cleanup
**Type:** Utility (bug fix + annotation)
**Status:** CLOSED — commit `983da239`
**Bestanden:**
- `src/core/database/query_optimizer.py` (typefout fix)
- `src/core/database/database.py`
- `src/core/database/query_analyzer.py`
- `src/core/database/retry_logic.py`
- `src/core/database/unit_of_work.py`
- `src/core/shared/production_logging.py`
- `src/core/shared/response_cache.py`
- `src/workers/workflow_worker.py`

---

## Samenvatting

Correctie van een typefout die door BE-UTL-023 werd geintroduceerd, plus aanvullende
`TODO(TYPE)` injectie op bestanden die de baseline injection hadden gemist.

---

## Wijzigingen

### Typefout correctie

`query_optimizer.py` L173/175: `_suggest_indexes` return type was verkeerd vernauwd naar
`list[dict[str, str]]`. De dicts bevatten `"columns": list[str]` — een list, geen string.

```python
# FOUT (geintroduceerd door BE-UTL-023)
def _suggest_indexes(self, sql: str) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []

# CORRECT
def _suggest_indexes(self, sql: str) -> list[dict[str, str | list[str]]]:
    suggestions: list[dict[str, str | list[str]]] = []
```

Pyright error `reportArgumentType` op L186/196 opgelost.

### TODO(TYPE) injectie

Aanvullende baseline-injectie op database/ en workers/ bestanden die 0 TODOs hadden
op genuinely polymorphe Any-usages (SQLAlchemy event handlers, dramatiq actor
pre-declarations, etc.).

---

## Trainingssamenvatting

**Flow: Typefout fix na type-narrowing**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety engineer |
| Voorwaarde | Pyright `reportArgumentType` na te strikte narrowing |
| Actie | Return type verbreden: `dict[str, str]` → `dict[str, str \| list[str]]` |
| Systeemverwerking | ruff check → pyright diagnostics verdwijnen |
| Succesrespons | 0 pyright errors op L186/196 |
| Foutrespons | N.v.t. |
| Uitzonderingen | Type-narrowing moet ALTIJD alle return-paths checken, ook heterogene dict-values |
