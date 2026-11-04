# Review BE-SEC-018: best_effort wrapping voor security audit DB writes

**Reviewer:** Gate 2 (code-reviewer + quality-reviewer), 2026-06-13
**Status:** APPROVED WITH MINOR GAPS

---

## Bevindingen

### CRITICAL — Geen

### HIGH — Geen

### MEDIUM (opgelost voor commit)

| # | Bevinding | Bestand | Actie |
|---|-----------|---------|-------|
| M-1 | `_last_hash` buiten best_effort block → hash chain corruptie bij mislukte commit | security_audit_service.py | Opgelost: _last_hash binnen best_effort body |
| M-2 | Dead `except SQLAlchemyError` blocks na wrapping | security_audit_service.py | Opgelost: blok verwijderd |
| M-3 | `exc_info=True` ontbrak in logger.error calls | security_audit_service.py | Opgelost: toegevoegd |
| M-4 | Architecture tests gebruikten relatieve paden | test_security_audit_best_effort.py | Opgelost: Path(__file__).parents[2] |
| M-5 | Architecture test verifieert _last_hash placement niet | test_security_audit_best_effort.py | Opgelost: test_log_event_last_hash_inside_best_effort toegevoegd |

### LOW / MINOR (geaccepteerd)

| # | Bevinding | Bestand | Actie |
|---|-----------|---------|-------|
| L-1 | `tenant_id or 0` in _create_alert (pre-existing) | security_audit_service.py | Backlog |
| L-2 | Em-dash in best_effort.py log string (pre-existing) | best_effort.py | Buiten scope SP-DSM-001 |

---

## Gate 3 verificatie

- `python -m pyright`: 0 errors
- `python -m pytest tests/architecture/ -v`: 112 passed, 12 xfailed
- `python -m pytest tests/unit/test_security_audit_a09.py tests/unit/test_security_audit_service.py`: 86 passed
- Architecture tests waren ROOD voor de fix: bewijs in pytest output

---

## Eindoordeel

**APPROVED WITH MINOR GAPS** — alle CRITICAL/HIGH bevindingen opgelost voor commit.
MEDIUM bevindingen M-1 t/m M-5 zijn allemaal gefixed. Minor L-1 en L-2 zijn pre-existing
en gaan naar backlog.
