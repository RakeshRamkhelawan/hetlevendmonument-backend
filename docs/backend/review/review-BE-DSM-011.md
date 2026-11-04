# Review BE-DSM-011: SP-DSM-003 Dag 1 -- Import-linter Contract 2+5

Datum: 2026-06-17
Reviewer: subagent code-reviewer + quality-reviewer
Sprint: SP-DSM-003 Dag 1
Verdict: APPROVED WITH MINOR GAPS

---

## Samenvatting

Contract 2 en Contract 5 zijn geactiveerd. Contract 3 is bewust deferred (>50 violations
stopvoorwaarde). 6 stale entries verwijderd. Lint-imports 6/6 kept, 0 broken. Pyright 0
errors, ruff 0 errors. Architectuurtests identiek aan baseline (12 passed, 4 xfailed).

---

## Bevindingen

### CRITICAL -- geen

### HIGH -- geen

### MINOR (opgelost voor commit)

**M1 -- xfail-reden stale (code reviewer)**
`test_dsm_grade_a_plus.py:95` reden was `"Contract 2/3/5 disabled until SP-AGT-004 +
SP-API-011"`. Contracts 2 en 5 zijn nu actief. Reden bijgewerkt naar
`"Contract 3 (layers) disabled -- SP-DSM-004"`. OPGELOST.

**M2 -- aparte known-violation comment per entry (quality reviewer)**
De tweede `ignore_imports` entry voor `retention_cleanup` piggybacked op de eerste comment.
Aparte `# known-violation:` comment toegevoegd. OPGELOST.

**M3 -- allow_indirect_imports motivering ontbrak (code reviewer)**
Contract 5 miste uitleg voor `allow_indirect_imports = true`. Uitleg-comment toegevoegd.
OPGELOST.

### INFO

**I1 -- Contract 2 dekking smaller dan oorspronkelijke naam suggereert**
Het contract dekt 4 van de ~55 v1-domeinen. De naam claimt een bredere invariant.
Acceptabel als baseline; backlog-item voor SP-DSM-004 om dekking uit te breiden.

**I2 -- Contract 5 two known-violations zijn echte schendingen**
`hash_chain` en `retention_cleanup` importeren copilot types in de verkeerde richting.
De fix (types verplaatsen naar governance.models of shared) is gelogd als SP-DSM-004.

**I3 -- Contract 3 deferred wegens >50 violations**
Stopvoorwaarde correct getriggerd. De `layers` constraint is fundamenteel incompatibel
met de huidige ADR-027/ADR-034 architectuur waarbij domain modules elkaar importeren.
Backlog SP-DSM-004: herontwerp naar permissieve same-layer definitie.

---

## Verificatie uitvoerd

- `lint-imports --config .importlinter`: 6 kept, 0 broken, 0 warnings
- `pytest tests/architecture/test_dsm_grade_a_plus.py -v`: 12 passed, 4 xfailed
- `python -m pyright`: 0 errors, 55 warnings (baseline)
- `ruff check src/`: All checks passed

---

## Eindoordeel: APPROVED WITH MINOR GAPS

Alle drie minors zijn opgelost voor de commit. De INFO-items zijn gedocumenteerd en
gebacklogd naar SP-DSM-004. Dag 1 is klaar voor commit.
