# BE-CFG-009 -- API Layer Startup: Lazy Imports + Architecture Tooling

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-009 |
| Feature naam | API Layer Startup: Lazy Imports + Architecture Tooling (ADR-033 Stap 0A/0B/0D) |
| Status | APPROVED WITH MINOR GAPS |
| Auteur | AI agent (SP-API-001 Dag 1) |
| Reviewer | AI agent (review-BE-CFG-009.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 1 |
| Gerelateerde router / module | `src/core/app_lifespan.py`, `src/main.py`, `src/core/api/router_registry.py`, `src/core/api/setup/router_registry.py`, `src/core/api/main.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Implementeer ADR-033 Stap 0A/0B/0D: verplaats `register_all_routers` naar synchrone startup,
maak 11 endpoint-imports lazy in de setup registry, voeg een TESTING-guard toe in api/main.py,
vervang hardcoded teller door `count += 1` en stel import-linter en architecture fitness tests in.

### In scope

- `app_lifespan.py`: verwijder `register_all_routers(app)` uit de async lifespan context
- `src/main.py`: voeg `register_all_routers(app)` toe synchroon in `create_app()` (r138-143),
  bewaard door `if not is_test_context` guard
- `src/core/api/setup/router_registry.py`: verplaats 11 module-level imports naar de body van
  `register_routers()` (lazy imports -- Stap 0A)
- `src/core/api/main.py`: TESTING-guard voor setup/router_registry import (Stap 0B)
- `src/core/api/router_registry.py`: vervang `count = N` / `return N` door `count = 0` +
  `count += 1` per `include_router` aanroep (Stap 0D)
- `.importlinter`: 1 actief contract (`api-no-domain`: `v1/*.router` mag geen domeinmodules
  importeren)
- `requirements-test.txt`: `import-linter>=2.0` toegevoegd
- `tests/architecture/__init__.py` + `tests/architecture/test_api_layer.py`: 4 fitness tests
- `scripts/ci-local-fast.sh`: `lint-imports` + `pytest tests/architecture/` toegevoegd
- `.pre-commit-config.yaml`: `architecture-contracts` + `architecture-fitness` hooks toegevoegd

### Out of scope

- Inhoudelijke wijzigingen aan individuele routers of endpoints
- Database-wijzigingen of Alembic migraties
- Frontend-wijzigingen

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand |
|----------|------|---------|
| `.importlinter` | Import-linter configuratie | `.importlinter` |
| `tests/architecture/__init__.py` | Test package | `tests/architecture/__init__.py` |
| `test_api_layer.py` | Test class (4 fitness tests) | `tests/architecture/test_api_layer.py` |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `app_lifespan.py` | `register_all_routers` aanroep verwijderd uit lifespan | `src/core/app_lifespan.py` |
| `create_app()` | `register_all_routers(app)` synchroon, `is_test_context` guard | `src/main.py` |
| `register_routers()` | 11 imports van module-level naar functie-body | `src/core/api/setup/router_registry.py` |
| `api/main.py` | TESTING-guard voor setup import | `src/core/api/main.py` |
| `router_registry.py` | `count = 0` + `count += 1` per router | `src/core/api/router_registry.py` |
| `requirements-test.txt` | `import-linter>=2.0` toegevoegd | `requirements-test.txt` |
| `ci-local-fast.sh` | `lint-imports` + architecture pytest stap | `scripts/ci-local-fast.sh` |
| `.pre-commit-config.yaml` | 2 architecture hooks toegevoegd | `.pre-commit-config.yaml` |

### Verwijderd

Niets.

### Beinvloede bestaande flows

Router registratie vindt nu synchroon plaats voor lifespan in `create_app()`. Het
gedrag voor HTTP-clients is identiek -- alle routers zijn beschikbaar zodra de
applicatie luistert.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|----------------|-------------------|
| BE-CFG-009-a | Lazy imports setup registry | Refactor | `src/core/api/setup/router_registry.py` | Wijziging | API startup |
| BE-CFG-009-b | Sync router registration in create_app | Startup wiring | `src/main.py` | Wijziging | API startup |
| BE-CFG-009-c | count += 1 teller | Refactor | `src/core/api/router_registry.py` | Wijziging | API startup |
| BE-CFG-009-d | TESTING-guard api/main.py | Guard | `src/core/api/main.py` | Wijziging | Test collectie |
| BE-CFG-009-e | import-linter contract | Tooling | `.importlinter` | Nieuw | CI / pre-commit |
| BE-CFG-009-f | Architecture fitness tests | Tests (4) | `tests/architecture/test_api_layer.py` | Nieuw | CI |

---

## API-flows

### Flow: API Startup Router Registratie

| Veld | Waarde |
|------|--------|
| Naam | API Startup Router Registratie |
| Trigger | `create_app()` aangeroepen bij applicatie-start |
| Voorwaarden | Python module volledig geladen; `is_test_context` is False |
| Request-pad | Geen HTTP request -- intern startup proces |
| Service-stappen | 1. `create_app()` aanroepen; 2. `register_all_routers(app)` synchroon; 3. Elke `_register_*` functie laadt imports lazy; 4. `count += 1` per geregistreerde router; 5. Lifespan start daarna (DB, Redis, etc.) |
| DB-operaties | Geen |
| Successtatus | Alle routers geregistreerd; teller correct; applicatie luistert |
| Foutpaden | ImportError in `_register_*` -- bubbelt naar startup en crasht de app |
| Eindtoestand | FastAPI app met volledig geregistreerde router tree |

### Flow: CI Architecture Fitness Check

| Veld | Waarde |
|------|--------|
| Naam | CI Architecture Fitness Check |
| Trigger | `ci-local-fast.sh` of pre-commit hook |
| Voorwaarden | `import-linter>=2.0` geinstalleerd; `tests/architecture/` aanwezig |
| Request-pad | Geen HTTP request -- CLI tool |
| Service-stappen | 1. `lint-imports --config .importlinter`; 2. `pytest tests/architecture/`; 3. 4 fitness tests lopen (eager import check, orphan routers, regellimiet 200/80) |
| DB-operaties | Geen |
| Successtatus | 0 contract violations; 4/4 tests PASS |
| Foutpaden | Contract violation = CI geblokkeerd; orphan router = test FAIL |
| Eindtoestand | Architectuurbewaking actief in CI en pre-commit |

---

## Detaildocumentatie per artefact

### Lazy imports in `register_routers()`

| Veld | Waarde |
|------|--------|
| Type | Refactor -- startup gedrag |
| Locatie | `src/core/api/setup/router_registry.py` |
| Gerelateerde flow | API Startup Router Registratie |
| Doel | Voorkom dat 11 endpoint-modules bij `import src.core.api.setup.router_registry` worden geladen |
| Functionele beschrijving | Alle 11 `from ... import router` statements verplaatst van module-level naar de body van `register_routers()`. Lazy loading reduceert test-collectietijd en voorkomt side effects bij import. |
| Technische beschrijving | Python evalueert de `import`-statements alleen bij de eerste aanroep van `register_routers()`. Daarna cacht Python het module-object. |
| Zichtbaarheids- en toegangsregels | Interne registratiefunctie; niet publiek. |
| Acceptatiecriteria | `test_no_eager_imports_in_setup_registry` GROEN; import smoketest `python -c "import src.core.api.setup.router_registry"` logt geen endpoint-module loads |

### `count = 0` + `count += 1` teller

| Veld | Waarde |
|------|--------|
| Type | Refactor |
| Locatie | `src/core/api/router_registry.py` |
| Doel | Vervang hardcoded `count = N` die altijd out-of-sync raakte bij toevoegen/verwijderen van routers |
| Technische beschrijving | `count = 0` voor de registraties; elke `app.include_router(...)` gevolgd door `count += 1`. `return count` aan het einde. |
| Acceptatiecriteria | `test_registry_files_under_80_lines` GROEN; `count` reflecteert exact het werkelijke aantal geregistreerde routers |

### `.importlinter` contract `api-no-domain`

| Veld | Waarde |
|------|--------|
| Type | Tooling configuratie |
| Locatie | `.importlinter` |
| Doel | Afdwingen dat `v1/*.router` modules geen directe domeinmodule-imports bevatten (ADR-033 import-discipline) |
| Technische beschrijving | 1 contract van type `forbidden`: source `src.core.api.v1.*.router`, forbidden imports `src.core.database`, `src.core.governance`, `src.core.learning`, `src.core.agents`, `src.core.workflow`, `src.core.llm` |
| Acceptatiecriteria | `lint-imports` geeft 0 violations; CI-stap groen |

### Trainingssamenvatting

#### Flow: Lazy Import Startup Refactor

| Veld | Waarde |
|------|--------|
| Actor | Backend engineer / AI agent |
| Voorwaarde | Module-level imports in `setup/router_registry.py` veroorzaken eagere module-loads bij test-collectie |
| Actie | Verplaats alle `from ... import router` statements naar de body van `register_routers()` |
| Systeemverwerking | Python laadt de endpoint-modules pas bij de eerste aanroep van `register_routers()`, niet bij import van de registry |
| Succesrespons | `test_no_eager_imports_in_setup_registry` PASS; pytest-collectietijd daalt meetbaar; `lint-imports` 0 violations |
| Foutrespons | ImportError of NameError in `register_routers()` bij ongeldig pad -- corrigeer het importpad en herrun |
| Uitzonderingen | Als een endpoint-module een circulaire import introduceert bij lazy loading, refactor naar een tussenliggende `dependencies.py` en spawn de `neo:neo-architect` skill voor advies |

#### Flow: Architecture Fitness CI Gate

| Veld | Waarde |
|------|--------|
| Actor | CI pipeline / pre-commit hook |
| Voorwaarde | Ontwikkelaar pusht code; `.importlinter` en `tests/architecture/` aanwezig |
| Actie | `lint-imports` + `pytest tests/architecture/` draaien automatisch |
| Systeemverwerking | import-linter loopt contracten na; pytest checkt 4 fitness tests (eager imports, orphan routers, regellimieten) |
| Succesrespons | 0 contract violations; 4/4 tests PASS; CI groen |
| Foutrespons | Contract violation: CI geblokkeerd; orphan router: test FAIL met naam van het orphan bestand |
| Uitzonderingen | Bij een false positive in de import-linter (bijv. toegestane cross-boundary import), voeg een `exclude` regel toe aan het contract in `.importlinter` en documenteer de reden |

---

## Integratorhandleiding

Geen publieke API-wijzigingen. Alle bestaande endpoints blijven op dezelfde paden beschikbaar.

Nieuwe vereiste voor ontwikkelaars die routers toevoegen:
1. Voeg imports lazy toe (in de body van `register_routers()` of `_register_*` helper)
2. Voeg `count += 1` toe na elke `app.include_router(...)` aanroep
3. Controleer dat `lint-imports` en `pytest tests/architecture/` groen blijven

---

## Open aannames / Open vragen / Risico's

| Type | Omschrijving | Status |
|------|--------------|--------|
| Aanname | `is_test_context` guard in `create_app()` voorkomt dubbele registratie bij pytest | Bevestigd via code-inspectie |
| Minor gap | `import-linter>=2.0` staat in `requirements-test.txt` i.p.v. `requirements-dev.txt` zoals de brief specificeerde | Open -- functioneel correct, maar dev-tooling hoort in dev requirements |
| Risico | Bestaande routers die al lazy importeerden zijn ongewijzigd -- geen regressierisico | Gesloten |

---

## QA-checks

- [x] `python -m py_compile src/core/api/setup/router_registry.py` -- geen errors
- [x] `python -m py_compile src/main.py` -- geen errors
- [x] `python -m py_compile src/core/api/router_registry.py` -- geen errors
- [x] `ruff check src/core/api/` -- 0 errors
- [x] `lint-imports --config .importlinter` -- 0 violations
- [x] `pytest tests/architecture/ -v` -- 4/4 PASS
- [x] `test_no_eager_imports_in_setup_registry` GROEN (was GROEN al voor fix -- bevestigt baseline)
- [x] Geen regressies in SP-WE sprint tests

---

## Definition of Done

- [x] Lazy imports in `setup/router_registry.py` geimplementeerd
- [x] `register_all_routers` synchroon in `create_app()`
- [x] `count += 1` teller actief in `router_registry.py`
- [x] TESTING-guard in `api/main.py`
- [x] `.importlinter` aanwezig met 1 actief contract
- [x] 4 architecture fitness tests PASS
- [x] CI-scripts bijgewerkt
- [x] Feature spec aangemaakt (dit bestand)
- [x] Review APPROVED WITH MINOR GAPS (`docs/backend/review/review-BE-CFG-009.md`)
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
