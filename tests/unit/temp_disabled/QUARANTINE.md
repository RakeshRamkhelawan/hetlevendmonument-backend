# Unit Test Quarantine

Owner: Platform Engineering (backend)
Target Reactivation Date: 2026-06-15

## Purpose

Temporary quarantine for unstable or timing-sensitive unit tests that can block CI.
This list must shrink over time; add tests here only with a concrete reactivation plan.

## Reactivation Policy

1. Pick one quarantined test module per sprint day.
2. Run it standalone with strict timeout.
3. Fix root cause and move test back to regular unit suite.
4. Update this file with status and date.

## Current Focus

- Stabilize governance/import paths and sync snapshot tests first.
- Re-enable auth/admin/workflow coverage in small batches.

## test_company_templates_seed.py (integration test in unit directory)

| Kolom | Waarde |
|-------|--------|
| **Reden** | Test roept `db_manager.initialize()` aan — echte asyncpg PostgreSQL connectie op productie-URL. Geen mocks. TCP-check op poort 5455 slaagt bij Docker up, maar asyncpg connectie wordt geweigerd (`ConnectionRefusedError: WinError 1225`). Hierdoor wordt de `@pytest.mark.requires_postgres` skip omzeild. |
| **Root cause** | `db_manager` gebruikt de productie `DATABASE_URL`, niet de test-database URL. Dit is een integratie-test die per ongeluk in `tests/unit/` terecht is gekomen. |
| **Coverage gap** | Company template seeding (`seed_platform_templates`) en de bijbehorende API response. Gedeeltelijk gedekt door integratietests. |
| **Reactivatieplan** | Verplaats naar `tests/integration/company/test_company_templates_seed.py`. Gebruik `postgres_session` fixture uit `tests/integration/conftest.py`. |
| **Actie** | Aparte sprint: `SP-COMP-INT-01` |
| **Quarantinedatum** | 2026-06-08 |

## test_mypy_audit.py (subprocess timeout in batch)

| Kolom | Waarde |
|-------|--------|
| **Reden** | Subprocess-based mypy scan over ~1700 bestanden; looptijd 60-180s per test. In een parallelle `-n 8` batch-run overschrijdt dit de 60s timeout en crasht de worker. |
| **Root cause** | Elke test roept `subprocess.run([..., "scripts/run_mypy_audit.py"])` aan. In isolatie groen; in xdist batch timeout. |
| **Coverage gap** | mypy type-checking wordt al als dedicated CI-stap uitgevoerd in `.github/workflows/ci-feature.yml`. Geen coverage verlies. |
| **Reactivatieplan** | Herschrijf tests naar in-process mypy API (geen subprocess) zodat ze binnen 60s draaien, of verplaats naar `tests/integration/` met `--timeout=300`. |
| **Quarantinedatum** | 2026-06-07 (commit `2dc0c36a`) |
| **Actie** | Gequarantineerd door SP-API-008/009 unit test stabilisatie sprint. |

## Pyright Subprocess Tests (test_pyright_audit.py)

**Status:** Permanent quarantine -- NOT for reactivation into unit suite.

**Why quarantined:** Each test invokes `subprocess.run([..., "scripts/run_pyright_audit.py"])` which
runs a full pyright scan over ~1700 files. Runtime: 60-300 seconds per test. This causes the entire
unit suite to timeout when collected.

**Root cause fixed (2026-05-30):** `tests/unit/temp_disabled` added to pyproject.toml
`norecursedirs` and `addopts --ignore`. Previously only `temp_disabled_backup` was ignored.

**Alternative:** Pyright runs as a dedicated CI step in `.github/workflows/ci-feature.yml`
(no pytest involved). The baseline comparison logic is tested there.

**To run manually (opt-in only):**
```bash
pytest tests/unit/temp_disabled/test_pyright_audit.py --run-typecheck --timeout=600
```
Note: `--timeout=600` is required because the global pytest timeout (300s) would fire
before the 600s subprocess timeout if omitted.

**Marked with:** `@pytest.mark.slow` + `@pytest.mark.typecheck` (skipped by default via conftest.py opt-in hook).

## test_mission_endpoints.py (SP-A01 regressie)

| Kolom | Waarde |
|-------|--------|
| **Reden** | `ImportError: cannot import name '_create_sample_mission'` — in-memory helpers verwijderd in PostgreSQL-migratie (commit `ba1e82fb`, 2026-05-28) |
| **Root cause** | Test schreef tegen de oude dict-gebaseerde opslag (`_missions_store`, `_save_mission`, `_get_mission_by_id`, `_create_sample_mission`). SP-A01 verwijderde deze volledig en verving ze door `MissionORM` + async SQLAlchemy queries. |
| **Coverage gap** | Missie-endpoints (create, list, get, approve, reject) hebben geen actieve unit tests meer. SP-A01 heeft 22 integratietests, maar unit-coverage ontbreekt. |
| **Reactivatieplan** | Herschrijf tegen `MissionORM` (zie `src/core/api/mission_endpoints.py` en `src/core/models/mission.py`). Gebruik `AsyncMock` voor `AsyncSession`. SP-A01-patroon is het referentiepatroon. |
| **Actie** | Aparte sprint: `SP-MIS-01` (schatting: 1 dag) |
| **Niet verwijderen** | File bevat 1.335 regels dekking — waardevolle basis voor de herschrijving. |


## test_sp_a01_missions_behavioral.py (xdist PostgreSQL race condition)

| Kolom | Waarde |
|-------|--------|
| **Reden** | `TestMissionEndpointsBehavioral` gebruikt `pg_client` fixture met een echte PostgreSQL-database. In `-n 8` parallelle runs kan een ander worker DROP SCHEMA CASCADE uitvoeren tussen een INSERT en de bijbehorende SELECT (GET-tests), waardoor 404/500 optreden in plaats van het verwachte 200/422. |
| **Root cause** | `pg_client` heeft function-scope: bij elke test wordt het schema opgebouwd en afgebroken. Bij 8 gelijktijdige workers overlapt de teardown van worker A met de setup van worker B. `_NonRefreshingSession` dekt de `db.refresh()` race maar niet de schema-drop race tijdens GET-requests. |
| **Coverage gap** | Missions endpoints gedragsvalidatie (POST 201, GET 404, POST 422). Gedeeltelijk gedekt door `TestMissionEndpointsNoDictStore` (blijft in reguliere suite). |
| **Reactivatieplan** | Refactor `pg_client` naar `scope="module"` fixture zodat setup/teardown eenmaal per klasse plaatsvindt i.p.v. per test. Verifieer dat `postgres_engine` een worker-specifiek schema gebruikt (conftest doet dit al via `search_path`). Verwijder `_NonRefreshingSession` workaround zodra fixture-scope correct is. |
| **Actie** | Volgende sprint na SP-DSM-COMPLETE. |
| **Quarantinedatum** | 2026-06-13 (commit SP-DSM-COMPLETE Dag 4) |

## test_agent_blocks_tenant_isolation.py (startup timeout)

| Kolom | Waarde |
|-------|--------|
| **Reden** | `TestAgentBlocksEndpointsTenantIsolation` klasse gebruikt `async_client` fixture met volledige app-stack. `src.main` import kost 13.7s op Python 3.13/Windows (80+ zware modules). Op een fresh process overschrijdt dit de pytest-timeout. |
| **Root cause** | Niet torch specifiek -- de totale module-graph startup-tijd is te hoog voor een unit-test context. Integratie-tests horen in `tests/integration/`. |
| **Coverage gap** | Canvas agent block endpoint tenant isolation. De registry unit tests (`TestAgentBlockRegistryTenantFiltering`) waren in hetzelfde bestand -- die zijn ook gequarantined maar kunnen terug naar `tests/unit/canvas/` als losse file. |
| **Reactivatieplan** | Verplaats `TestAgentBlocksEndpointsTenantIsolation` naar `tests/integration/canvas/test_agent_blocks_isolation.py`. Registry tests kunnen direct terug. |
| **Actie** | Aparte sprint: `SP-CANVAS-INT-01` |

## test_import_performance.py (subprocess startup timer)

| Kolom | Waarde |
|-------|--------|
| **Reden** | Roept `subprocess.run()` aan om startuptijd en geheugengebruik te meten. Looptijd 13-24s per test (afhankelijk van systeemload). Incompatibel met de 60s-timeout in de unit-suite. |
| **Root cause** | Fundamenteel subprocess-gebaseerd -- niet te fixen zonder de test te herschrijven naar in-process meting. |
| **Coverage gap** | Startup performance regression detection. Geen direct coverage-verlies in logica. |
| **Reactivatieplan** | Verplaats naar `tests/performance/` met eigen CI-stap en `--timeout=120`. Of gebruik `tracemalloc` in-process. |
| **Actie** | Performance test infrastructure sprint. |
| **Quarantinedatum** | 2026-06-23 (perf: unit suite wall-clock reduction) |

## test_ethics_trainer_import.py (subprocess factory test)

| Kolom | Waarde |
|-------|--------|
| **Reden** | Roept `subprocess.run()` aan om een factory-instantiatie in een fresh process te testen. Looptijd 9-19s per test. Overschrijdt de 60s-timeout bij parallelle runs. |
| **Root cause** | Subprocess-gebaseerd om importisolatie te garanderen -- inherent traag. |
| **Coverage gap** | EthicsTrainer factory instantiation. De factory zelf is gedekt door andere unit tests. |
| **Reactivatieplan** | Herschrijf naar `importlib.import_module()` in-process met subprocess-isolatie via `sys.modules` reset, of verplaats naar `tests/integration/`. |
| **Actie** | EthicsTrainer import test refactor. |
| **Quarantinedatum** | 2026-06-23 (perf: unit suite wall-clock reduction) |
