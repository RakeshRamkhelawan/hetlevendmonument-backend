# Feature Spec: BE-API-036 -- FA-002 HTTPException 5xx Informatielek Fix

**ID:** BE-API-036
**Sprint:** SP-API-009 Dag 5
**Datum:** 2026-06-11
**Status:** IMPLEMENTED

---

## Probleemstelling

35 endpoints in `src/core/api/v1/` retourneerden interne foutdetails aan clients via
`HTTPException(status_code=5xx, detail=str(e))` of `detail=f"...{e}..."`.

Dit is een OWASP A5 Sensitive Data Exposure violation: stack traces, foutberichten en
interne klassenamen zijn zichtbaar voor clients en potentieel aanvallers.

---

## Oplossing

Fix-patroon (backend-patterns.md regel 10):

```python
# VOOR
raise HTTPException(status_code=500, detail=str(e))
raise HTTPException(status_code=500, detail=f"Operation failed: {e}")

# NA
logger.error("operation failed: %s: %s", type(e).__name__, e, exc_info=True)
raise HTTPException(status_code=500, detail="Internal error") from e
```

---

## Scope

35 violations in 10 bestanden, ingedeeld in 4 groepen:

| Groep | Bestanden | Violations | Wijziging |
|-------|-----------|------------|-----------|
| A (agentic, geen logger) | agentic_routing_router.py, agents.py, router_debug.py, supervisors.py | 4 | logger + detail + from e |
| B (autonomous, logger OK) | agents_router.py, code_router.py, emergence_router.py, healing_router.py | 13 | detail + from e |
| C (monitoring_v1, logger OK) | alerts_router.py, metrics_router.py | 15 | detail + from e (f-string) |
| D (routing, geen logger) | router.py | 3 | logger + detail + from e |

**Buiten scope:** 4xx violations (informatief voor client), dict-gebaseerde returns zonder HTTPException.

---

## Architecture Test

`tests/architecture/test_fa002_httpexception_no_str_e.py::test_no_httpexception_5xx_with_info_leak_in_v1`

- Detecteert: `detail=str(e)` en `detail=f"...{e}..."` bij 5xx in `src/core/api/v1/`
- Absoluut pad via `Path(__file__).resolve().parents[2]`
- Line-by-line parenthesis-depth tracker (geen DOTALL-spanning)
- Status na fix: **PASS**

---

## Pre-existing items buiten scope (SP-API-010 backlog)

- `autonomous/agents_router.py:119-123`: dict met `str(e)[:200]` in response body
- `routing/router.py:148-152`: `"message": str(e)` in health-endpoint return dict

---

## Verificatie

```bash
pytest tests/architecture/test_fa002_httpexception_no_str_e.py -v  # 1 passed
pytest tests/architecture/ -q                                        # 75 passed, 3 xfailed
python -m pyright                                                    # 0 errors
ruff check src/core/api/v1/agentic/ src/core/api/v1/autonomous/ src/core/api/v1/monitoring_v1/ src/core/api/v1/routing/
# All checks passed
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
