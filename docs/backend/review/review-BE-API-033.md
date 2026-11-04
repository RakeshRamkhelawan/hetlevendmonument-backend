# Review BE-API-033: import-linter Contract 1 -- api-no-domain

**Reviewer:** code-reviewer + quality-reviewer (Gate 2, 2 rondes)
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-06-11

## Bevindingen

### FA-001 (MINOR -- backlog)
**Laag:** 1 -- Code
**Bevinding:** Lokale agent-caches in critic_router.py, health_router.py en workflow_router.py
zijn module-lokaal en gescheiden van de caches in dependencies.py. `clear_tenant_cache()`
in dependencies.py raakt de router-lokale caches niet.
**Ernst:** MINOR
**Actie:** TODO(SP-API-010): consolideer lokale caches en factory functies naar dependencies.py.

### FA-002 (MINOR -- backlog)
**Laag:** 1 -- Code
**Bevinding:** stats_router.py importeert factory functies cross-router uit health_router.py
en workflow_router.py. Architectureel correct voor cache-coherentie, maar koppelt routers
aan elkaar.
**Ernst:** MINOR
**Actie:** TODO(SP-API-010): redirect stats_router naar dependencies.py factories wanneer
de lokale caches worden geconsolideerd.

### FA-003 (MINOR -- backlog, bevonden door Final Approver 2026-06-11)
**Laag:** 1 -- Code
**Bevinding:** `clear_tenant_cache()` in dependencies.py is geexporteerd via `__all__` maar
heeft geen callers in `src/`. Ook de dependencies.py caches worden nooit geevict. Dit geldt
ook voor de lokale caches in de 3 router bestanden. Een tenant kan nooit worden geevict,
ook niet bij suspensie of verwijdering.
**Bewijs:** grep op `clear_tenant_cache` in src/ geeft alleen de definitie op
`dependencies.py:71` en de `__all__` registratie op `:96`. Geen caller gevonden.
**Ernst:** MINOR (pre-existing, buiten scope SP-API-009)
**Actie:** TODO(SP-API-010): voeg caller toe vanuit tenant suspend/delete flow, en consolideer
alle 4 cache-populaties (dependencies + 3 routers) zodat evictie compleet is.

## Bevestigingen

- ADR-033 Contract 1: PASSED (import-linter: 4 contracts KEPT, 0 BROKEN)
- import patronen: alle router bestanden importeren agent-klassen via dependencies facade
- Tenant isolatie: caches zijn per-tenant (dict[int, Agent]) -- ongewijzigd
- CLAUDE.md compliance: datetime.now(timezone.utc), geen hardcoded secrets, ASCII-only
- ruff: All checks passed
- pyright: 0 errors (baseline 0 ongewijzigd)
- mypy: 0 errors

## Oordeel

**APPROVED WITH MINOR GAPS** -- import-linter ADR-033 criterium 2 voldaan.
Minors gaan naar SP-API-010 backlog.
