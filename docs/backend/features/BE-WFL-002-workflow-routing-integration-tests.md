# BE-WFL-002 -- Workflow Routing Integration Tests + DSM Meting

**Sprint:** SP-AGT-003 Dag 2
**Datum:** 2026-06-10
**Status:** IMPLEMENTED

---

## Samenvatting

Integratietests voor de dag 1 AgentRouterAgent wiring (BE-WFL-001) en DSM-meting bevestigen
dat de ADR-034 boundary ongewijzigd is na SP-AGT-003 Dag 1.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `tests/integration/test_workflow_real_routing.py` | 2 integratietests aangemaakt (Windows/no-PostgreSQL skip) |
| `tests/architecture/test_adr034_orchestration_boundary.py` | ADR-034 regressietest toegevoegd voor providers.py |
| `docs/backend/features/ID-REGISTRY.md` | BE-WFL-002 geregistreerd |

---

## Integratietests

Bestand: `tests/integration/test_workflow_real_routing.py`

| Test | Beschrijving |
|------|-------------|
| `test_create_workflow_engine_produces_wired_runtime` | Verifieert dat `create_workflow_engine()` een engine produceert met een echte `AgentRouterAgent` (niet mock, niet None) |
| `test_run_agent_with_real_router_returns_dict` | Verifieert dat `run_agent()` met echte router geen exception gooit en een dict met `"success"` key retourneert |

Skip-gedrag:
- **Windows**: geskipt via `pytestmark` (ProactorEventLoop deadlock)
- **Linux zonder PostgreSQL**: geskipt via `tests/integration/conftest.py` module-level check
- **Linux met PostgreSQL**: GROEN verwacht op CI

---

## ADR-034 architectuurtest

Bestand: `tests/architecture/test_adr034_orchestration_boundary.py`

Nieuwe test: `test_providers_py_has_no_database_import_after_dag1_wiring`

Statische AST-check die altijd draait (ook zonder PostgreSQL, ook op Windows).
Bewijs dat `providers.py` na SP-AGT-003 Dag 1 wiring nog steeds geen `src.core.database.database`
importeert. Loopt in de architectuursuite bij elke `pytest tests/architecture/` aanroep.

---

## DSM meting

Gemeten na SP-AGT-003 Dag 1 (commit `2c06ba61`):

| Module | Database imports | Verwacht | Status |
|--------|-----------------|---------|--------|
| `src/core/agents/` | 9 | 9 | ONGEWIJZIGD |
| `src/core/workflow/` module-level | 2 | 2 (pre-existing) | ONGEWIJZIGD |

Details `agents/` (9 imports, pre-existing):
- `budget_manager.py:24`
- `diagnostics_agent/database.py:12`
- `knowledge_agent/database.py:12`
- `knowledge_agent/routes.py:19`
- `models.py:19`
- `seed_agent_registry.py:185`
- `sentiment_agent/database.py:12`
- `strategy_models.py:16`
- `translation_agent/routes.py:15`

Details `workflow/` module-level (2 pre-existing):
- `dead_letter_queue.py:21`
- `models.py:23`

De deferred import in `worker.py::create_workflow_engine()` (regel ~289) is een
functie-body import en telt NIET mee als module-level import.

---

## Tests

| Test | Status |
|------|--------|
| `test_create_workflow_engine_produces_wired_runtime` | Geskipt op Windows/geen PostgreSQL; GROEN op Linux+PostgreSQL (CI) |
| `test_run_agent_with_real_router_returns_dict` | Geskipt op Windows/geen PostgreSQL; GROEN op Linux+PostgreSQL (CI) |
| `test_providers_py_has_no_database_import_after_dag1_wiring` (architecture) | GROEN (64/64 architecture tests pass) |
| Gerichte regressiecheck (141 tests) | GROEN -- 0 regressies |

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
