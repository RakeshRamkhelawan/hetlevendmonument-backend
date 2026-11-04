# BE-CFG-011 -- Domain Registry Split Dag 3: analytics + realtime + tenants

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-011 |
| Feature naam | Domain Registry Split Dag 3: analytics + realtime + tenants |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 3) |
| Reviewer | AI agent (review-BE-CFG-011.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Dag 3 |
| Gerelateerde router / module | `src/core/api/registries/`, `src/core/api/router_registry.py`, `tests/architecture/` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Zet drie nieuwe Laag 2 domeinregistries op (ADR-033 Strangler Fig stap 2) die monitoring,
realtime-communicatie en tenant/CRUD-beheer isoleren. Voeg AST-gebaseerde equivalentietests toe
die bewijzen dat de registry exact dezelfde router-modules registreert als de originele functies.

### In scope

- `src/core/api/registries/analytics.py` — monitoring, productie, rbac, security, analytics, events, health, feature flags (57 regels)
- `src/core/api/registries/realtime.py` — WebSocket, Co-Pilot WS/audit, notifications v1 (46 regels)
- `src/core/api/registries/tenants.py` — tenants, users, documents, tools, procedures-stub (70 regels)
- `src/core/api/router_registry.py` — delegeert via lazy imports naar nieuwe registries
- `tests/architecture/test_registry_equivalence.py` — 5 AST-equivalentietests (alle 5 GROEN)

### Out of scope

- Inhoudelijke routewijzigingen of nieuwe endpoints
- Agents, workflows, company layer, billing (Dag 4)
- Volledige verwijdering van dode `_register_*` functies (na 5 groene CI-runs per ADR-033 §6)

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand | Regels |
|----------|------|---------|--------|
| `analytics.register()` | Registry functie | `src/core/api/registries/analytics.py` | 57 |
| `realtime.register()` | Registry functie | `src/core/api/registries/realtime.py` | 46 |
| `tenants.register()` | Registry functie | `src/core/api/registries/tenants.py` | 70 |
| `test_registry_equivalence.py` | Test module (5 tests) | `tests/architecture/test_registry_equivalence.py` | 123 |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `register_all_routers()` | Delegeert naar analytics/realtime/tenants via lazy imports | `src/core/api/router_registry.py` |

### Verwijderd

Niets — dode `_register_*` functies bewaard per Strangler Fig protocol.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging |
|----|------|------|-------------|----------------|
| BE-CFG-011a | `analytics.register` | Registry functie | `src/core/api/registries/analytics.py` | Nieuw |
| BE-CFG-011b | `realtime.register` | Registry functie | `src/core/api/registries/realtime.py` | Nieuw |
| BE-CFG-011c | `tenants.register` | Registry functie | `src/core/api/registries/tenants.py` | Nieuw |
| BE-CFG-011d | `test_registry_equivalence` | Test module | `tests/architecture/test_registry_equivalence.py` | Nieuw |

---

## API-flows

### Flow: Analytics Domain Registry Startup

| Veld | Waarde |
|------|--------|
| Naam | Analytics Registry Startup |
| Trigger | `register_all_routers(app)` aanroepen bij applicatiestart |
| Voorwaarden | Python modules beschikbaar |
| Request-pad | Intern startup proces — geen HTTP request |
| Service-stappen | 1. Lazy import `analytics` registry; 2. `analytics.register(app)` aanroepen; 3. 6-9 routers geregistreerd afhankelijk van optionele modules |
| Successtatus | Monitoring, analytics, health en feature-flag routers beschikbaar op `/api/v1` en `/api` |
| Foutpaden | Events/Feature Flags router: try/except — warning gelogd, startup gaat door |
| Eindtoestand | Alle analytics-gerelateerde paden beschikbaar |

### Flow: Tenants Registry Startup

| Veld | Waarde |
|------|--------|
| Naam | Tenants Registry Startup |
| Trigger | `register_all_routers(app)` aanroepen bij applicatiestart |
| Voorwaarden | `ENABLE_P5_STUB_CRUD_ROUTERS` en `ENVIRONMENT` env vars gelezen |
| Request-pad | Intern startup proces |
| Service-stappen | 1. `_stub_crud_enabled()` evalueren; 2. Tenants/users/documents/tools proberen; 3. Procedures alleen bij `_stub_crud_enabled()=True` |
| Successtatus | CRUD-routers beschikbaar; procedures optioneel |
| Foutpaden | Per router: try/except — warning gelogd, niet fataal |
| Eindtoestand | Tenants/users/documents/tools altijd geprobeerd; procedures afhankelijk van flag |

---

## Detaildocumentatie per artefact

### `tenants._stub_crud_enabled()`

| Veld | Waarde |
|------|--------|
| Type | Helper functie |
| Doel | Bepaal of de procedures-stub geregistreerd mag worden |
| Business rules | In `production`/`prod` altijd `False`, ongeacht de vlag; elders: vlag-waarde |
| Zichtbaarheid | Module-privé (underscore-prefix) |
| Foutafhandeling | Geen exceptions — puur boolean logica op env vars |

### `test_registry_equivalence` (5 tests)

Alle 5 tests zijn AST-gebaseerd — ze lezen bronbestanden en vergelijken geëxtraheerde import-module-paden:

| Test | Verifieert |
|------|------------|
| `test_auth_admin_registry_covers_same_modules_as_original` | auth_admin.py ⊇ _register_auth_admin + _register_admin_management |
| `test_compliance_registry_covers_same_modules_as_original` | compliance.py ⊇ _register_governance_v1 + _register_compliance |
| `test_analytics_registry_covers_same_modules_as_original` | analytics.py ⊇ _register_monitoring_security + _register_health + _register_feature_flags + _register_events |
| `test_realtime_registry_covers_same_modules_as_original` | realtime.py ⊇ _register_websocket + _register_copilot_ws + _register_copilot_audit + _register_notifications_v1 |
| `test_tenants_registry_covers_same_modules_as_original` | tenants.py ⊇ _register_p5_crud_routers |

---

### Trainingssamenvatting

#### Flow: Registry equivalentietest uitvoeren

| Veld | Waarde |
|------|--------|
| Actor | CI-pipeline / developer |
| Voorwaarde | Registry bestand aangemaakt of gewijzigd |
| Actie | `pytest tests/architecture/test_registry_equivalence.py -v` |
| Systeemverwerking | AST parseert registry-bestand en originele `_register_*`-functies; vergelijkt import-module-sets |
| Succesrespons | Alle 5 tests PASSED — registry bevat superset van originele modules |
| Foutrespons | `AssertionError`: lijst van ontbrekende module-paden getoond |
| Uitzonderingen | Als een `_register_*`-functie verwijderd is, updaten de bijbehorende test |

#### Flow: Tenants registry startup met gated procedures

| Veld | Waarde |
|------|--------|
| Actor | FastAPI applicatiestart |
| Voorwaarde | `ENABLE_P5_STUB_CRUD_ROUTERS` env var aanwezig of afwezig |
| Actie | `tenants.register(app)` wordt aangeroepen door `register_all_routers` |
| Systeemverwerking | `_stub_crud_enabled()` evalueert env var + environment; procedures-router conditioneel |
| Succesrespons | Tenants/users/documents/tools altijd geprobeerd; procedures optioneel |
| Foutrespons | Bij `ENVIRONMENT=production` + vlag: warning gelogd, stub niet geladen |
| Uitzonderingen | Bij ontbrekende module: try/except vangt op, warning gelogd, geen fatal error |
