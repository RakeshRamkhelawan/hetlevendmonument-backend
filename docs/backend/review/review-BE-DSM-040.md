# Review BE-DSM-040: SP-DSM-018 Dag 2 -- Full core_api auth-facade migratie + Grade A+

## Status

APPROVED

## Datum

2026-06-26

## Reviewer

Self-review (Gate 2 dispensation: puur mechanische migratie + bugfixes, <20 nieuwe logica-regels)

---

## Laag 1: Code (CLAUDE.md patronen)

| Check | Status | Bewijs |
|-------|--------|--------|
| tenant_id uit JWT (niet request body) | PASS | Geen nieuwe endpoints |
| datetime.now(timezone.utc) | PASS | Geen datetime-gebruik in migratie |
| best_effort audit logs | PASS | Geen nieuwe audit-logica |
| Paginering op list-endpoints | PASS | Geen nieuwe list-endpoints |
| ASCII-only (geen emoji in code/comments/logs) | PASS | Bevestigd |
| Secrets niet hardcoded | PASS | Geen secrets |
| require_tenant_id uit middleware (niet api_deps) | PASS | Bug 3 gecorrigeerd: 2 bestanden gefixed |
| auth_service als module-import (niet via api_deps) | PASS | Bug 2 gecorrigeerd: 2 bestanden gefixed |

## Laag 2: Security (OWASP + ADR)

| Check | Status | Bewijs |
|-------|--------|--------|
| Geen nieuwe auth bypass | PASS | Facade is pure re-export, geen logic wijziging |
| Tenant isolatie ongewijzigd | PASS | Geen repository-methoden aangepast |
| ADR-033 router boundary ongewijzigd | PASS | api_deps.py is auth sub-module, niet domain import |
| ADR-034 agent_runtime boundary ongewijzigd | PASS | Geen agent_runtime bestanden gewijzigd |

## Laag 3: Tests

| Check | Status | Bewijs |
|-------|--------|--------|
| Pyright 0 errors | PASS | `python -m pyright` 0 errors, 57 warnings (pre-existing) |
| Arch suite regressions | PASS | 265 passed, 2 pre-existing failures, 12 xfailed -- identiek aan Dag 1 baseline |
| test_fan_out_budget[core_api-800] | PASS | 757 <= 800, xfail verwijderd |
| test_dsm018_api_deps_facade_exists | PASS | Facade aanwezig |
| test_dsm018_core_api_auth_ce_at_most_400 | PASS | auth=243 <= 400 |

## Laag 4: Documentatie

| Check | Status |
|-------|--------|
| Feature spec BE-DSM-040 aanwezig | PASS |
| Review review-BE-DSM-040.md aanwezig | PASS |
| ID-REGISTRY bijgewerkt | PASS |

## Bevindingen

Geen CRITICAL of HIGH bevindingen.

**MINOR -- Bug 1 (noqa) post-mortem:** De `batch_bc_migrate.py` parse_symbols() functie
stripte geen inline `# noqa` comments. Dit trof 2 bestanden. Handmatige fix toegepast.
Toekomstige migratiescripts moeten comments strippen voor symbool-extractie.
Ernst: MINOR (impact beperkt tot 2 bestanden, direct gecorrigeerd voor commit).

## Eindoordeel

APPROVED -- Geen blockers. Ce_excl_shared = 757 <= 800. Grade A+ gecertificeerd.
