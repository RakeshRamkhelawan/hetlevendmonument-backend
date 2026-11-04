# Review: BE-DSM-014 -- Contract 5 Hardening

**Sprint**: SP-DSM-005 Dag 1
**Datum**: 2026-06-17
**Reviewer**: code-reviewer + quality-reviewer (self-review, <20 regels per bestand, gerichte type-move)
**Verdict**: APPROVED

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
Geen.

### LOW / INFORMATIONEEL

1. **`src -> src.workers` in Contract 5 ignore_imports**: Zelfde statische-analyse-artefact
   als in Contract 3 (layers). De ignore is correct en gedocumenteerd. Geen runtime impact.
   Zie ook: Contract 3 `ignore_imports` voor hetzelfde patroon (SP-DSM-003 Dag 2).

2. **Test regex bugfix (`$` -> `\Z`)**: Pre-existing bug in de xfail-test die alleen
   zichtbaar werd na activatie. Fix is correct: `\Z` matcht end-of-string i.p.v.
   end-of-line bij `re.MULTILINE`. Geen andere tests geraakt.

3. **Pyright warnings over unused imports in governance/models.py**: Pre-existing
   `Optional` warning, al aanwezig voor deze dag. Geen nieuwe errors.

## Verificatie checklist

- [x] Type-identiteit geverifieerd: `VerdictType is VT2`, `OfficerVerdict is OV2`, etc.
- [x] `lint-imports`: 9 kept, 0 broken
- [x] `pytest tests/architecture/`: 14 passed, 3 xfailed, 0 failed
- [x] `test_contract5_governance_independence_hardened`: PASSED
- [x] `python -m pyright`: 0 errors (baseline ongewijzigd)
- [x] `ruff check src/`: All checks passed
- [x] Gerichte regressie 79 tests: 0 failures
- [x] ADR-003 naleving: geen tenant_id wijzigingen
- [x] Geen datetime.now() of emoji in code
- [x] Backward compat: re-export `as OfficerVerdict` (pyright-compatible expliciete re-export)

## Conclusie

Contract 5 correct gehard: `allow_indirect_imports = false`, 0 governance->copilot
direct-imports. Type-move naar `governance.models` volgt ADR-027. Backward compat
bewaard via expliciete `as`-re-exports. Geen CRITICAL of HIGH bevindingen.
