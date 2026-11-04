# BE-CFG-013 -- router_registry.py Dead Code Removal -- Strangler Fig Voltooiing

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-013 |
| Feature naam | router_registry.py Dead Code Removal -- Strangler Fig Voltooiing |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 5) |
| Reviewer | AI agent (review-BE-CFG-013.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 5 |
| Gerelateerde router / module | `src/core/api/router_registry.py`, `tests/architecture/test_registry_equivalence.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Verwijder de 23 dode `_register_*` hulpfuncties en 2 dode helpers uit `router_registry.py` die
zijn vervangen door de Laag 2 domeinregistries (Dag 1-4). Dit is de finale stap van de
Strangler Fig migratie (ADR-033): het bestand krimpt van ~1100 naar ~320 regels en functioneert
nu als een dunne orkestrator die uitsluitend delegeert naar domeinregistries. De 12
equivalentietests in `tests/architecture/` fungeerden als vangnet en bevestigen dat geen router
verloren is gegaan.

### In scope

- Verwijdering van 23 dode `_register_*` functies uit `router_registry.py`
- Verwijdering van 2 dode helpers die exclusief door de verwijderde functies werden gebruikt
- `_register_optional_routers` behouden (nog actief als directe registratie)
- `_register_scheduling` behouden (nog actief als directe registratie)
- 12 AST-equivalentietests als vangnet gedraaid -- alle 12 GROEN

### Out of scope

- Inhoudelijke routewijzigingen of nieuwe endpoints
- Wijzigingen aan de Laag 2 domeinregistries (Dag 1-4)
- Nieuwe architectuurpatronen buiten ADR-033

---

## Build summary

### Nieuw gebouwd

Geen nieuwe artefacten -- dit is een pure verwijderingssprint.

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `router_registry.py` | 23 dode `_register_*` functies + 2 dode helpers verwijderd; ~1100 -> ~320 regels | `src/core/api/router_registry.py` |

### Verwijderd

23 dode `_register_*` functies plus 2 bijbehorende helpers. Alle functies waren al vervangen
door Laag 2 domeinregistries in Dag 1-4. De orkestrator-functie `register_all_routers()`
delegeert nu uitsluitend via lazy imports naar de registries.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|----|------|------|-------------|----------------|
| BE-CFG-013a | `router_registry.py` (verkleind) | Orchestrator module | `src/core/api/router_registry.py` | Wijziging (~1100 -> ~320 regels) |

---

## API-flows

### Flow: Dead code verwijdering uitvoeren (safe deletion workflow)

| Veld | Waarde |
|------|--------|
| Naam | Dead Code Verwijdering via Strangler Fig Protocol |
| Trigger | Developer start Dag 5 van SP-API-001 |
| Voorwaarden | Alle 12 equivalentietests GROEN na Dag 4; geen CI-falen op develop |
| Actie | Verwijder 23 `_register_*` functies en 2 helpers uit `router_registry.py` |
| Systeemverwerking | 1. Draai equivalentietests pre-delete om baseline vast te leggen; 2. Verwijder dode functies per batch; 3. Draai equivalentietests post-delete; 4. Draai volledige unit test suite (94 tests) |
| Succesrespons | 12/12 equivalentietests GROEN; 94/94 unit tests GROEN; router_registry.py ~320 regels |
| Foutrespons | Equivalentietest rood: een registry mist een module die de verwijderde functie nog bevatte -- herstel die module in de registry en herhaal |
| Uitzonderingen | `_register_optional_routers` en `_register_scheduling` zijn bewust behouden; verwijder deze niet zonder apart ADR-besluit |

### Flow: Equivalentietest als vangnet

| Veld | Waarde |
|------|--------|
| Naam | Equivalentietest Validatie na Dead Code Removal |
| Trigger | Na elke verwijdering van een `_register_*` functie |
| Voorwaarden | `tests/architecture/test_registry_equivalence.py` aanwezig met 12 tests |
| Actie | `pytest tests/architecture/test_registry_equivalence.py -v` |
| Systeemverwerking | AST parseert elke Laag 2 registry en vergelijkt import-module-sets met de verwijderde originele functies; test faalt als registry een module mist |
| Succesrespons | Alle 12 tests PASSED -- elke registry bevat superset van de originele modules |
| Foutrespons | `AssertionError`: ontbrekende module-paden getoond; developer voegt de module toe aan de betreffende registry |
| Uitzonderingen | Als een `_register_*` functie al verwijderd is, verwijder ook de bijbehorende equivalentietest na verificatie dat de registry compleet is |

---

## Detaildocumentatie per artefact

### `router_registry.py` na dead code removal

| Veld | Waarde |
|------|--------|
| Type | Dunne orkestrator (ADR-033 Laag 3) |
| Doel | Delegeert applicatiestart-routerregistratie naar Laag 2 domeinregistries |
| Regels voor | ~1100 regels (23 dode `_register_*` functies + helpers) |
| Regels na | ~320 regels (enkel orkestrator-logica + 2 actieve helpers) |
| Behouden | `_register_optional_routers` (actief), `_register_scheduling` (actief) |
| Business rule | Nooit nieuwe `_register_*` functies toevoegen; gebruik altijd een Laag 2 registry |
| Foutafhandeling | Per domein: try/except rondom registry-import; warning gelogd, startup gaat door |

### Equivalentietests (12 tests)

Alle 12 tests zijn AST-gebaseerd -- ze lezen bronbestanden en vergelijken geextraheerde
import-module-paden. Na verwijdering van de dode functies verifiëren de tests dat elke Laag 2
registry de correcte superset bevat.

| Test | Verifieert |
|------|------------|
| `test_auth_admin_registry_covers_same_modules_as_original` | auth_admin.py superset van originele auth/admin modules |
| `test_compliance_registry_covers_same_modules_as_original` | compliance.py superset van governance/compliance modules |
| `test_analytics_registry_covers_same_modules_as_original` | analytics.py superset van monitoring/health/events modules |
| `test_realtime_registry_covers_same_modules_as_original` | realtime.py superset van WS/copilot/notifications modules |
| `test_tenants_registry_covers_same_modules_as_original` | tenants.py superset van CRUD/procedures modules |
| `test_missions_registry_covers_same_modules_as_original` | missions.py superset van mission modules |
| `test_agents_registry_covers_same_modules_as_original` | agents.py superset van agent modules |
| `test_agentic_registry_covers_same_modules_as_original` | agentic.py superset van agentic flow modules |
| `test_workflows_registry_covers_same_modules_as_original` | workflows.py superset van workflow modules |
| `test_core_api_registry_covers_same_modules_as_original` | core_api.py superset van core API modules |
| `test_integrations_registry_covers_same_modules_as_original` | integrations.py superset van integration modules |
| `test_company_registry_covers_same_modules_as_original` | company.py superset van company/copilot modules |

---

### Trainingssamenvatting

#### Flow: Dead code verwijdering uitvoeren

| Veld | Waarde |
|------|--------|
| Actor | Developer / AI agent |
| Voorwaarde | Strangler Fig Dag 1-4 voltooid; alle equivalentietests GROEN |
| Actie | Verwijder elke `_register_*` functie die al gedelegeerd is naar een Laag 2 registry |
| Systeemverwerking | 1. Baseline test run; 2. Batch-verwijdering dode functies; 3. Post-delete test run; 4. Volledige unit suite |
| Succesrespons | 12/12 equivalentietests GROEN; router_registry.py dunne orkestrator (~320 regels) |
| Foutrespons | Rode equivalentietest toont welke module ontbreekt in registry; herstel module en hervalideer |
| Uitzonderingen | `_register_optional_routers` en `_register_scheduling` zijn actieve functies -- niet verwijderen |

#### Flow: Toekomstige `_register_*` functie veilig verwijderen

| Veld | Waarde |
|------|--------|
| Actor | Developer die een nieuwe domeinregistry heeft aangemaakt |
| Voorwaarde | Nieuwe Laag 2 registry aangemaakt en gedelegeerd vanuit `register_all_routers()` |
| Actie | 1. Schrijf/update equivalentietest; 2. Verifieer test GROEN; 3. Verwijder de `_register_*` functie; 4. Hervalideer test |
| Systeemverwerking | AST vergelijkt registry-imports met (nu verwijderde) originele functie; test detecteert ontbrekende modules |
| Succesrespons | Test GROEN na verwijdering -- registry bevat alle originele modules |
| Foutrespons | Test ROOD -- registry mist een of meer modules; voeg toe aan registry en herhaal |
| Uitzonderingen | Als de originele functie bewust minder modules registreerde (optionele omgeving), documenteer dit als `NOTE` in de equivalentietest |
