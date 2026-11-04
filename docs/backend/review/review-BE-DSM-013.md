# Review BE-DSM-013: SP-DSM-004 -- Aanpak B + Contract 5 backlog

Datum: 2026-06-17
Reviewer: subagent code-reviewer + quality-reviewer
Sprint: SP-DSM-004 Dag 1
Verdict: APPROVED WITH MINOR GAPS

---

## Samenvatting

Twee nieuwe import-linter contracts toegevoegd (`infra-no-api`, `governance-no-workflow-direct`).
Contract 5 comments bijgewerkt (backlog SP-DSM-005). Architectuurtest uitgebreid naar 9
required contracts. Falende xfail(strict=True) test gedocumenteerd voor Contract 5 backlog.
Lint-imports 9/9 kept, 0 broken. Pyright 0 errors, ruff clean.

---

## Bevindingen

### CRITICAL -- geen

### HIGH -- geen

### MINOR (opgelost voor commit)

**M1 -- Regex sloeg door naar Contract 6 sectie (quality reviewer)**
De oorspronkelijke regex `[governance-independence].*?allow_indirect_imports.*false` met
`re.DOTALL` matchte tot `allow_indirect_imports = false` in Contract 6 (`agent_runtime_boundary`).
Test toonde `[XPASS(strict)]` in plaats van `XFAIL`. Opgelost door sectie te isoleren:
`(?=\[importlinter:|$)` stopt bij de volgende `[importlinter:` header. OPGELOST.

**M2 -- Test body had for/if/return logic (quality reviewer)**
De eerste implementatie gebruikte een `for`-loop met `in_contract5` teller.
`testing.md`: "No logic (if/loops) in tests." Opgelost door regex-aanpak. OPGELOST.

**M3 -- Falende test miste `@pytest.mark.xfail` (quality reviewer CRITICAL)**
Zonder xfail brak de test de 0-failures baseline. Alle andere deferred architecture tests
in dit bestand gebruiken `@pytest.mark.xfail`. Opgelost: `@pytest.mark.xfail(strict=True, ...)`.
`strict=True` garandeert dat CI rood gaat zodra de test slaagt (forceert marker-verwijdering). OPGELOST.

**M4 -- infra-no-api comment misleidend (code reviewer INFO, opgelost)**
Origineel: "Dit contract handhaft alleen de directe infra->api grens." Dit suggereerde dat
Contract 3 (layers) de transitieve paden "catalogiseert" in plaats van bewaakt. Bijgewerkt
naar: "Contract 3 (layers) bewaakt al zowel directe als transitieve infra->api paden via
type=layers semantiek." OPGELOST.

### INFO

**I1 -- governance-no-workflow-direct: zero enforcement coverage voor nieuwe violations**
De enige directe violation (`dsar_service -> workflow.models`) staat in `ignore_imports`.
Met `allow_indirect_imports = true` worden transitive paden ook niet gevangen. Een nieuwe
directe `governance -> workflow` koppeling zou worden gemist totdat in SP-DSM-005 de
`ignore_imports` uitbreiding opvalt via `unmatched_ignore_imports_alerting = warn`.
`code-quality-reviewer` suggereert een aanvullende grep-based test. Dit is backlog SP-DSM-005
samen met de dsar_service workflow-adapter fix.

**I2 -- Contract 5 type-move >10 callers: deferred naar SP-DSM-005**
`OfficerVerdict` heeft >10 callers in `copilot/*`. Type-move naar `governance.models`
vereist een bredere refactoring. Gedocumenteerd in `test_contract5_governance_independence_hardened`
met `xfail(strict=True)`.

---

## Verificatie uitvoerd

- `lint-imports --config .importlinter`: 9 kept, 0 broken, 0 warnings
- `pytest tests/architecture/test_dsm_grade_a_plus.py -v`: 13 passed, 4 xfailed, 0 failed
- `python -m pyright`: 0 errors, 55 warnings (baseline)
- `ruff check src/`: All checks passed

---

## Eindoordeel: APPROVED WITH MINOR GAPS

Alle 3 minors (M1/M2/M3) en INFO M4 zijn opgelost voor commit. De twee INFO-items (I1/I2)
zijn gedocumenteerd en gebacklogd naar SP-DSM-005. Dag 1 klaar voor commit.
