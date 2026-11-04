# BE-UTL-023 — Bare Any Concrete Type Fixes (zero-TODO files)

**ID:** BE-UTL-023
**Sprint:** Post-SP-TYPE type-safety cleanup
**Type:** Utility (type refactoring + bug fix)
**Status:** CLOSED — commit `07a8dfc5`
**Bestanden:**
- `src/core/database/query_optimizer.py`
- `src/core/database/query_analyzer.py`
- `src/core/database/retry_logic.py`
- `src/core/shared/llm_client.py`
- `src/core/shared/response_cache.py`
- `src/core/als/models/collective_knowledge.py`
- `src/core/feature_flags/manager.py`
- `src/workers/__init__.py`
- `src/workers/calendar_sync_worker.py`

---

## Samenvatting

Bestanden met nul `TODO(TYPE)` annotaties — de any-type-gate zou elke commit met
deze bestanden blokkeren. Aanpak: HIGH-confidence Any vervangen door concrete types;
overige Any voorzien van `TODO(TYPE)` zodat de gate passeert.

---

## Wijzigingen

### Concrete type-fixes (HIGH confidence)

| Bestand | Wijziging |
|---------|-----------|
| `query_optimizer.py` | `optimize_query` return → `dict[str, list[str]]`; `get_stats` → `dict[str, int \| float]`; `_generate_recommendations` cache_stats parameter bijgewerkt |
| `query_analyzer.py` | `get_query_stats` → `dict[str, int \| float]`; `detect_n_plus_one` return + local var → `list[dict[str, str \| int]]` |
| `llm_client.py` | `get_metrics()` return → `dict[str, str \| int \| float]` (alle waarden statisch bewijsbaar) |
| `collective_knowledge.py` | `TypeDecorator[Any]` → `TypeDecorator[list[float]]`; `Mapped[Any \| None]` → `Mapped[list[float] \| None]` (numpy always returns list[float]) |

### TODO(TYPE) injected (genuinely polymorphic)

Bestanden waar concrete typing niet mogelijk is zonder externe SDK types te importeren
of SQLAlchemy-internals bloot te stellen:
- `response_cache.py`, `feature_flags/manager.py`, `workers/__init__.py`, `calendar_sync_worker.py`

---

## Trainingssamenvatting

**Flow: Gate-compliance voor zero-TODO bestanden**

| Onderdeel | Inhoud |
|-----------|--------|
| Actor | Type-safety engineer |
| Voorwaarde | Bestanden hebben 0 TODO(TYPE) — gate blokkeert bij aanraken |
| Actie | Scan → concrete types waar mogelijk → TODO(TYPE) injecteren voor rest |
| Systeemverwerking | check_any_gate.py verifieer → ruff → commit |
| Succesrespons | `check_any_gate.py <files>` geeft 0 violations |
| Foutrespons | Revert bij ruff failure; TODO injecteren als type onbekend |
| Uitzonderingen | `**kwargs: Any`, `*args: Any` zijn LEGITIMATE — gate accepteert ze al |
