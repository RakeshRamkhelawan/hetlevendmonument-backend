# BE-API-DSM002-dag1 -- ADR-033 API-Layer Violations Fix Dag 1

**Sprint:** SP-DSM-002 Dag 1
**Status:** DONE
**Datum:** 2026-06-16
**Commit:** cc5f6637

---

## Overzicht

Dag 1 van de ADR-033 violation-reductie sprint. Baseline: 152 directe verboden imports in
76 bestanden. Na Dag 1: 127 violations (-25) in 70 bestanden.

ADR-033 verbiedt directe imports van FORBIDDEN_MODULES in `src/core/api/` bestanden
buiten `dependencies.py`. De fix: verboden module-imports verplaatsen naar
`*.dependencies.py` facades (die exempt zijn van de scanner).

---

## Gewijzigde bestanden

### Nieuwe dependencies.py facades (4)

| Bestand | Doel |
|---------|------|
| `src/core/api/v1/als/dependencies.py` | Signal, SignalTier, OrganismRegistry, get_db |
| `src/core/api/v1/als/council_dependencies.py` | build_council, require_council_approval |
| `src/core/api/v1/gatekeeper/dependencies.py` | GatekeeperDecision, GatekeeperRepository, HITLRequestModel |
| `src/core/api/webhooks/dependencies.py` | AuditLog, TenantFilterBypass, TenantSubscriptionCache, get_db |

`council_dependencies.py` is bewust apart gehouden: `als/dependencies.py` ->
`copilot.council.factory` -> `als.*` vormt een circulaire import-keten.

### Uitgebreide dependencies.py facades (3)

| Bestand | Toevoeging |
|---------|-----------|
| `src/core/api/v1/cva/dependencies.py` | +5: CVAService, LLM*, db_manager, get_system_prompt |
| `src/core/api/v1/agentic/dependencies.py` | +check_learning_health |
| `src/core/api/dependencies.py` | +consent_read_limit, +get_twin_stats (explicit re-export) |

`get_twin_stats` gebruikt `as get_twin_stats` re-export zodat de lokale name binding in
`admin_digital_twin.py` intact blijft en 5 bestaande `patch(...)` calls in tests geldig
blijven.

### Router-fixes (7 bestanden, ~25 violations -> 0)

| Bestand | Violations verwijderd |
|---------|----------------------|
| `src/core/api/v1/cva/chat_router.py` | 5 |
| `src/core/api/v1/agentic/learning.py` | 3 (incl. 1 inline + 1 unused import) |
| `src/core/api/v1/als/als_agents_router.py` | 5 (incl. 2 inline) |
| `src/core/api/v1/als/als_tasks_router.py` | 3 |
| `src/core/api/v1/gatekeeper/gatekeeper_decisions_router.py` | 4 (incl. 3 inline) |
| `src/core/api/admin_digital_twin.py` | 3 |
| `src/core/api/webhooks/stripe_handler.py` | 4 (incl. 1 inline) |

### Overig

- `.importlinter`: 17 nieuwe `ignore_imports` entries voor alle nieuwe
  `dependencies.py -> forbidden_module` edges onder Contract 1
- `tests/architecture/test_dsm_api_violations.py`: ceiling 152 -> 127
- `tests/architecture/test_dsm002_groep_c_deferred.py`: 4 xfail assertions voor
  uitgestelde Groep C bestanden (`learning.py`, `main.py`, `lifecycle.py`, `_prana_contracts_cache.py`)

---

## Gedefereerde bestanden (Groep C)

Per `quality-gates.md` vereist elk uitgesteld item een falende architecture test.

| Bestand | Violations | Reden uitgesteld | Architecture test |
|---------|-----------|-----------------|------------------|
| `src/core/api/learning.py` | 10+ | Strangler Fig migratie vereist | `test_api_learning_py_violations_zero` (xfail) |
| `src/core/api/main.py` | -- | ADR-beslissing vereist | `test_api_main_py_violations_zero` (xfail) |
| `src/core/api/setup/lifecycle.py` | -- | Lifespan/startup, ADR-beslissing | `test_api_lifecycle_py_violations_zero` (xfail) |
| `src/core/api/_prana_contracts_cache.py` | -- | Circulair import risico | `test_prana_contracts_cache_violations_zero` (xfail) |

---

## Verificatie

- pyright: 0 errors (baseline 0 gehandhaafd)
- ruff: 0 errors
- architecture tests: 2 passed, 4 xfailed
- targeted unit tests: 16 passed, 0 failures
- violation scanner: 152 -> 127 (-25)
