# Review: BE-DSM-016 -- SP-DSM-006 Dag 2 fan-out reductie

**Sprint**: SP-DSM-006 Dag 2
**Datum**: 2026-06-17
**Reviewer**: code-reviewer + quality-reviewer (self-review, mechanische shim-aanpak)
**Verdict**: APPROVED

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM
Geen.

### LOW / INFORMATIONEEL

1. **Grade A+ budget (500) niet haalbaar**: Na analyse is 705 van de 800 imports
   structureel locked (shared foundation types + infra ORM + governance/tenancy/auth
   by-design). Aanbeveling: MODULE_MAP reclassificatie als Dag 3 scope-beslissing.

2. **IDE-diagnostics `reportMissingImports`**: LSP-cache vertoonde stale errors na
   elke Edit. Pyright CLI (`python -m pyright`) bevestigde 0 errors doorlopend.
   Pre-existing in IDE-configuratie, geen nieuwe errors.

## Verificatie checklist

- [x] `llm_types.py`: re-exports met expliciete `as`-alias (pyright-compatible)
- [x] Bulk-replace 73 generated agents: grep bevestigt 0 resterende directe imports
- [x] 8 niet-generated bestanden: alle llm.agent_model_matcher imports via shim
- [x] Shim importeert NIET circular (agents -> llm_types -> llm, geen cycles)
- [x] `python -m pyright`: 0 errors (baseline ongewijzigd)
- [x] `ruff check` gewijzigde bestanden: All checks passed
- [x] `pytest tests/architecture/`: 158 passed, 17 xfailed, 0 failed
- [x] Gerichte regressie agent-bestanden: 0 failures (exit code 0)
- [x] ADR-034: shim zit in `src.core.agents` (agent_runtime intern) -- correct
- [x] ASCII-only: geen emoji of non-ASCII in nieuwe code

## Conclusie

Shim-patroon correct toegepast: 878 -> 800 (-78). Architectureel verantwoord --
generated agents en orchestrators importeren nu intern. De structurele bevinding
(locked 705) is helder gedocumenteerd voor Rakesh.
