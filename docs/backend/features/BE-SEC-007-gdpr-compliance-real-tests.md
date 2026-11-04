# Backend Feature Specification

## Metadata

- Feature ID: BE-SEC-007
- Feature naam: Echte GDPR Compliance Tests (SOC 2 Bewijs)
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review (reviewer-prompt toegepast)
- Datum: 2026-05-30
- Gerelateerde user story / ticket: B-020 (MASTER-AUDIT-COMPLEET.md)
- Gerelateerde router / module: tests/compliance/
- Gerelateerde frontend endpoints: Geen (backend test-only sprint)
- Gerelateerde database tabellen: user_twin_consent, users, audit_logs, user_behavior_observation, user_cognitive_profile, twin_suggestion_log, c7_workflow, agents, conversations
- Versie: 1.0

---

## Doel en scope

### Doel

Vervang mock-only GDPR compliance tests door echte async integratietests die productie-services (`TwinConsentManager`, `GDPREnforcer`, `DSARService`) aanroepen met een echte PostgreSQL database. Dit levert audit-bewijs voor SOC 2 CC6/CC7 privacy-controles dat valideerbaar is door externe auditors.

### In scope

1. Volledige rewrite van `tests/compliance/test_gdpr_compliance.py` (473 regels dict-only -> 10 echte async integratietests)
2. Aanmaken `tests/compliance/conftest.py` voor fixture-hergebruik
3. Aanmaken `tests/unit/test_sp_h08_compliance_test_quality.py` (AST-based quality gate)
4. Toevoegen `import src.core.learning.twin_models` aan `tests/integration/conftest.py`
5. Docstring-correctie `src/core/learning/consent/consent_manager.py` (opt-out -> opt-in)

### Out of scope

- Nieuwe API-endpoints, services of ORM-modellen bouwen
- Nieuwe Alembic-migraties
- Frontend-wijzigingen
- Nieuwe GDPR-functionaliteit in productiecode

---

## Build summary

- **Nieuw gebouwd:**
  - `tests/compliance/conftest.py` -- pytest_plugins bridge naar integratie fixtures
  - `tests/unit/test_sp_h08_compliance_test_quality.py` -- AST-based quality gate
- **Gewijzigd:**
  - `tests/compliance/test_gdpr_compliance.py` -- volledige rewrite (mock -> echte services)
  - `tests/integration/conftest.py` -- twin_models import toegevoegd voor schema setup
  - `src/core/learning/consent/consent_manager.py` -- docstring consistentie fix
- **Verwijderd:** Geen (oud bestand inhoudelijk volledig vervangen)
- **Beinvloede bestaande flows:**
  - CI compliance test suite run
  - SOC 2 Type I audit trail bewijs-verzameling
  - Integration test schema setup (twin tabellen nu correct geregistreerd)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-SEC-007a | GDPR Compliance Test Suite | Test suite | `tests/compliance/test_gdpr_compliance.py` | Wijziging | GDPR compliance verification |
| BE-SEC-007b | Compliance Conftest Bridge | Test fixture bridge | `tests/compliance/conftest.py` | Nieuw | GDPR compliance verification |
| BE-SEC-007c | Compliance Test Quality Gate | Test validator | `tests/unit/test_sp_h08_compliance_test_quality.py` | Nieuw | Quality assurance |
| BE-SEC-007d | Twin Models Schema Import | Test fixture patch | `tests/integration/conftest.py` | Wijziging | Integration test schema setup |
| BE-SEC-007e | TwinConsentManager Docstring Fix | Documentatie correctie | `src/core/learning/consent/consent_manager.py` | Wijziging | Consent management |

---

## API-flows

### Flow ID: BE-FLW-007a -- GDPR Compliance Test Execution

Deze flow beschrijft de uitvoering van de compliance test suite, niet een productie-API-flow. De tests valideren bestaande productie-services.

- **Naam:** GDPR Compliance Test Suite Execution
- **Trigger (HTTP-methode + route of event):** `pytest tests/compliance/test_gdpr_compliance.py -v`
- **Voorwaarden (auth, tenant, feature flag):**
  - PostgreSQL testdatabase beschikbaar op poort 5435 of 5455
  - Database schema geinitialiseerd via `tests/integration/conftest.py` session-scoped fixture
  - `app.current_tenant` session variabele gezet via TenantMiddleware equivalent in test setup
- **Request-pad:** N.v.t. (test suite, geen HTTP request)
- **Service-stappen:**
  1. Test framework laadt `tests/compliance/conftest.py` (pytest_plugins bridge)
  2. `postgres_session` fixture maakt function-scoped async session aan
  3. Per test: service instantie gemaakt met `db=postgres_session`
  4. Service voert DB-operaties uit (SELECT, INSERT, UPDATE, DELETE)
  5. Test assertions valideren service-output
  6. Fixture rollback verwijdert test-mutaties
- **DB-operaties:**
  - `user_twin_consent`: INSERT (nieuwe consent records), UPDATE (status wijzigingen)
  - `users`: SELECT (tenant isolatie verificatie), UPDATE (soft delete flags)
  - `audit_logs`: SELECT (Art. 15 access trail)
  - `user_behavior_observation`: DELETE (Art. 17 hard delete)
  - `user_cognitive_profile`: DELETE (Art. 17 hard delete)
  - `twin_suggestion_log`: DELETE (Art. 17 hard delete)
- **Successtatus + response:** 10 passed in ~9s
- **Foutpaden:**
  - PostgreSQL niet bereikbaar -> pytest skip (allow_module_level)
  - Ontbrekende twin tabellen -> `relation "user_twin_consent" does not exist`
  - Service-bug -> assertion failure met stacktrace
- **Eindtoestand (DB, cache, events):**
  - DB: geen persistente wijzigingen (transaction rollback per test)
  - Cache: geen (Redis niet gebruikt in tests)
  - Events: geen (event bus niet actief in test context)

---

## Detaildocumentatie per artefact

---

## [BE-SEC-007a] GDPR Compliance Test Suite

### 1. Type

Test suite / Integratietests

### 2. Locatie

- Bestandspad: `tests/compliance/test_gdpr_compliance.py`
- Klasse / functie: `TestConsentManagement`, `TestPIIDetection`, `TestDSARAccessAndErasure`

### 3. Gerelateerde flow

BE-FLW-007a -- GDPR Compliance Test Execution

### 4. Doel

Valideer dat productie-GDPR-services correct functioneren door ze aan te roepen met echte database-sessies in plaats van mock-dictionaries.

### 5. Functionele beschrijving

De test suite verifieert zes GDPR-artikelen via tien individuele tests:

- **Art. 7 (Consent):** Nieuwe users hebben default disabled consent. Opt-in maakt tracking actief. Opt-out stopt tracking onmiddellijk.
- **Art. 5 (Data Minimization):** PII-detectie herkent email-patronen in payloads.
- **Art. 15 (Right of Access):** DSAR-export bevat audit trail data.
- **Art. 17 (Right to Erasure):** Soft delete markeert user inactive met grace period. Hard delete vereist admin. Twin erasure request zet vlag.
- **Art. 20 (Data Portability):** DSAR-export retourneert user data in gestructureerd format.
- **Art. 32 (Security):** Cross-tenant DSAR-export wordt afgewezen.

### 6. Technische beschrijving

- **Module-level pytestmark:** `[pytest.mark.asyncio, pytest.mark.integration]` zodat elke test async uitgevoerd wordt en als integratietest gemarkeerd is.
- **Fixture dependency:** `postgres_session` uit `tests/integration/conftest.py` (geladen via `pytest_plugins` bridge).
- **Test pattern:** Arrange-Act-Assert per testfunctie. Services worden direct geinstantieerd met de test-session:
  ```python
  mgr = TwinConsentManager(db=postgres_session)
  status = await mgr.get_consent_status(user_id="...", tenant_id=1)
  ```
- **Transaction isolatie:** `join_transaction_mode="create_savepoint"` in fixture zorgt dat `session.commit()` binnen services omgezet wordt naar savepoint-releases. Outer transaction rollback na elke test garandeert schone staat.
- **Synthetische testdata:** User IDs volgen pattern `gdpr-test-user-###` om conflicten met seeded data te vermijden.

### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** Geen (test-only, geen HTTP endpoint)
- **Vereiste rol / scope:** Geen
- **Tenant-isolatie:** Verplicit aanwezig in elke service-aanroep via `tenant_id=1` parameter. Cross-tenant test (T-010) bewijst dat isolatie werkt.
- **Feature flag:** Geen

### 8. Request-specificatie

N.v.t. -- Deze artefact is een test suite, geen API-endpoint.

### 9. Response-specificatie

N.v.t. -- Deze artefact is een test suite.
Test output bij succes:
```
tests/compliance/test_gdpr_compliance.py::TestConsentManagement::test_consent_create_defaults_to_disabled PASSED
tests/compliance/test_gdpr_compliance.py::TestConsentManagement::test_consent_enable_and_check PASSED
tests/compliance/test_gdpr_compliance.py::TestConsentManagement::test_consent_revoke_clears_tracking PASSED
tests/compliance/test_gdpr_compliance.py::TestConsentManagement::test_twin_request_hard_delete_sets_flag PASSED
tests/compliance/test_gdpr_compliance.py::TestPIIDetection::test_pii_detection_finds_email PASSED
tests/compliance/test_gdpr_compliance.py::TestDSARAccessAndErasure::test_dsar_export_returns_user_data PASSED
tests/compliance/test_gdpr_compliance.py::TestDSARAccessAndErasure::test_dsar_export_includes_audit_trail PASSED
tests/compliance/test_gdpr_compliance.py::TestDSARAccessAndErasure::test_dsar_soft_delete_marks_inactive PASSED
tests/compliance/test_gdpr_compliance.py::TestDSARAccessAndErasure::test_dsar_hard_delete_rejects_non_admin PASSED
tests/compliance/test_gdpr_compliance.py::TestDSARAccessAndErasure::test_dsar_export_rejects_cross_tenant PASSED
```

### 10. Validaties en constraints

- `TwinConsentManager` vereist `AsyncSession` (geen sync session)
- `DSARService` vereist bestaande user in `users` tabel (seeded via conftest)
- `GDPREnforcer.detect_pii()` werkt sync en vereist geen DB
- Alle async tests moeten `@pytest.mark.asyncio` dragen (via module-level pytestmark)

### 11. Business rules

- BR-001: Nieuw consent record heeft status `disabled` (GDPR Art. 7 opt-in vereist)
- BR-002: Expliciete opt-in (`ENABLED`) activeert alle vier tracking-categorieën
- BR-003: Opt-out (`DISABLED`) deactiveert alle tracking-categorieën
- BR-004: DSAR soft delete zet `is_active=False`, `deleted_at=timestamp`, `deletion_scheduled_for=timestamp+30d`
- BR-005: DSAR hard delete vereist `is_admin=True`
- BR-006: Cross-tenant data access wordt altijd afgewezen (`DSARTenantIsolationError`)

### 12. Afhankelijkheden

- `tests/integration/conftest.py` (session-scoped schema + function-scoped session)
- `src.core.learning.consent.consent_manager.TwinConsentManager`
- `src.core.governance.gdpr_enforcer.GDPREnforcer`
- `src.core.governance.dsar_service.DSARService`
- `src.core.models.rbac_models.User` (voor soft delete verificatie)

### 13. Foutafhandeling

De tests valideren dat services correcte exceptions raisen:

- `DSARTenantIsolationError`: User niet gevonden in opgegeven tenant (T-010)
- `DSARAuthorizationError`: Non-admin probeert hard delete (T-008)
- `AssertionError`: Test faalt als service-gedrag afwijkt van verwachting

### 14. Transacties en data-integriteit

- Primaire test-data wordt geflusht binnen `postgres_session` savepoint.
- `TwinConsentManager.set_consent_status()` doet `await self._db.flush()` (geen commit).
- `DSARService.delete_user_data()` doet `await self._db.commit()` in soft-delete pad -- dit wordt door SQLAlchemy savepoint-mode omgezet naar `RELEASE SAVEPOINT`.
- Outer transaction rollback in fixture garandeert dat alle mutaties na de test ongedaan zijn.

### 15. Telemetry / logging / tracing

- `TwinConsentManager` logt via `loguru` naar `logger.info()` bij consent-wijzigingen.
- `DSARService._create_audit_log()` schrijft `AuditLog` entries via `best_effort` wrapper.
- Test output wordt opgeslagen in `logs/test_report.json` (pytest-json-report plugin).

### 16. Caching

- Niet van toepassing in test context.
- Productie: `TwinConsentManager` gebruikt Redis cache (TTL=300s) maar test-fixture heeft geen Redis verbinding.

### 17. Acceptatiecriteria

- [ ] 10/10 compliance tests PASS tegen echte PostgreSQL database
- [ ] Quality gate (AST-based) slaagt en bevestigt >=5 async tests
- [ ] Geen mock-only assertions in compliance suite
- [ ] Tenant isolatie correct getest (cross-tenant export faalt)
- [ ] Docstring consistent met implementatie (`default=disabled`)
- [ ] Integratie conftest laadt twin_models correct
- [ ] Geen regressies in bestaande test suites

### 18. Integratoruitleg

- Voer compliance tests uit met: `pytest tests/compliance/test_gdpr_compliance.py -v`
- Vereist PostgreSQL op poort 5435 of 5455 (Docker: `make test-db-up`)
- Tests zijn idempotent dankzij transaction rollback -- veilig om meerdere keren te draaien
- Quality gate draaien: `pytest tests/unit/test_sp_h08_compliance_test_quality.py -v`

### 19. Trainingssamenvatting

- **Actor:** Compliance auditor / SOC 2 assessor / CI-pipeline
- **Voorwaarde:** PostgreSQL testdatabase draait; schema geinitialiseerd; tenant_id=1 geseed
- **Actie (request):** `pytest tests/compliance/test_gdpr_compliance.py -v`
- **Systeemverwerking:** 10 async integratietests instantieren productie-services met echte DB-sessie; services voeren SELECT/INSERT/UPDATE/DELETE uit; assertions valideren GDPR-compliant gedrag
- **Succesrespons:** 10 passed in ~9s
- **Foutrespons:** FAIL bij ontbrekende DB, of assertion failure bij service-bug
- **Uitzonderingen:** `DSARTenantIsolationError` bij cross-tenant export; `DSARAuthorizationError` bij non-admin hard delete

---

## [BE-SEC-007b] Compliance Conftest Bridge

### 1. Type

Test fixture bridge

### 2. Locatie

- Bestandspad: `tests/compliance/conftest.py`
- Klasse / functie: `pytest_plugins`

### 3. Gerelateerde flow

BE-FLW-007a

### 4. Doel

Maak integratie test fixtures (zoals `postgres_session`) beschikbaar in `tests/compliance/` zonder duplicatie.

### 5. Functionele beschrijving

Laadt `tests.integration.conftest` als pytest plugin zodat alle fixtures (schema setup, DB engine, sessions, auth tokens) automatisch beschikbaar zijn voor compliance tests.

### 6. Technische beschrijving

```python
pytest_plugins = ["tests.integration.conftest"]
```

Dit importeert alle fixtures uit de integratie conftest, inclusief:
- `setup_database_schema` (session-scoped schema drop/create)
- `setup_rls_policies` (session-scoped RLS)
- `postgres_session` (function-scoped session + rollback)
- `admin_token`, `normal_user_token`

### 7. Zichtbaarheids- en toegangsregels

- Alleen relevant binnen pytest test runner.
- Module-level `pytest.skip` in `tests/integration/conftest.py` kan de hele compliance suite overslaan als PostgreSQL niet draait.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `tests/integration/conftest.py` moet bestaan en correcte fixtures bevatten.

### 11. Business rules

- Geen.

### 12. Afhankelijkheden

- `tests/integration/conftest.py`

### 13. Foutafhandeling

- Als PostgreSQL niet draait: `pytest.skip("PostgreSQL test database not available...", allow_module_level=True)`

### 14. Transacties en data-integriteit

- Geen directe transacties; delegeert naar integratie fixtures.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] `pytest tests/compliance/` kan collecteren zonder fixture-import errors
- [ ] `postgres_session` is beschikbaar in compliance tests

### 18. Integratoruitleg

- Deze bridge voorkomt fixture-duplicatie tussen `tests/integration/` en `tests/compliance/`.
- Wijzigingen aan integratie fixtures worden automatisch overgenomen in compliance tests.

### 19. Trainingssamenvatting

- **Actor:** Test engineer
- **Voorwaarde:** Integratie conftest bestaat met geldige fixtures
- **Actie:** Plaats `pytest_plugins = ["tests.integration.conftest"]` in `tests/compliance/conftest.py`
- **Systeemverwerking:** Pytest laadt alle integratie fixtures als lokale fixtures
- **Succesrespons:** Compliance tests kunnen `postgres_session` en andere fixtures gebruiken
- **Foutrespons:** `pytest.skip` als PostgreSQL ontbreekt
- **Uitzonderingen:** Geen

---

## [BE-SEC-007c] Compliance Test Quality Gate

### 1. Type

Test validator / Unit test

### 2. Locatie

- Bestandspad: `tests/unit/test_sp_h08_compliance_test_quality.py`
- Klasse / functie: `TestComplianceTestQuality`

### 3. Gerelateerde flow

Quality assurance gate voor compliance tests.

### 4. Doel

Voorkom regressie naar mock-only tests door AST-gebaseerde verificatie dat compliance tests echte service-calls bevatten.

### 5. Functionele beschrijving

De quality gate parsed `tests/compliance/test_gdpr_compliance.py` als AST en controleert:
1. Bevat `ast.Call` nodes met `TwinConsentManager`, `GDPREnforcer`, of `DSARService`
2. Bevat minstens 5 `ast.AsyncFunctionDef` test-functies

### 6. Technische beschrijving

```python
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in ("TwinConsentManager", "GDPREnforcer", "DSARService"):
            has_real_calls = True
            break
```

Voorheen gebruikte substring matching (`"TwinConsentManager" in source`) die gamebaar was via comments. AST Call-node detectie is robuuster.

### 7. Zichtbaarheids- en toegangsregels

- Alleen relevant in unit test context (geen DB nodig).

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.
Succes: 2 passed
Falen: AssertionError met message "Compliance tests zijn nog steeds mock-assertions..."

### 10. Validaties en constraints

- Bestand `tests/compliance/test_gdpr_compliance.py` moet bestaan.
- AST moet parsebaar zijn (geldige Python syntax).

### 11. Business rules

- BR-QG-001: Compliance tests moeten minstens 5 async test-functies bevatten.
- BR-QG-002: Compliance tests moeten minstens één `Call` node hebben naar `TwinConsentManager`, `GDPREnforcer`, of `DSARService`.

### 12. Afhankelijkheden

- `pathlib.Path`
- `ast` (standaard library)

### 13. Foutafhandeling

- `AssertionError` bij falen van een van de twee checks.

### 14. Transacties en data-integriteit

- Geen DB-interactie.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] Quality gate slaagt na build
- [ ] Quality gate faalt als compliance tests geen echte service-calls bevatten

### 18. Integratoruitleg

- Draai met: `pytest tests/unit/test_sp_h08_compliance_test_quality.py -v`
- Deze gate is TDD-proof: schrijf de gate eerst, dan pas de compliance tests.

### 19. Trainingssamenvatting

- **Actor:** CI-pipeline / ontwikkelaar
- **Voorwaarde:** `tests/compliance/test_gdpr_compliance.py` bestaat
- **Actie:** `pytest tests/unit/test_sp_h08_compliance_test_quality.py -v`
- **Systeemverwerking:** Leest compliance test broncode, parsed AST, zoekt Call nodes en AsyncFunctionDef nodes
- **Succesrespons:** 2 passed
- **Foutrespons:** AssertionError met specifieke failure reason
- **Uitzonderingen:** SyntaxError als compliance test bestand ongeldige Python bevat

---

## [BE-SEC-007d] Twin Models Schema Import

### 1. Type

Test fixture patch

### 2. Locatie

- Bestandspad: `tests/integration/conftest.py` (regel ~165)
- Klasse / functie: Module-level import

### 3. Gerelateerde flow

Integration test schema setup

### 4. Doel

Zorg dat `user_twin_consent`, `user_behavior_observation`, `user_cognitive_profile` en `twin_suggestion_log` tabellen aangemaakt worden tijdens session-scoped schema setup.

### 5. Functionele beschrijving

`Base.metadata.create_all()` creëert alleen tabellen van modellen die geregistreerd zijn in SQLAlchemy `Base`. Zonder expliciete import worden twin-modellen niet geregistreerd en ontbreken de tabellen in de test database.

### 6. Technische beschrijving

```python
import src.core.learning.models
import src.core.learning.twin_models  # <-- toegevoegd
```

Dit forceert het uitvoeren van `twin_models.py` module-level code, waardoor `UserTwinConsent`, `UserBehaviorObservation`, `UserCognitiveProfile` en `TwinSuggestionLog` geregistreerd worden in `Base.metadata`.

### 7. Zichtbaarheids- en toegangsregels

- Alleen relevant tijdens test schema setup.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `src.core.learning.twin_models` moet bestaan en geldige SQLAlchemy models bevatten.

### 11. Business rules

- Geen.

### 12. Afhankelijkheden

- `src.core.learning.twin_models`

### 13. Foutafhandeling

- `ModuleNotFoundError` als twin_models verplaatst wordt.

### 14. Transacties en data-integriteit

- Geen directe transacties; delegeert naar schema setup fixture.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] `user_twin_consent` tabel bestaat na schema setup
- [ ] `user_behavior_observation` tabel bestaat na schema setup
- [ ] `user_cognitive_profile` tabel bestaat na schema setup

### 18. Integratoruitleg

- Wanneer nieuwe ORM-modellen toegevoegd worden die niet via bestaande import-paden bereikbaar zijn, voeg een expliciete import toe aan `tests/integration/conftest.py`.

### 19. Trainingssamenvatting

- **Actor:** Test engineer
- **Voorwaarde:** Nieuwe ORM-modellen toegevoegd
- **Actie:** Voeg `import src.core.learning.twin_models` toe aan conftest
- **Systeemverwerking:** Module-uitvoering registreert modellen in SQLAlchemy Base.metadata
- **Succesrespons:** Tabellen aangemaakt tijdens schema setup
- **Foutrespons:** `relation "user_twin_consent" does not exist`
- **Uitzonderingen:** Geen

---

## [BE-SEC-007e] TwinConsentManager Docstring Fix

### 1. Type

Documentatie correctie

### 2. Locatie

- Bestandspad: `src/core/learning/consent/consent_manager.py`
- Klasse / functie: Module-level docstring (regel 5) + `get_consent_status()` docstring (regel 82)

### 3. Gerelateerde flow

Consent management

### 4. Doel

Corrigeer inconsistentie tussen docstring en werkelijke implementatie om verwarring bij toekomstige ontwikkelaars en auditors te voorkomen.

### 5. Functionele beschrijving

De docstring beweerde "opt-out model, default=enabled" maar de code implementeert "opt-in model, default=disabled" (alle boolean velden `False`, status `"disabled"`). Dit is correct voor GDPR Art. 7 maar de docstring was misleidend.

### 6. Technische beschrijving

Wijzigingen:
- Regel 5: `"opt-out model, default=enabled"` -> `"opt-in model, default=disabled"`
- Regel 82: `"Default: ENABLED (opt-out model)."` -> `"Default: DISABLED (opt-in model)."`

### 7. Zichtbaarheids- en toegangsregels

- Documentatie-only wijziging; geen gedragsverandering.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- Geen.

### 11. Business rules

- Geen wijziging in business rules.

### 12. Afhankelijkheden

- Geen.

### 13. Foutafhandeling

- Geen.

### 14. Transacties en data-integriteit

- Geen.

### 15. Telemetry / logging / tracing

- Geen.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] Docstring beschrijft `opt-in model, default=disabled`
- [ ] Docstring consistent met `_get_or_create_consent()` implementatie

### 18. Integratoruitleg

- Geen actie vereist voor integrators. Interne codekwaliteit fix.

### 19. Trainingssamenvatting

- **Actor:** AI agent / ontwikkelaar
- **Voorwaarde:** Docstring inconsistent met implementatie gedetecteerd
- **Actie:** Update docstring naar correcte beschrijving
- **Systeemverwerking:** Broncode documentatie bijgewerkt
- **Succesrespons:** Docstring consistent met code
- **Foutrespons:** N.v.t.
- **Uitzonderingen:** Geen

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Deze feature levert geen nieuwe API-endpoints. Het is een test-infrastructuur sprint die bestaande GDPR-services valideert.

- **Om compliance tests te draaien:**
  ```bash
  # Start PostgreSQL testdatabase
  make test-db-up

  # Draai compliance suite
  pytest tests/compliance/test_gdpr_compliance.py -v

  # Draai quality gate
  pytest tests/unit/test_sp_h08_compliance_test_quality.py -v
  ```
- **Verwachte resultaten:** 10 passed (compliance) + 2 passed (quality gate)
- **Afhangelijkheden:** PostgreSQL op poort 5435 of 5455
- **CI-integratie:** Deze tests draaien automatisch in de CI-pipeline bij wijzigingen aan GDPR-gerelateerde code.

---

## Open aannames

- De seeded integratie users (id=1 admin, id=2 normal user) blijven bestaan in `tests/integration/conftest.py`.
- PostgreSQL testdatabase op poort 5435/5455 blijft beschikbaar.
- `DSARService` interne structuur (9 data-categorieën in export) blijft stabiel.

## Open vragen

- Moeten Art. 16 (Right to Rectification) en Art. 18 (Right to Restriction) ook dedicated compliance tests krijgen? (Niet in scope van deze sprint.)
- Moet de quality gate ook verifiëren dat tests `assert` statements bevatten (niet lege async functies)?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Compliance tests draaien niet zonder PostgreSQL | Medium | Hoog | CI heeft PostgreSQL service container; lokale dev kan `make test-db-up` gebruiken |
| `best_effort` audit logs blijven staan tussen tests | Low | Medium | Audit logs hebben geen unieke constraints; geen test-interferentie |
| Toekomstige service-wijziging breekt compliance tests | Medium | Medium | Quality gate detecteert regressie; tests draaien in CI bij elke PR |

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) -- N.v.t. (geen nieuwe endpoints)
- [x] Alle foutstatus-codes getest -- Via service exceptions (DSARTenantIsolationError, DSARAuthorizationError)
- [x] Auth en permissies getest -- T-008 (hard delete admin check)
- [x] Tenant-isolatie getest -- T-010 (cross-tenant rejection)
- [x] Validaties getest (ongeldige invoer) -- Via service-validatie in tests
- [x] Edge cases getest (leeg, null, grenzen) -- Nieuwe user zonder consent record
- [x] Data-integriteit en transacties getest -- Fixture rollback + savepoint-mode
- [ ] Performance / load getest (indien relevant) -- Niet in scope
- [ ] Caching getest (indien van toepassing) -- Niet in scope (Redis niet actief in tests)
- [x] Logging en tracing gecontroleerd -- Audit trail aanwezig in DSARService

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
