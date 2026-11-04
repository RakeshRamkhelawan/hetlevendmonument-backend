# BE-DSM-007: SP-DSM-002 Dag 3 -- bootstrap-exempt + activepieces rate_limiter batch

**Sprint:** SP-DSM-002 Dag 3
**Datum:** 2026-06-16
**ADR:** ADR-033 (3-laags router + dependencies.py facade)
**Violations:** 117 -> 100 (-17)

---

## Wat is er veranderd?

### Taak 1: Groep C bootstrap-exempt (-13 violations)

`scripts/dsm_api_violation_finder.py` uitgebreid met `_BOOTSTRAP_EXEMPT`:

```python
_BOOTSTRAP_EXEMPT: frozenset[str] = frozenset({"main.py", "lifecycle.py", "_prana_contracts_cache.py"})
```

**Rationale per bestand:**
- `api/main.py` (5 violations): applicatie entry point, geen v1/-domein router
- `api/setup/lifecycle.py` (5 violations): lifespan/startup code, geen v1/-domein router
- `api/v1/_prana_contracts_cache.py` (3 violations): ALS infra-cache met circular import risico; tijdelijk exempt, pending ADR-beslissing

Drie `@pytest.mark.xfail` markers in `test_dsm002_groep_c_deferred.py` geconverteerd naar passing tests.

### Taak 2: activepieces governance.rate_limiter batch (-4 violations)

Vier `activepieces/` routers importeerden `integration_read_limit` / `integration_write_limit` rechtstreeks uit `src.core.governance.rate_limiter`. Fix via het ADR-033 facade-patroon:

1. `src/core/api/v1/activepieces/dependencies.py` uitgebreid:
   ```python
   from src.core.governance.rate_limiter import (
       integration_read_limit,
       integration_write_limit,
   )
   ```

2. Vier router-bestanden omgezet naar eigen-domein import:
   - `catalog_router.py`
   - `connections_router.py`
   - `execution_router.py`
   - `flows_router.py`

3. `.importlinter` entry toegevoegd (documentatie-stijl):
   ```
   src.core.api.v1.activepieces.dependencies -> src.core.governance.rate_limiter
   ```

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `scripts/dsm_api_violation_finder.py` | `_BOOTSTRAP_EXEMPT` frozenset + stale `rel` variabele verwijderd |
| `tests/architecture/test_dsm002_groep_c_deferred.py` | 3 xfail markers verwijderd + docstring bijgewerkt |
| `tests/architecture/test_dsm_api_violations.py` | Ceiling 117 -> 100 |
| `src/core/api/v1/activepieces/dependencies.py` | rate_limiter symbolen toegevoegd aan facade |
| `src/core/api/v1/activepieces/catalog_router.py` | Import via dependencies.py |
| `src/core/api/v1/activepieces/connections_router.py` | Import via dependencies.py |
| `src/core/api/v1/activepieces/execution_router.py` | Import via dependencies.py |
| `src/core/api/v1/activepieces/flows_router.py` | Import via dependencies.py |
| `.importlinter` | activepieces -> governance.rate_limiter edge |

---

## Correctie t.o.v. de pre-gegenereerde brief

De brief vermeldde `focus_builder/` als domein voor de rate_limiter batch. Geverifieerd via grep:
- `focus_builder/` importeert alleen `src.core.middleware.rate_limiter` (ALLOWED -- niet in FORBIDDEN_MODULES)
- De 4 violations zaten in `activepieces/` (src.core.governance.rate_limiter)

---

## Testresultaten

| Check | Resultaat |
|-------|-----------|
| `python scripts/dsm_api_violation_finder.py` | Total violations: 100 |
| `python -m pyright` | 0 errors, 55 warnings |
| `ruff check src/` | All checks passed |
| `pytest tests/architecture/` | 153 passed, 16 xfailed |
| `pytest tests/unit/activepieces/` | 57 passed |
| `pytest tests/architecture/test_dsm002_groep_c_deferred.py` | 4 passed |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-002 Dag 3: bootstrap-exempt (main.py, lifecycle.py, \_prana_contracts_cache.py) + activepieces rate_limiter batch (117->100 violations) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-002 Dag 3: bootstrap-exempt (main.py, lifecycle.py, \_prana_contracts_cache.py) + activepieces rate_limiter batch (117->100 violations).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
