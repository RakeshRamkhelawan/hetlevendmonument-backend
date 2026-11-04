# Review: BE-API-034 -- ADR-033 circulaire dep focus_builder

**ID:** BE-API-034
**Sprint:** SP-API-009 Dag 3
**Datum:** 2026-06-11
**Reviewer:** Gate 2 ronde 3 (code-reviewer + quality-reviewer)
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Verwijdert de `agent_runtime -> core_api` circulaire afhankelijkheid door
`_get_internal_agents` te verplaatsen van `src.core.api.v1.focus_builder.agents`
naar het nieuwe `src.core.als.agents.focus_builder_agents` module.

---

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MINOR GAPS (backlog)

| ID | Bevinding | Bewijs | Ernst | Actie |
|----|-----------|--------|-------|-------|
| FA-M01 | `_DEPT_ICONS` gebruikt ASCII string identifiers; frontend verwacht mogelijk andere icon-namen | `focus_builder_agents.py:1-30` | MINOR | TODO(SP-API-010): afstemmen met frontend |
| FA-M02 | `agents.py` bevat nog emoji in legacy strings | `agents.py:_CATEGORY_MAP` | MINOR | Scope SP-API-010 |

---

## Gate 2 oordeel (ronde 3)

**code-reviewer:** GO
**quality-reviewer:** GO

Beide reviewers akkoord na 3 rondes. Ronde 1 en 2 hadden CHANGES_REQUESTED
op: binding copy semantics voor `_INTERNAL_AGENTS_CACHE`, `no_implicit_reexport`
compliance, CI gap `tests/architecture/` niet in run, en onnodige re-export van
`_build_als_agents`. Alle blockers gefixed in implementatie.

---

## Checklist

- [x] ADR-033 criterium 4: agent_runtime -> core_api = 0 (lint-imports: 4 KEPT 0 BROKEN)
- [x] `no_implicit_reexport`: `_get_internal_agents as _get_internal_agents` syntax
- [x] Geen re-export van `_INTERNAL_AGENTS_CACHE` (binding copy risico vermeden)
- [x] AUDIT-COLL-03c: `_build_als_agents()` niet op module-level in nieuw bestand
- [x] ASCII-only: geen emoji of non-ASCII in `focus_builder_agents.py`
- [x] `tests/architecture/` toegevoegd aan CI (structurele gap gedicht)
- [x] SP-API-010 backlog tests `xfail(strict=True)` -- CI-compatibel
- [x] pyright 0 errors (baseline ongewijzigd)
- [x] ruff clean
- [x] 31 gerichte tests passed, 72 architecture tests passed (3 xfailed)
- [x] datetime.now(timezone.utc) niet van toepassing (geen datetime code)
- [x] tenant_id niet van toepassing (geen endpoint code)
