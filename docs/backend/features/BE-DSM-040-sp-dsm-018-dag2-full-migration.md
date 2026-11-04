# BE-DSM-040: SP-DSM-018 Dag 2 -- Full core_api auth-facade migratie (Batch B+C) + Grade A+ certificering

## Status

APPROVED

## Sprint

SP-DSM-018 Dag 2

## Datum

2026-06-26

## Samenvatting

Volledige migratie van alle resterende core_api bestanden (157 bestanden) naar de
`src/core/auth/api_deps.py` facade. Na migratie is de Grade A+ drempel behaald:
core_api Ce_excl_shared = 757 <= 800.

## Deliverables

### 1. Batch B+C migratie (157 bestanden)

Alle bestanden in `src/core/api/` die nog direct auth sub-modules importeerden zijn
gemigreerd via `batch_bc_migrate.py`. Na migratie: core_api->auth = 243 (was 365 na Dag 1).

### 2. Post-migratie bugfixes (4 bestanden)

Vier bestanden vereisten handmatige correctie na de geautomatiseerde migratie:

| Bestand | Bug | Fix |
|---------|-----|-----|
| `src/core/api/v1/workflow/dependencies.py` | Inline `# noqa: F401` comments braken consolidated import (OAuth2Scope in comment) | Handmatige correctie |
| `src/core/api/v1/subagents/router.py` | Zelfde noqa-bug | Handmatige correctie |
| `src/core/api/auth/router_registration.py` | `auth_service` module incorrect in api_deps import | Split: module-import + api_deps-import |
| `src/core/api/v1/admin/users_router.py` | Zelfde auth_service module-bug | Split: module-import + api_deps-import |

Aanvullend: 2 bestanden importeerden `require_tenant_id` via api_deps (niet beschikbaar):

| Bestand | Fix |
|---------|-----|
| `src/core/api/v1/analytics/agents.py` | `require_tenant_id` terug naar `src.core.middleware.tenant_context` |
| `src/core/api/v1/sync/json_router.py` | Idem |

### 3. Grade A+ certificering: xfail verwijderd

`tests/architecture/test_dsm_grade_a_plus.py::test_fan_out_budget[core_api-800]`
xfail-marker verwijderd: test PASSES als gewone test.

## DSM Metrics

Ce_excl_shared = fan-out - shared-edges (alleen de "shared" laag wordt uitgesloten;
auth, governance, agent_runtime e.a. tellen MEE in de Ce-berekening).

| Metriek | Voor SP-DSM-018 | Na Dag 1 | Na Dag 2 | Target |
|---------|-----------------|----------|----------|--------|
| core_api fan-out | 966 | ~1009 | 1013 | -- |
| core_api->auth edges | ~450 | 365 | 243 | -- |
| core_api->shared edges | ~254 | 254 | 256 | -- |
| Ce_excl_shared (=fan-out - shared) | 966 | ~755 | **757** | <=800 |
| Grade A+ budget | BLOCKER | BEREIKT | GECERTIFICEERD | PASS |

## Arch Tests

| Test | Status |
|------|--------|
| `test_dsm018_api_deps_facade_exists` | PASS |
| `test_dsm018_core_api_auth_ce_at_most_400` | PASS (auth=243 <= 400) |
| `test_fan_out_budget[core_api-800]` | PASS (757 <= 800, xfail verwijderd) |

## Pyright

0 errors (baseline 0, ongewijzigd).

## Root Causes Migratie-bugs

### Bug 1: Inline noqa comments

`parse_symbols()` stripte geen inline `# noqa` comments van import-regels. Als een
bestand `from src.core.auth.scopes import OAuth2Scope  # noqa: F401` had, werd
`OAuth2Scope  # noqa: F401` als symboolnaam opgeslagen. De consolidated import werd
dan `from src.core.auth.api_deps import req_scopes  # noqa: F401, OAuth2Scope  # noqa: F401`
waarbij Python alles na `#` als comment beschouwt — OAuth2Scope wordt nooit geimporteerd.

### Bug 2: auth_service als sub-module object

`from src.core.auth import auth_service` importeert de sub-module (niet een klasse).
De migratie captuurde `auth_service` als symbool en plaatste het in de api_deps import.
api_deps exporteert de module niet. Fix: herstel directe sub-module import naast api_deps import.

### Bug 3: require_tenant_id niet in auth

`require_tenant_id` komt uit `src.core.middleware.tenant_context`, niet uit auth.
De migratie trof 2 bestanden die dit symbool via een gecombineerde auth-import hadden.
Fix: split naar correcte middleware-import.

## Wijzigingen

- `src/core/api/v1/workflow/dependencies.py` (bugfix noqa)
- `src/core/api/v1/subagents/router.py` (bugfix noqa)
- `src/core/api/auth/router_registration.py` (bugfix auth_service module)
- `src/core/api/v1/admin/users_router.py` (bugfix auth_service module)
- `src/core/api/v1/analytics/agents.py` (bugfix require_tenant_id)
- `src/core/api/v1/sync/json_router.py` (bugfix require_tenant_id)
- `tests/architecture/test_dsm_grade_a_plus.py` (xfail verwijderd)
- 151+ gemigreerde bestanden in `src/core/api/` (Batch B+C)


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-DSM-018 Dag 2: Batch B+C 157 bestanden gemigreerd + 6 bugfixes (noqa/auth\_service/require\_tenant\_id). Ce\_excl\_shared=757<=800. xfail verwijderd. Grade A+ GECERTIFICEERD. Pyright 0 errors. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-DSM-018 Dag 2: Batch B+C 157 bestanden gemigreerd + 6 bugfixes (noqa/auth\_service/require\_tenant\_id). Ce\_excl\_shared=757<=800. xfail verwijderd. Grade A+ GECERTIFICEERD. Pyright 0 errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
