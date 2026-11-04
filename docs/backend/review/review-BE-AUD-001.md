# Review BE-AUD-001 -- AuditService.log_event() transactie-grens fix

**Sprint:** SP-AUDIT-003 Dag 1
**Datum:** 2026-06-30
**Reviewer:** code-reviewer + security-reviewer (Gate 2)
**Uitkomst:** APPROVED WITH MINOR ISSUES

---

## Bevindingen

### GEFIXD (in deze commit)

| ID | Bevinding | Ernst | Fix |
|----|-----------|-------|-----|
| R-001 | 5 bestaande tests asserteerden `commit.assert_called_once()` -- na fix FOUT | BLOCKER | `flush.assert_called_once()` + `commit.assert_not_called()` |
| R-002 | `test_log_event_handles_database_error` injecteerde error in `commit` -- na fix niet meer getriggerd | BLOCKER | Injectie verplaatst naar `flush` |
| R-003 | Docstring vermeldde geen flush-semantiek | MINOR | Bijgewerkt met "flush() semantics: entry is durable only when caller commits (ADR-019)" |
| R-004 | Nieuwe tests asserteerden geen `result is True` | MINOR | `assert result is True` toegevoegd |

### PRE-EXISTING (aparte backlog, buiten scope SP-AUDIT-003)

| ID | Bevinding | Ernst | Actie |
|----|-----------|-------|-------|
| R-005 | `log_security_event()` logt raw `details` dict -> PII-risico | HIGH | TODO(SP-AUDIT-004) |
| R-006 | `tenant_id=None` in `log_event()` stil verworpen bij DB NOT NULL | MEDIUM | TODO(SP-AUDIT-004) |
| R-007 | Scheduling callers zonder `db.commit()` -- FALSE ALARM: `get_db` auto-commit op regel 489 | N/A | Geen actie |
| R-008 | Dead branch in `log_request_audit()` severity-logica | LOW | TODO(SP-AUDIT-004) |

---

## Oordeel

**APPROVED WITH MINOR ISSUES** -- alle BLOCKER en MINOR items gefixed. Pre-existing issues
gedocumenteerd voor SP-AUDIT-004 backlog. `get_db` auto-commit (regel 489) bevestigt dat
scheduling callers veilig zijn na de fix.
