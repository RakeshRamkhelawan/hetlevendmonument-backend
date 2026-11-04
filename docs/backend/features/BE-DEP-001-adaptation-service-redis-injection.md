# BE-DEP-001 — AdaptationService Redis Injection

**ID:** BE-DEP-001
**Sprint:** SP-E06
**Datum:** 2026-05-29
**Bestand:** `src/core/api/v1/agentic/dependencies.py`
**Status:** APPROVED

---

## Samenvatting

De `get_adaptation_service` FastAPI-dependency injecteerde voorheen geen Redis-client (hardcoded `redis_client=None`), waardoor de `RuleCache`-laag in `CachedAdaptationRuleService` altijd uitgeschakeld bleef. Fix: inject een echte Redis-client via de canonieke `get_redis_client()` factory, met graceful fallback naar `None` bij Redis-onbeschikbaarheid (zodat de endpoint werkzaam blijft, caching uitgeschakeld).

---

## Gewijzigd bestand

| Pad | Wijziging |
|-----|-----------|
| `src/core/api/v1/agentic/dependencies.py` | `get_redis_client()` geimporteerd; try/except fallback toegevoegd |

---

## Architectuurbeslissingen

1. **Canonical Redis factory:** `from src.core.database.redis import get_redis_client` — zelfde pattern als 8+ andere bestanden (auth/router.py, copilot/dependencies.py, etc.). Geen nieuwe verbindingspool.
2. **Graceful fallback:** `try/except` rond `get_redis_client()` — Redis-onbeschikbaarheid geeft een warning en zet `redis=None`. De `RuleCache` detecteert dit via `self._enabled = redis_client is not None` en valt terug op DB-only queries.
3. **Geen hardcoded URL:** Redis URL komt intern uit `get_redis_url()` in de factory (CLAUDE.md §8).

---

## Trainingssamenvatting

### Flow: Adaptation Rule Service aanvragen met Redis caching

| Veld | Inhoud |
|------|--------|
| **Actor** | FastAPI dependency injection framework (bij elk verzoek aan een `/agentic/*` endpoint) |
| **Voorwaarde** | Redis-instantie bereikbaar op `REDIS_URL` |
| **Actie** | `get_adaptation_service(db)` wordt aangeroepen als FastAPI `Depends()` |
| **Systeemverwerking** | `get_redis_client()` haalt client op uit connection pool; `create_cached_adaptation_service(db, redis_client=redis)` bouwt een `CachedAdaptationRuleService` met actieve `RuleCache` |
| **Succesrespons** | `AdaptationRuleService` (runtime: `CachedAdaptationRuleService`) beschikbaar; adaptation rules worden gecached voor 5 minuten (TTL=300s) |
| **Foutrespons** | Redis onbereikbaar → `logger.warning`; `redis=None` doorgegeven; caching uitgeschakeld, DB-fallback actief; endpoint blijft functioneel |
| **Uitzonderingen** | DB onbereikbaar → `get_db()` raises, endpoint geeft 500. Redis én DB onbereikbaar → dubbele fout, endpoint geeft 500 |

---

## Tests

- `tests/unit/test_sp_e06_small_fixes.py::TestAdaptationServiceRedis` (4 tests)
  - `test_redis_client_none_removed` — source check
  - `test_redis_url_not_hardcoded` — CLAUDE.md §8 compliance
  - `test_get_redis_client_imported` — import aanwezig
  - `test_adaptation_service_receives_non_none_redis_behavioral` — mock verificatie
