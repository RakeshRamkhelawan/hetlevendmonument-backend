# BE-CFG-010 -- Domain Registry Split: auth_admin + compliance (ADR-033)

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-010 |
| Feature naam | Domain Registry Split: auth_admin + compliance (ADR-033) |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 2) |
| Reviewer | AI agent (review-BE-CFG-010.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 2 |
| Gerelateerde router / module | `src/core/api/registries/auth_admin.py`, `src/core/api/registries/compliance.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Splits de monolithische `register_all_routers()` in `router_registry.py` op naar Laag 2
domeinregistries conform ADR-033. Twee nieuwe registry-modules (`auth_admin` en `compliance`)
bevatten elk een enkelvoudige `register(app) -> int` functie. `router_registry.py` delegeert
naar deze modules via lazy imports. De fitness test `test_registry_files_under_80_lines` is
hierdoor nu GROEN.

### In scope

- Aanmaken van `src/core/api/registries/__init__.py` (package init voor Laag 2)
- Aanmaken van `src/core/api/registries/auth_admin.py` (55 regels) met `register(app) -> int`
- Aanmaken van `src/core/api/registries/compliance.py` (35 regels) met `register(app) -> int`
- Wijziging van `src/core/api/router_registry.py`: `register_all_routers()` delegeert naar de twee nieuwe modules

### Out of scope

- Verwijdering van de `_register_auth_admin`, `_register_admin_management`, `_register_governance_v1`,
  `_register_compliance` functies in `router_registry.py` (Strangler Fig: verwijderen na 5 groene CI-runs)
- Andere domeinregistries (agents, workflows, etc.) -- dit is Dag 2 scope
- Database-wijzigingen of Alembic migraties
- Nieuwe endpoints of functionaliteit

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand |
|----------|------|---------|
| `registries/__init__.py` | Package init | `src/core/api/registries/__init__.py` |
| `auth_admin.register` | Registry function (55 regels) | `src/core/api/registries/auth_admin.py` |
| `compliance.register` | Registry function (35 regels) | `src/core/api/registries/compliance.py` |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `register_all_routers` | Delegeert nu naar `auth_admin.register(app)` en `compliance.register(app)` via lazy imports | `src/core/api/router_registry.py` |

### Verwijderd

Niets. Oude `_register_*` functies in `router_registry.py` blijven als dead code (Strangler Fig
patroon -- verwijderen na 5 groene CI-runs).

### Beinvloede bestaande flows

Geen functionele wijzigingen. Alle routers worden op identieke paden geregistreerd. De
fitness test `test_registry_files_under_80_lines` is nu GROEN (was SKIP voor deze wijziging).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|----------------|-------------------|
| BE-CFG-010 | auth_admin.register | Registry function | `src/core/api/registries/auth_admin.py` | Nieuw | Router registratie startup |
| BE-CFG-010 | compliance.register | Registry function | `src/core/api/registries/compliance.py` | Nieuw | Router registratie startup |

---

## API-flows

### Flow: Auth/Admin Router Registratie via auth_admin Registry

| Veld | Waarde |
|------|--------|
| Naam | Auth/Admin Router Registratie |
| Trigger | `register_all_routers(app)` aangeroepen bij applicatie-startup |
| Voorwaarden | FastAPI applicatie-object beschikbaar; alle router-modules importeerbaar |
| Request-pad | Geen HTTP request -- intern startup proces |
| Service-stappen | 1. `register_all_routers(app)` roept `auth_admin.register(app)` aan; 2. `auth_admin.register` importeert routers via lazy imports; 3. `auth_admin.register` includeert: auth_router, admin_router, admin_learning_router, admin_digital_twin_router, management_router, admin_experiments_router; 4. Optioneel: rag_router als `RAG_ENABLED=true`; 5. Retourneert totaalteller |
| DB-operaties | Geen |
| Successtatus | Alle routers geregistreerd; teller verhoogd met het aantal geregistreerde routers |
| Foutpaden | `ImportError` bij ontbrekende router-module -- bubbelt op naar `register_all_routers` |
| Eindtoestand | Auth, admin en management endpoints beschikbaar op `/api/v1` |

### Flow: Compliance Router Registratie via compliance Registry

| Veld | Waarde |
|------|--------|
| Naam | Compliance Router Registratie |
| Trigger | `register_all_routers(app)` aangeroepen bij applicatie-startup |
| Voorwaarden | FastAPI applicatie-object beschikbaar; governance/gatekeeper/compliance modules importeerbaar |
| Request-pad | Geen HTTP request -- intern startup proces |
| Service-stappen | 1. `register_all_routers(app)` roept `compliance.register(app)` aan; 2. `compliance.register` importeert routers via lazy imports; 3. Registreert governance_v1_router; 4. Registreert gatekeeper_router (try/except: optioneel, fout wordt gelogd maar stopt niet de startup); 5. Registreert compliance_router op prefix `/api/v1`; 6. Retourneert teller |
| DB-operaties | Geen |
| Successtatus | Compliance routers geregistreerd; teller verhoogd |
| Foutpaden | `gatekeeper_router` import in try/except -- als import mislukt wordt het overgeslagen en gelogd |
| Eindtoestand | Governance en compliance endpoints beschikbaar |

---

## Detaildocumentatie per artefact

### `auth_admin.register`

| Veld | Waarde |
|------|--------|
| Type | Registry function |
| Locatie | `src/core/api/registries/auth_admin.py` |
| Doel | Registreer alle auth- en admin-gerelateerde routers op de FastAPI applicatie |
| Functionele beschrijving | Registreert: auth_router, admin_router (met prefix `/api/v1`), admin_learning_router, admin_digital_twin_router (prefix `/api/v1`), management_router, admin_experiments_router (prefix `/api/v1`). Conditoneel: rag_router als `_rag_enabled()` truthy. |
| Technische beschrijving | Signatuur `def register(app: FastAPI) -> int`. Lazy imports voorkomen circulaire afhankelijkheden. `_rag_enabled()` helper leest `RAG_ENABLED` env var. Retourneert aantal geregistreerde routers. |
| Zichtbaarheids- en toegangsregels | Module-publiek. Alleen aanroepbaar door `router_registry.register_all_routers`. |
| Acceptatiecriteria | Bestand <= 80 regels; `test_registry_files_under_80_lines` GROEN; alle auth/admin endpoints bereikbaar na startup |

### `compliance.register`

| Veld | Waarde |
|------|--------|
| Type | Registry function |
| Locatie | `src/core/api/registries/compliance.py` |
| Doel | Registreer alle compliance- en governance-gerelateerde routers op de FastAPI applicatie |
| Functionele beschrijving | Registreert: governance_v1_router, gatekeeper_router (optioneel via try/except), compliance_router (prefix `/api/v1`). Gatekeeper is optioneel omdat de module mogelijk niet altijd beschikbaar is. |
| Technische beschrijving | Signatuur `def register(app: FastAPI) -> int`. Try/except om gatekeeper-import: als de import mislukt, wordt de router overgeslagen en wordt er een warning gelogd. Retourneert aantal geregistreerde routers. |
| Zichtbaarheids- en toegangsregels | Module-publiek. Alleen aanroepbaar door `router_registry.register_all_routers`. |
| Acceptatiecriteria | Bestand <= 80 regels; governance en compliance endpoints bereikbaar; gatekeeper-afwezigheid crasht startup niet |

### Trainingssamenvatting

#### Flow: Domain Registry Splitsing (auth_admin + compliance)

| Veld | Waarde |
|------|--------|
| Actor | Backend engineer / AI agent |
| Voorwaarde | `register_all_routers()` bevat te veel directe router-registraties; `test_registry_files_under_80_lines` slaagt niet |
| Actie | Maak `src/core/api/registries/auth_admin.py` en `compliance.py` aan met `register(app) -> int`; laat `router_registry.py` delegeren via lazy imports |
| Systeemverwerking | Bij startup roept `register_all_routers(app)` `auth_admin.register(app)` en `compliance.register(app)` aan; elke registry-module importeert en registreert zijn eigen routers |
| Succesrespons | Alle auth/admin/compliance endpoints bereikbaar op `/api/v1`; `test_registry_files_under_80_lines` GROEN |
| Foutrespons | `ImportError` in registry-module -- bubbelt op en crasht de applicatie-startup; fix door ontbrekende module toe te voegen |
| Uitzonderingen | Gatekeeper-router is optioneel (try/except); als import mislukt, wordt de router overgeslagen met een warning log; overige routers worden wel geregistreerd |

---

## Integratorhandleiding

Geen API-contract wijzigingen. Alle endpoints blijven beschikbaar op dezelfde paden.

Bij het toevoegen van een nieuwe router aan het auth/admin of compliance domein:
1. Voeg de lazy import en `app.include_router()` aanroep toe aan het juiste registry-bestand
2. Verhoog de return-teller
3. Verifieer dat het registry-bestand <= 80 regels blijft (fitness test)

Bij het toevoegen van een geheel nieuw domein: maak een nieuw bestand aan in
`src/core/api/registries/<domein>.py` en voeg een delegatie-aanroep toe in
`router_registry.register_all_routers`.

---

## Open aannames / Open vragen / Risico's

| Type | Omschrijving | Status |
|------|--------------|--------|
| Aanname | Oude `_register_*` functies in `router_registry.py` worden verwijderd na 5 groene CI-runs (Strangler Fig) | Open -- bewust uitgesteld |
| Aanname | gatekeeper_router import is optioneel; try/except is bewust en gedocumenteerd | Bevestigd |
| Risico | Strangler Fig dead code vergeten verwijderen | Laag -- `test_registry_files_under_80_lines` bewaakt de grootte |

---

## QA-checks

- [x] `python -m py_compile src/core/api/registries/auth_admin.py` -- geen errors
- [x] `python -m py_compile src/core/api/registries/compliance.py` -- geen errors
- [x] `ruff check src/core/api/registries/` -- 0 errors
- [x] `wc -l src/core/api/registries/auth_admin.py` -- <= 80 regels (55 regels)
- [x] `wc -l src/core/api/registries/compliance.py` -- <= 80 regels (35 regels)
- [x] `pytest tests/unit/test_registry_files_under_80_lines.py -v` -- GROEN (was SKIP)
- [x] Geen regressies in bestaande router-registratie tests

---

## Definition of Done

- [x] `src/core/api/registries/__init__.py` aangemaakt
- [x] `src/core/api/registries/auth_admin.py` aangemaakt (<= 80 regels)
- [x] `src/core/api/registries/compliance.py` aangemaakt (<= 80 regels)
- [x] `router_registry.py` delegeert naar beide nieuwe modules
- [x] `test_registry_files_under_80_lines` GROEN
- [x] Alle kwaliteitschecks groen
- [x] Feature spec aangemaakt (dit bestand)
- [x] Review APPROVED (`docs/backend/review/review-BE-CFG-010.md`)
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
