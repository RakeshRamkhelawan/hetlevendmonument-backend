# Review: BE-DSM-028 -- SP-DSM-012 infra->governance 2->0

## Datum
2026-06-24

## Reviewer
Claude (quality-reviewer)

## Uitkomst
**APPROVED**

---

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
Geen.

### LOW / MINOR

**L-001** — `test_dsm_medium_pairs_tracking.py::test_governance_infra_terug_not_growing`
bewaakt `infra->governance <= 2` als ceiling. Nu infra->governance = 0, is de ceiling niet
meer nodig maar ook niet schadelijk. Update naar `== 0` in een volgende cleanup-sprint.
**Ernst:** MINOR

---

## CLAUDE.md compliance

| Check | Status |
|-------|--------|
| Geen datetime.now() / datetime.utcnow() | PASS |
| Geen tenant_id uit request body | N.v.t. |
| Geen emoji / non-ASCII in code of comments | PASS |
| pyright 0 errors | PASS |
| Geen nieuwe test failures | PASS (220 arch tests groen) |
| ADR-004 (ORM tenant filtering) | PASS -- __tablename__ guard correct |

---

## ADR compliance

| ADR | Bevinding |
|-----|-----------|
| ADR-004 | PASS: AuditLog skip-logica bewaard via `__tablename__` check; security-pad vereenvoudigd |

---

## Veiligheidsanalyse Fix 1

De outer `try/except Exception` verwijdering is veilig:
- `getattr(entity_class, "__tablename__", "")` gooit nooit een exception
- `== "audit_logs"` vergelijking ook niet
- De inner `try/except` voor `_SAString` type-detection blijft intact
- Exceptions van `statement.where()` propageren nu correct naar de outer
  `except (AttributeError, InvalidRequestError)` (fail-secure: `literal(False)` filter)

Netto veiligheidseffect: **verbeterd** -- de eerdere silent exception-swallowing path
die AuditLog tenant-filterde in het fallback-pad is nu weg.
