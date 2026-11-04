# BE-UTL-040: BM25Service Factory Pattern

## Samenvatting

Vervangt module-level `bm25_service = BM25Service()` door `get_bm25_service()` factory + `_LazyBM25Proxy` backward-compat alias. Geen I/O (mkdir) meer bij import.

## Scope

- `src/core/search/bm25_service.py`
- `src/core/search/hybrid_search.py` (import blijft werken via proxy)

## Wijzigingen

```python
# Before (at module level):
bm25_service = BM25Service()  # triggers mkdir at import

# After:
_bm25_service_instance: BM25Service | None = None

def get_bm25_service() -> BM25Service:
    global _bm25_service_instance
    if _bm25_service_instance is None:
        _bm25_service_instance = BM25Service()
    return _bm25_service_instance

class _LazyBM25Proxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_bm25_service(), name)

bm25_service = _LazyBM25Proxy()  # no I/O at import
```

## Tests

- `tests/unit/search/test_bm25_service_factory.py` — 3 tests (singleton, no I/O at import, lazy init)

## ADR Impact

- ADR-009 (Traefik/health): snellere startup, geen mkdir bij import

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)

> Module-level singletons die I/O doen zijn een klassieke startup bottleneck. Vervang door een factory + lazy proxy. Bestaande `from module import singleton` imports blijven werken zonder refactoring.
