# BE-CFG-012 -- Domain Registry Split Dag 4: agents + agentic + workflows + core_api + integrations + company + copilot

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-012 |
| Feature naam | Domain Registry Split Dag 4: agents + agentic + workflows + core_api + integrations + company + copilot |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 4) |
| Reviewer | AI agent (review-BE-CFG-012.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 4 |
| Gerelateerde router / module | `src/core/api/registries/`, `src/core/api/router_registry.py`, `tests/architecture/` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Zet zeven nieuwe Laag 2 domeinregistries op (ADR-033 Strangler Fig stap 3 — hoogste complexiteit)
die agents, agentic features, workflows, core API, billing/integrations, company layer en copilot
isoleren. Breid de AST-gebaseerde equivalentietests uit tot 12 totaal. Na Dag 4 zijn nog slechts
twee directe `_register_*`-aanroepen over in `router_registry.py`:
`_register_optional_routers` (misc/bounded context) en `_register_scheduling` (ADR-033 bounded
context exception).

### In scope

- `src/core/api/registries/agents.py` — agents + agent submodules (54 regels)
- `src/core/api/registries/agentic.py` — agentic features gecomprimeerd (85 regels)
- `src/core/api/registries/workflows.py` — workflow-gerelateerde routers (74 regels)
- `src/core/api/registries/core_api.py` — core API endpoints (52 regels)
- `src/core/api/registries/integrations.py` — billing + integrations (60 regels)
- `src/core/api/registries/company.py` — company layer routers (61 regels)
- `src/core/api/registries/copilot.py` — copilot turn + AI Act incidents + enterprise OS (38 regels)
- `src/core/api/router_registry.py` — delegeert naar alle 7 nieuwe registries
- `tests/architecture/test_registry_equivalence.py` — 7 nieuwe equivalentietests (12 totaal)

### Out of scope

- Inhoudelijke routewijzigingen of nieuwe endpoints
- Verwijdering van dode `_register_*` functies (Dag 5, na 5 groene CI-runs per ADR-033 §6)
- `_register_optional_routers` en `_register_scheduling` (bewust bewaard als directe calls)

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand | Regels |
|----------|------|---------|--------|
| `agents.register()` | Registry functie | `src/core/api/registries/agents.py` | 54 |
| `agentic.register()` | Registry functie | `src/core/api/registries/agentic.py` | 85 |
| `workflows.register()` | Registry functie | `src/core/api/registries/workflows.py` | 74 |
| `core_api.register()` | Registry functie | `src/core/api/registries/core_api.py` | 52 |
| `integrations.register()` | Registry functie | `src/core/api/registries/integrations.py` | 60 |
| `company.register()` | Registry functie | `src/core/api/registries/company.py` | 61 |
| `copilot.register()` | Registry functie | `src/core/api/registries/copilot.py` | 38 |
| 7 equivalentietests (Dag 4) | Test functies | `tests/architecture/test_registry_equivalence.py` | +nieuw |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `register_all_routers()` | Delegeert naar alle 7 nieuwe registries via lazy imports | `src/core/api/router_registry.py` |

### Verwijderd

Niets — dode `_register_*` functies bewaard per Strangler Fig protocol.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|----|------|------|-------------|----------------|
| BE-CFG-012a | `agents.register` | Registry functie | `src/core/api/registries/agents.py` | Nieuw |
| BE-CFG-012b | `agentic.register` | Registry functie | `src/core/api/registries/agentic.py` | Nieuw |
| BE-CFG-012c | `workflows.register` | Registry functie | `src/core/api/registries/workflows.py` | Nieuw |
| BE-CFG-012d | `core_api.register` | Registry functie | `src/core/api/registries/core_api.py` | Nieuw |
| BE-CFG-012e | `integrations.register` | Registry functie | `src/core/api/registries/integrations.py` | Nieuw |
| BE-CFG-012f | `company.register` | Registry functie | `src/core/api/registries/company.py` | Nieuw |
| BE-CFG-012g | `copilot.register` | Registry functie | `src/core/api/registries/copilot.py` | Nieuw |
| BE-CFG-012h | `test_registry_equivalence` (Dag 4) | Test module uitbreiding | `tests/architecture/test_registry_equivalence.py` | Gewijzigd |

---

## API-flows

### Flow: Agents Domain Registry Startup

| Veld | Waarde |
|------|--------|
| Naam | Agents Registry Startup |
| Trigger | `register_all_routers(app)` aanroepen bij applicatiestart |
| Voorwaarden | Python modules beschikbaar; optionele agent-submodule-routers via try/except |
| Request-pad | Intern startup proces -- geen HTTP request |
| Service-stappen | 1. Lazy import `agents` registry; 2. `agents.register(app)` aanroepen; 3. Hoofd-agent routers + agent-submodule routers geregistreerd |
| Successtatus | Agents- en agent-submodule-routers beschikbaar op `/api/v1` |
| Foutpaden | Optionele agent-submodule routers: try/except -- warning gelogd, startup gaat door |
| Eindtoestand | Alle agents-gerelateerde paden beschikbaar |

### Flow: Copilot Registry Startup

| Veld | Waarde |
|------|--------|
| Naam | Copilot Registry Startup |
| Trigger | `register_all_routers(app)` aanroepen bij applicatiestart |
| Voorwaarden | Python modules beschikbaar |
| Request-pad | Intern startup proces |
| Service-stappen | 1. Lazy import `copilot` registry; 2. `copilot.register(app)` aanroepen; 3. copilot/turn + AI Act incidents + enterprise OS routers geregistreerd |
| Successtatus | Copilot, AI Act en enterprise OS endpoints beschikbaar |
| Foutpaden | Per router: try/except -- warning gelogd, niet fataal |
| Eindtoestand | Alle copilot-gerelateerde paden beschikbaar |

---

## Detaildocumentatie per artefact

### `agentic.register()` — gecomprimeerde registratie

| Veld | Waarde |
|------|--------|
| Type | Registry functie |
| Doel | Registreert alle agentic feature routers (Focus Builder, Council deliberation, ALS, etc.) |
| Business rules | Alle sub-routers via try/except; mislukken is niet fataal |
| Zichtbaarheid | Publiek via `register(app)` interface |
| Foutafhandeling | Per router: warning gelogd, startup gaat door |

### `test_registry_equivalence` -- Dag 4 uitbreiding (7 nieuwe tests, 12 totaal)

| Test | Verifieert |
|------|------------|
| `test_agents_registry_covers_same_modules_as_original` | agents.py superset van _register_agents + _register_agent_submodules |
| `test_agentic_registry_covers_same_modules_as_original` | agentic.py superset van _register_agentic_features |
| `test_workflows_registry_covers_same_modules_as_original` | workflows.py superset van _register_workflows |
| `test_core_api_registry_covers_same_modules_as_original` | core_api.py superset van _register_core_api |
| `test_integrations_registry_covers_same_modules_as_original` | integrations.py superset van _register_billing_integrations |
| `test_company_registry_covers_same_modules_as_original` | company.py superset van _register_company_layer |
| `test_copilot_registry_covers_same_modules_as_original` | copilot.py superset van _register_copilot_turn + _register_ai_act_incidents + _register_enterprise_os |

---

### Trainingssamenvatting

#### Flow: Zeven nieuwe registries toevoegen aan applicatiestart

| Veld | Waarde |
|------|--------|
| Actor | FastAPI applicatiestart / `register_all_routers()` |
| Voorwaarde | 7 nieuwe registry-bestanden aanwezig in `src/core/api/registries/` |
| Actie | `register_all_routers(app)` wordt aangeroepen vanuit `main.py` vóór lifespan |
| Systeemverwerking | Voor elke registry: lazy import + `X.register(app)`; try/except per router voorkomt fatale startup-fouten |
| Succesrespons | Alle agents/agentic/workflows/core_api/integrations/company/copilot endpoints beschikbaar |
| Foutrespons | Bij ontbrekende module: warning gelogd, overige routers starten normaal |
| Uitzonderingen | `_register_optional_routers` en `_register_scheduling` blijven directe aanroepen in `router_registry.py` |

#### Flow: Equivalentietest uitvoeren na registry-wijziging (Dag 4)

| Veld | Waarde |
|------|--------|
| Actor | CI-pipeline / developer |
| Voorwaarde | Registry bestand aangemaakt of gewijzigd; 12 equivalentietests aanwezig |
| Actie | `pytest tests/architecture/test_registry_equivalence.py -v` |
| Systeemverwerking | AST parseert alle 12 registry-bestanden en bijbehorende originele `_register_*`-functies; vergelijkt import-module-sets |
| Succesrespons | Alle 12 tests PASSED -- elke registry bevat superset van originele modules |
| Foutrespons | `AssertionError`: lijst van ontbrekende module-paden getoond per registry |
| Uitzonderingen | Als een `_register_*`-functie verwijderd is (Dag 5), bijbehorende test aanpassen |
