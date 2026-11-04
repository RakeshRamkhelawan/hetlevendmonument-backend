# Review: BE-DSM-015 -- SP-DSM-006 Dag 1 governance->agent_runtime = 0

**Sprint**: SP-DSM-006 Dag 1
**Datum**: 2026-06-17
**Reviewer**: code-reviewer (subagent) + quality-reviewer (self-review)
**Verdict**: APPROVED

## Bevindingen

### CRITICAL
Geen.

### HIGH
Geen.

### MEDIUM

1. **MEDIUM-1 (OPGELOST)**: `str(tenant_id)` -> `tenant_id` voor asyncpg integer type-binding.
   asyncpg gebruikt strikte type-binding; `agents.tenant_id` is Integer. `str()` casting
   zou op productie `asyncpg.exceptions.DataError` veroorzaken. Gecorrigeerd voor commit.

### LOW

1. **LOW-1 (OPGELOST)**: TODO in testdocstring verwees naar pre-fix toestand. Verwijderd.
   CLAUDE.md: "Don't commit TODOs you can do now."

## Verificatie checklist

- [x] `from src.core.agents.models import Agent` volledig verwijderd uit governance dir
- [x] SQL injection: `tenant_id` gebonden als `:tenant_id` named parameter (geen string-concatenatie)
- [x] Tenant isolatie: `WHERE tenant_id = :tenant_id` filtert correct
- [x] DSAR data correctheid: `id, name, agent_type` -- zelfde velden als ORM-query
- [x] Error handling: `logger.error("...", type(e).__name__, e, exc_info=True)` (Pattern 10)
- [x] `begin_nested()` verwijderd: correct voor read-only SELECT (geen savepoint nodig)
- [x] ASCII-only: geen emoji of non-ASCII in nieuwe code
- [x] `datetime.now(timezone.utc)`: bestaand gebruik correct, geen nieuwe violations
- [x] ADR-034 naleving: governance->agent_runtime = 0 (AST-geverifieerd)
- [x] `python -m pyright`: 0 errors (baseline ongewijzigd)
- [x] `ruff check src/core/governance/dsar_service.py`: All checks passed
- [x] Gerichte regressie (52 DSAR + GDPR tests): 0 failures
- [x] `test_governance_has_zero_direct_agent_runtime_imports`: PASSED

## Conclusie

Raw SQL vervangt ORM-import correct. Tenant-isolatie, SQL-injection veiligheid, en DSAR
data-correctheid zijn geverifieerd. MEDIUM-1 en LOW-1 zijn opgelost voor commit.
Geen CRITICAL of HIGH bevindingen na correcties.
