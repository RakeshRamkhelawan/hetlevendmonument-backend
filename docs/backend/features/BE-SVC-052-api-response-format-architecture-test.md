# BE-SVC-052 — BP-001 API Response Format Architecture Test

**Sprint:** SP-SEC-002 Dag 1
**Datum:** 2026-07-01
**Status:** APPROVED

## Samenvatting

Architecture test die CI-blokkeert zolang router-bestanden `return`-statements bevatten die niet de `{"success": True, "data": ...}` wrapper gebruiken. Test is opzettelijk ROOD totdat alle 248 non-conformante endpoints gefixed zijn.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `tests/architecture/test_api_response_format_conformance.py` | Nieuw — CI-blokkerende architecture test |

## Test-gedrag

- **ROOD op commit:** Scant 4 kritieke router-bestanden op niet-success-wrapped returns.
- **GROEN na fix:** Zodra alle returns in scope de `{"success": True, ...}` wrapper gebruiken.
- **Scope:** `agent_crud_router.py`, `external_agent_router.py`, `notifications_router.py`, `workflow_router.py`

## ADR-compliance

Geen nieuwe ADR-violations. Test enforceert bestaand ADR-033 + backend-patterns pattern 7.

## Testbewijs

```
tests/architecture/test_api_response_format_conformance.py::test_critical_routers_use_success_wrapper FAILED (intentional)
```

## Trainingssamenvatting

- Actor: CI-pipeline die `pytest tests/architecture/test_api_response_format_conformance.py` uitvoert.
- Voorwaarde: De vier router-bestanden in `ROUTER_FILES_SCOPE` bestaan.
- Actie (request): Draai `pytest tests/architecture/test_api_response_format_conformance.py::test_critical_routers_use_success_wrapper`.
- Systeemverwerking: De test parset de broncode met AST, selecteert alleen functies met `@router.*` decorator en controleert of return-statements conformant zijn (`"success"`, `JSONResponse`, `StreamingResponse`, `RedirectResponse`, `Response(`, `FileResponse` of pass-through keywords).
- Succesrespons: Test PASS met 0 non-conformante returns.
- Foutrespons: Test FAIL met lijst van bestand/regel combinatie(s) die geen success/data-wrapper gebruiken.
- Uitzonderingen: De test is opzettelijk ROOD totdat alle 248 non-conformante endpoints in scope zijn aangepast.
