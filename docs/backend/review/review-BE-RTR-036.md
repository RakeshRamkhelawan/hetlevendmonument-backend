# Review — BE-RTR-036 Router Boundary Hardening

**Datum:** 2026-06-12  
**Reviewer:** Claude Sonnet 4.6 (code-reviewer + quality-reviewer)  
**Sprint:** SP-API-010  
**Verdict:** APPROVED WITH MINOR GAPS

---

## Samenvatting

14 ADR-033 violations gefixed via het ADR-033 facade-patroon (7 dependencies.py bestanden
aangemaakt of uitgebreid). Contract 1 scope uitgebreid met auth/router.py en 4 nieuwe
forbidden_modules. Alle 13 architecture tests groen. 0 contracts broken. Pyright 0 errors
op gewijzigde bestanden.

---

## Bevindingen

### GOEDGEKEURD

| Check | Status |
|-------|--------|
| ADR-033 facade-patroon correct toegepast | PASS |
| Geen tenant_id uit request body | PASS |
| Geen datetime.now() / datetime.utcnow() | PASS |
| Geen hardcoded secrets of PII | PASS |
| Geen emoji of non-ASCII in code/comments | PASS |
| Alle imports zijn ASCII-only | PASS |
| `as X` patroon voor re-exports (F401-suppressor) | PASS |
| ruff E402 globally ignored — import os na statement OK | PASS |
| pyright 0 errors op gewijzigde bestanden | PASS |
| 13/13 boundary tests GROEN | PASS |
| 106/106 architecture tests GROEN (12 xfailed) | PASS |
| 4/4 import-linter contracts KEPT | PASS |

### MINOR GAPS (geen blockers)

**MG-1:** Import-linter warning `ml.dependencies -> ml.tool_predictor` niet in graph.
- Oorzaak: `sklearn`/`joblib` ontbreken in analyse-venv waardoor import-linter de
  module-grens niet volledig kan tracen.
- Impact: 0 (contracts blijven KEPT; de import bestaat wel in de code).
- Actie: documenteren in final-approver brief.

**MG-2:** 2 pre-existing pyright errors in `crag_endpoints.py` en `pack_intent_matcher.py`
- Niet veroorzaakt door SP-API-010; aanwezig voor deze sprint.
- Actie: aparte backlog-taak voor pyright baseline herstel.

**MG-3:** `v1/routing/router.py` heeft `# orphan:exempt` marker — pending Strangler Fig
- Dit bestand staat buiten de normale ADR-033 v1/ migratie.
- Actie: Dag 4/5 migratie (al gepland).

**MG-4:** `test_forgot_password_calls_email_service` flaky onder xdist -n 8
- Slaagt in isolatie; pre-existing xdist fixture-ordering flakiness.
- Niet veroorzaakt door SP-API-010 import-restructuring.
