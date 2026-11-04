# Review: BE-API-035 -- FA-004 Startup Smoke-Test

**ID:** BE-API-035
**Sprint:** SP-API-009 Dag 4
**Datum:** 2026-06-11
**Reviewer:** self-review (< 20 regels, 1 bestand -- Gate 2 drempel)
**Status:** APPROVED

---

## Samenvatting

Voegt `tests/architecture/test_startup.py` toe met 2 smoke-tests voor ADR-033
router registratie. Geen productiecode gewijzigd.

---

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MINOR
Geen.

---

## Checklist

- [x] ASCII-only: geen emoji of non-ASCII in testbestand
- [x] Geen `@pytest.mark.skip` of losse `xfail`
- [x] Importpaden correct: `src.core.api.router_registry` en `src.core.api.main` geverifieerd
- [x] `register_all_routers` retourneert `int` (124) -- type-check in assert
- [x] Geen productiecode aangeraakt
- [x] pyright 0 errors (baseline ongewijzigd)
- [x] ruff clean
- [x] 74 passed, 3 xfailed (2 nieuw groen)
- [x] Geen regressies

## Eindoordeel

APPROVED -- minimale test-only change, alle checks groen.
