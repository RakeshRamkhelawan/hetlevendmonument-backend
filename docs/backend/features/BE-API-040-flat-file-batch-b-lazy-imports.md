# BE-API-040: ADR-033 Batch B -- Flat File Lazy Import Fixes

**Sprint:** SP-API-010 Dag 3
**Status:** APPROVED
**Datum:** 2026-06-11

---

## Samenvatting

Alle 7 overgebleven `src/core/api/*_endpoints.py` flat files die module-level forbidden imports hadden
zijn gefixed via lazy imports (ADR-033 Contract 1). Architectuur test GROEN, pyright 0 errors.

---

## Scope

| Bestand | Violations (voor) | Fix |
|---------|-------------------|-----|
| `billing_endpoints.py` | 1 (`database.database`) | `from src.core.api.dependencies import get_db` |
| `crag_endpoints.py` | 1 (`agents.corrective_rag_agent`) | Lazy import inside function body |
| `swarm_websocket_endpoints.py` | 1 (`governance.oversight_gate`) | Lazy import inside `start_swarm` |
| `knowledge_endpoints.py` | 1 (`agents.agent_registry`) | Parameter verwijderd; afhankelijkheid was ongebruikt |
| `workflow_builder_endpoints.py` | 1 (`llm.llm_service`) | Lazy import inside `suggest_nodes` |
| `nlp_endpoints.py` | 1 (`agents.enhanced_nlp_parser`) | Lazy singleton `_get_nlp_parser()` + TYPE_CHECKING guard |
| `workflow_suggestions_endpoints.py` | 1 (`workflow.models`) | TYPE_CHECKING guard + lazy import inside helper |

**Totaal:** 7 violations verwijderd, 0 module-level forbidden imports resterend in Batch B.

---

## Bijkomende fixes (pre-existing, meegenomen)

- `swarm_websocket_endpoints.py`: test patch-path gecorrigeerd naar source module (`src.core.governance.oversight_gate.OversightGate`)
- `knowledge_endpoints.py`: 8x `str(e)` in HTTPException details -> `"Internal error"` (OWASP A5)
- `workflow_builder_endpoints.py`: 8x emoji in NATIVE_TOOLS -> ASCII literals; `str(e)` -> `"Internal error"`; logger format gecorrigeerd
- `nlp_endpoints.py`: 7x `str(e)` -> `"Internal error"`; `logger.exception` -> `logger.error(..., exc_info=True)`
- Pre-existing uncommitted pyright errors in `predictor.py`, `service.py`, `system_monitor_agent.py`: gefixed met gerichte `type: ignore` comments

---

## Architecture Test

`tests/architecture/test_flat_file_batch_b_clean.py` -- 1 PASSED

---

## Tests

- `tests/architecture/test_flat_file_batch_b_clean.py`: 1 PASSED
- `tests/unit/test_swarm_websocket_endpoints.py`: PASSED
- `tests/unit/test_swarm_ws_tenant_hardening.py`: PASSED
- `tests/architecture/ + tests/unit/api/`: 189 passed, 12 xfailed

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
