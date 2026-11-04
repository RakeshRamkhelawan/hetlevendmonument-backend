# Review BE-SVC-049: Sync Router DB-cleanup

## Verdict: APPROVED WITH MINOR GAPS

## Reviewer
Claude (code-reviewer + security-reviewer, S2 Taak 2)

## Checklist

| Item | Status |
|------|--------|
| ADR-033 compliant: geen AsyncSession/get_db in router.py | PASS |
| Ongebruikte parameters correct verwijderd | PASS |
| Architecture test GROEN | PASS |
| Unit tests GROEN (18) | PASS |
| Pyright 0 errors | PASS |

## Minor Gaps

**MINOR-1 (pre-existing)**: Snapshot handlers hebben geen `get_current_user` -- unauthenticated stubs. Gepland voor stub-implementatie.

**MINOR-2 (pre-existing)**: Exception details bevatten raw `str(e)` in 500 responses. Fix bij stub-implementatie.
