# BE-CFG-008 -- _register_notifications_v1 Forward Reference Fix in router_registry

| Veld | Waarde |
|------|--------|
| Feature ID | BE-CFG-008 |
| Feature naam | _register_notifications_v1 Forward Reference Fix in router_registry |
| Status | APPROVED |
| Auteur | AI agent (SP-WE-23) |
| Reviewer | AI agent (review-BE-CFG-008.md) |
| Datum | 2026-06-01 |
| Gerelateerde user story / ticket | NEW-WIRE-005 |
| Gerelateerde router / module | `src/core/api/router_registry.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Corrigeer de definitievolgorde van `_register_notifications_v1` in `router_registry.py` zodat
de functiedefinitie voor de aanroep staat, consistent met alle andere `_register_*` hulpfuncties
in hetzelfde bestand.

### In scope

- Verplaatsen van de functiedefinitie `_register_notifications_v1` (7 regels) van na de aanroep
  naar voor de aanroepende functie `register_all_routers`
- Toevoegen van 2 regression tests die de correcte volgorde permanent bewaken

### Out of scope

- Inhoudelijke wijzigingen aan `_register_notifications_v1`
- Wijzigingen aan de notifications router (`src/core/api/v1/notifications/router.py`)
- Nieuwe endpoints of functionaliteit
- Database-wijzigingen of Alembic migraties
- Wijzigingen aan andere `_register_*` functies

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand |
|----------|------|---------|
| `TestNotificationsRouterRegistryOrder` | Test class (2 tests) | `tests/unit/test_sp_we_23_notifications_router_registry.py` |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `_register_notifications_v1` | Definitievolgorde gecorrigeerd (r1021 -> r978) | `src/core/api/router_registry.py` |

### Verwijderd

Niets.

### Beinvloede bestaande flows

Geen functionele wijzigingen -- de notifications router wordt op identieke manier geregistreerd
op `/api/v1`. Alleen de bronvolgorde is veranderd.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|----------------|-------------------|
| BE-CFG-008 | _register_notifications_v1 | Helper function | `src/core/api/router_registry.py:978` | Wijziging (volgorde) | Router registratie startup |

---

## API-flows

### Flow: Router Registry Startup

| Veld | Waarde |
|------|--------|
| Naam | Router Registry Startup |
| Trigger | FastAPI applicatie start (`register_all_routers(app)` aangeroepen vanuit `app_lifespan.py`) |
| Voorwaarden | Python module volledig geladen |
| Request-pad | Geen HTTP request -- intern startup proces |
| Service-stappen | 1. `register_all_routers(app)` aanroepen; 2. `_register_notifications_v1(app)` aanroepen; 3. Router geincludeerd op `/api/v1` |
| DB-operaties | Geen |
| Successtatus | Router geregistreerd, `total` verhoogd met 1 |
| Foutpaden | ImportError bij ontbrekende notifications router module |
| Eindtoestand | Notifications router beschikbaar op `/api/v1/notifications` |

---

## Detaildocumentatie per artefact

### `_register_notifications_v1`

| Veld | Waarde |
|------|--------|
| Type | Helper function |
| Locatie | `src/core/api/router_registry.py:978` |
| Gerelateerde flow | Router Registry Startup |
| Doel | Registreer de notifications v1 router op de FastAPI applicatie |
| Functionele beschrijving | Importeert de notifications router module en includeert hem op prefix `/api/v1`. Retourneert 1 als teller voor het totale aantal geregistreerde routers. |
| Technische beschrijving | Gebruikt deferred import (`from src.core.api.v1.notifications.router import router`) om circulaire imports te voorkomen. Aanroep via `app.include_router(router, prefix="/api/v1")`. |
| Zichtbaarheids- en toegangsregels | Module-private functie (underscore-prefix). Alleen aanroepbaar door `register_all_routers`. |
| Request-specificatie | Geen (niet een HTTP endpoint) |
| Response-specificatie | `int` -- altijd 1 |
| Validaties en constraints | Geen runtime validaties; Python garanteert type correctheid bij import |
| Business rules | Definitie moet VOOR de aanroep staan (definitievolgorde-conventie dit project) |
| Afhankelijkheden | `src.core.api.v1.notifications.router` (deferred import) |
| Foutafhandeling | ImportError bij ontbrekende module -- bubbelt op naar `register_all_routers` |
| Transacties en dataintegriteit | Niet van toepassing |
| Telemetry / logging / tracing | `logger.debug("Notifications router registered at /api/v1/notifications")` |
| Caching | Niet van toepassing |
| Acceptatiecriteria | `grep` toont definitielijn < aanroeplijn; module importeert zonder errors; ruff geeft 0 errors |
| Integratoruitleg | Niet van toepassing -- interne functie |

### Trainingssamenvatting

#### Flow: Router Registry Forward Reference Correctie

| Veld | Waarde |
|------|--------|
| Actor | Backend engineer / AI agent |
| Voorwaarde | `_register_notifications_v1` definitie staat na aanroep in router_registry.py |
| Actie | Verplaats de functiedefinitie naar boven de aanroep (geen inhoudelijke wijziging) |
| Systeemverwerking | Python parseert het module opnieuw; definitie nu voor aanroep in bronvolgorde |
| Succesrespons | `grep -n "_register_notifications_v1" src/core/api/router_registry.py` toont definitielijn < aanroeplijn |
| Foutrespons | Syntax error of import error bij onjuiste verplaatsing -- corrigeer direct |
| Uitzonderingen | Als de functie groter is dan verwacht (> 7 regels), spawn pr-review skill voor verificatie |

---

## Integratorhandleiding

Deze fix heeft geen invloed op de publieke API. De notifications endpoints blijven beschikbaar
op dezelfde paden als voor de fix. Geen actie vereist voor integrators.

---

## Open aannames / Open vragen / Risico's

| Type | Omschrijving | Status |
|------|--------------|--------|
| Aanname | Alle andere `_register_*` functies in router_registry.py staan al VOOR hun aanroep | Bevestigd via code-inspectie |
| Risico | Geen -- puur bronvolgorde-wijziging zonder functionele impact | Gesloten |

---

## QA-checks

- [x] `python -m py_compile src/core/api/router_registry.py` -- geen errors
- [x] `python -c "import src.core.api.router_registry; print('OK')"` -- importeert correct
- [x] `ruff check src/core/api/router_registry.py` -- 0 errors
- [x] `grep -n "_register_notifications_v1"` toont definitie (978) < aanroep (1025)
- [x] `pytest tests/unit/test_sp_we_23_notifications_router_registry.py -v` -- 2/2 PASS
- [x] Geen regressies in SP-WE sprint tests (26/26 PASS)

---

## Definition of Done

- [x] Functiedefinitie staat voor de aanroep in bronvolgorde
- [x] Alle kwaliteitschecks groen
- [x] 2 regression tests PASS
- [x] Feature spec aangemaakt (dit bestand)
- [x] Review APPROVED (`docs/backend/review/review-BE-CFG-008.md`)
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
- [x] Sprint CLOSED in SPRINT-CANVAS.md en SPRINT_TRACKER.md
