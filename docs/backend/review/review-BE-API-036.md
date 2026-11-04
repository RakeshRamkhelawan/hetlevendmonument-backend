# Review: BE-API-036 -- FA-002 HTTPException 5xx Informatielek Fix

**ID:** BE-API-036
**Sprint:** SP-API-009 Dag 5
**Datum:** 2026-06-11
**Reviewer:** Gate 2 (code-reviewer + quality-reviewer, 2 rondes)
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

35 OWASP A5 violations gefixed in 10 bestanden. Architecture test uitgebreid met
f-string detectie, absoluut pad en i=j correctie.

---

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MINOR

**M1 -- `routing/router.py:148-152`: health-endpoint dict lek (buiten HTTPException scope)**
`return {"status": "error", "message": str(e)}` — lekt interne foutboodschap.
Gedocumenteerd als SP-API-010 backlog.

**M2 -- `autonomous/agents_router.py:119-123`: dict-gebaseerde lek**
`"message": "...%s" % str(e)[:200]` — zelfde lek via andere route.
Gedocumenteerd als SP-API-010 backlog.

---

## Checklist

- [x] ASCII-only: geen emoji of non-ASCII in gewijzigde bestanden
- [x] Geen `@pytest.mark.skip` toegevoegd
- [x] architecture test: absoluut pad, i=j fix, f-string detectie
- [x] 4xx violations onaangeroerd
- [x] logger.error pattern conform backend-patterns.md regel 10
- [x] `from e` exception chain toegevoegd aan alle violations
- [x] pyright 0 errors (baseline ongewijzigd)
- [x] ruff clean (all checks passed)
- [x] 75 passed, 3 xfailed (0 nieuwe failures)
- [x] 141 unit tests (agentic + api/v1) -- 0 failures
- [x] ADR-033 changelog bijgewerkt

## Eindoordeel

APPROVED WITH MINOR GAPS -- M1/M2 zijn pre-existing buiten HTTPException-scope,
gedocumenteerd voor SP-API-010. Alle 35 violations en architecture test PASS.
