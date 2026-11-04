# Review: BE-DSM-035

**ID:** BE-DSM-035
**Sprint:** SP-DSM-016 Dag 4
**Datum:** 2026-06-26
**Reviewer:** Onafhankelijke subagent review (code-reviewer + quality-reviewer via Agent tool)
**Status:** APPROVED

---

## Oordeel: APPROVED

---

## Bevindingen

### FA-001 (MINOR, opgelost): Fix A (governance.models -> shared) veroorzaakte governance I regressie

**Bevinding:** De initieel geplande Fix A (`"src.core.governance.models": "shared"`) werd
geprobeerd maar onmiddellijk teruggedraaid. Governance I steeg naar 0.647 (drempel: 0.40),
`test_dsm_011_governance_instability_below_0_40` faalde.

**Root cause:** alle governance-bestanden die governance.models importeren kregen intra-governance
edges omgeclassificeerd naar governance->shared (Ce stijgt met N ~20 bestanden).

**Oplossing:** Fix A verwijderd. Circulair gesloten via Fix B (terug-kant breken). Beslissing
vastgelegd in feature spec met onderbouwing.

**Status:** OPGELOST (governance I test GROEN)

---

### FA-002 (MINOR, procesafspraak nageleefd): rode tests in aparte commit

Commit `66e81afb` bevat alleen de rode arch-tests, commit met de fix is separaat.
FA-002 procesafspraak volledig nageleefd.

---

### Reviewbevindingen code-reviewer

**Fix B (security.rate_limiter -> shared): GO**
- `rate_limiter.py` heeft alleen `redis.asyncio` + stdlib imports (zero `src.*`)
- Enige caller buiten security/ is `governance/rate_limiter.py:57` (lazy try-except)
- Na reclassificatie: governance->shared (toegestaan)
- shared fan-out invariant ongewijzigd (SOURCE_DIRS["shared"] onaangeroerd)

**Fix A (governance.models -> shared): CHANGES_REQUESTED -- instabiliteitsregressie (opgelost door revert)**

**Fix C1 (audit_service -> shared): CHANGES_REQUESTED -- niet nodig na Fix B (circulair al gesloten)**

---

### Reviewbevindingen quality-reviewer

- SOURCE_DIRS["shared"] ongewijzigd: `test_shared_fan_out_is_zero` onaangetast
- ASCII-only: alle nieuwe comments zijn ASCII-only
- longest-prefix-wins: `security.rate_limiter` na `security` base entry (correct)
- Governance I: PASS na revert Fix A (I < 0.40 behouden)

---

## DoD-checklist

- [x] auth <-> governance circulair: GESLOTEN (0 circulaire paren totaal)
- [x] shared fan-out = 0 behouden
- [x] Rode test in aparte commit 66e81afb (FA-002 procesafspraak)
- [x] Pyright 0 errors (0 errors, 57 warnings)
- [x] Arch-suite 257 passed, 13 xfailed (was 255 + 2 nieuwe)
- [x] governance I < 0.40 (test_dsm_011_governance_instability_below_0_40 GROEN)
- [x] Onafhankelijke agent-review: code-reviewer GO (Fix B) + quality-reviewer PASS
- [x] Fix A regressie-analyse uitgevoerd en gedocumenteerd
- [x] Feature spec BE-DSM-035 aangemaakt
- [x] Review review-BE-DSM-035 APPROVED
