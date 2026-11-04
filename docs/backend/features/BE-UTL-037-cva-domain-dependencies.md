# BE-UTL-037 -- CVA Domain Dependencies Module (ADR-033)

| Veld | Waarde |
|------|--------|
| Feature ID | BE-UTL-037 |
| Feature naam | CVA Domain Dependencies Module (ADR-033) |
| Status | APPROVED |
| Auteur | AI agent (SP-API-001 Dag 1) |
| Reviewer | AI agent (review-BE-UTL-037.md) |
| Datum | 2026-06-02 |
| Gerelateerde user story / ticket | SP-API-001 Stap 0C |
| Gerelateerde router / module | `src/core/api/v1/cva/dependencies.py` |
| Gerelateerde frontend endpoints | Geen |
| Gerelateerde database tabellen | Geen |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Verplaats de CVA-domein helper `handle_cva_value_error` uit de globale `cva_utils.py` naar een
nieuw domein-specifiek `src/core/api/v1/cva/dependencies.py` module, conform het ADR-033
drie-laags router-patroon dat domain-specific dependencies in `v1/<domein>/dependencies.py`
plaatst.

### In scope

- Aanmaken van `src/core/api/v1/cva/__init__.py` (package init)
- Aanmaken van `src/core/api/v1/cva/dependencies.py` met `handle_cva_value_error`
- Bijwerken van de import in `src/core/api/cva_chat.py` (van `cva_utils` naar `v1.cva.dependencies`)
- Bijwerken van de import in `src/core/api/cva_conversations.py` (van `cva_utils` naar `v1.cva.dependencies`)

### Out of scope

- Inhoudelijke logicawijzigingen aan `handle_cva_value_error`
- Wijzigingen aan `cva_utils.py` zelf (het globale bestand blijft aanwezig voor andere consumers)
- Database-wijzigingen of Alembic migraties
- Nieuwe endpoints of functionaliteit

---

## Build summary

### Nieuw gebouwd

| Artefact | Type | Bestand |
|----------|------|---------|
| `src/core/api/v1/cva/__init__.py` | Package init | `src/core/api/v1/cva/__init__.py` |
| `handle_cva_value_error` | Helper function | `src/core/api/v1/cva/dependencies.py` |

### Gewijzigd

| Artefact | Wijziging | Bestand |
|----------|-----------|---------|
| `cva_chat.py` | Import van `cva_utils` -> `v1.cva.dependencies` | `src/core/api/cva_chat.py` |
| `cva_conversations.py` | Import van `cva_utils` -> `v1.cva.dependencies` | `src/core/api/cva_conversations.py` |

### Verwijderd

Niets. `cva_utils.py` blijft aanwezig voor overige consumers.

### Beinvloede bestaande flows

Geen functionele wijzigingen -- `handle_cva_value_error` gedraagt zich identiek. Alleen de
importlocatie is veranderd.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|----------------|-------------------|
| BE-UTL-037 | handle_cva_value_error | Helper function | `src/core/api/v1/cva/dependencies.py` | Nieuw | CVA foutafhandeling |

---

## API-flows

### Flow: CVA ValueError naar HTTP Exception conversie

| Veld | Waarde |
|------|--------|
| Naam | CVA ValueError naar HTTP Exception |
| Trigger | CVAService gooit een `ValueError` tijdens endpoint-verwerking |
| Voorwaarden | CVA endpoint is aangeroepen; CVAService heeft de fout opgegooid |
| Request-pad | Geen directe HTTP flow -- helper wordt aangeroepen vanuit endpoint exception handlers |
| Service-stappen | 1. Endpoint vangt `ValueError`; 2. Roept `handle_cva_value_error(e, context)` aan; 3. Helper geeft `HTTPException` terug |
| DB-operaties | Geen |
| Successtatus | `HTTPException(status_code=404)` bij "not found or access denied" in bericht; `HTTPException(status_code=422)` voor overige ValueErrors |
| Foutpaden | Geen -- helper gooit zelf nooit een exceptie |
| Eindtoestand | Caller geeft de `HTTPException` terug aan FastAPI voor correcte HTTP-response |

---

## Detaildocumentatie per artefact

### `handle_cva_value_error`

| Veld | Waarde |
|------|--------|
| Type | Helper function |
| Locatie | `src/core/api/v1/cva/dependencies.py` |
| Gerelateerde flow | CVA ValueError naar HTTP Exception |
| Doel | Converteer CVAService `ValueError` naar de juiste `HTTPException` status code |
| Functionele beschrijving | Inspecteert het bericht van de `ValueError`. Als het "not found or access denied" bevat (case-insensitive), retourneert het een 404. In alle andere gevallen retourneert het een 422 met `detail=f"{context}: {e}"`. |
| Technische beschrijving | Enkelvoudige functie met signatuur `def handle_cva_value_error(e: ValueError, context: str) -> HTTPException`. Gebruikt `str(e).lower()` voor de inspectie. Geen externe dependencies of I/O. |
| Zichtbaarheids- en toegangsregels | Module-publiek. Importeerbaar door alle CVA-endpoint modules in `src/core/api/`. |
| Request-specificatie | Geen (geen HTTP endpoint) |
| Response-specificatie | `HTTPException` -- `status_code=404` of `status_code=422` |
| Validaties en constraints | `e` moet een `ValueError` zijn; `context` is een vrij te kiezen beschrijvende string voor de caller |
| Business rules | "not found or access denied" resulteert in 404; alle overige ValueErrors in 422 |
| Afhankelijkheden | `fastapi.HTTPException` |
| Foutafhandeling | Geen -- de functie zelf gooit nooit een exceptie |
| Transacties en dataintegriteit | Niet van toepassing |
| Telemetry / logging / tracing | Geen -- logging is verantwoordelijkheid van de caller |
| Caching | Niet van toepassing |
| Acceptatiecriteria | `cva_chat.py` en `cva_conversations.py` importeren vanuit `v1.cva.dependencies`; `ruff check` 0 errors; module importeert zonder errors |
| Integratoruitleg | Gooi een `ValueError` vanuit CVAService en vang hem op in het endpoint; delegeer naar `handle_cva_value_error(e, "context omschrijving")` voor correcte HTTP status |

### Trainingssamenvatting

#### Flow: CVA ValueError Conversie

| Veld | Waarde |
|------|--------|
| Actor | CVA endpoint handler (cva_chat.py of cva_conversations.py) |
| Voorwaarde | CVAService heeft een `ValueError` opgegooid met een foutbericht |
| Actie | Endpoint roept `handle_cva_value_error(e, context)` aan in de `except ValueError` clausule |
| Systeemverwerking | Helper inspecteert `str(e).lower()` op "not found or access denied"; selecteert 404 of 422 |
| Succesrespons | `HTTPException` met juiste status code en `detail=f"{context}: {e}"` teruggegeven aan FastAPI |
| Foutrespons | Niet van toepassing -- helper gooit zelf nooit een exceptie |
| Uitzonderingen | Als een nieuwe CVAService fout op een andere status code moet mappen, breid de conditie in `handle_cva_value_error` uit en voeg een regression test toe |

---

## Integratorhandleiding

Callers importeren de helper als:

```python
from src.core.api.v1.cva.dependencies import handle_cva_value_error

try:
    result = await cva_service.some_operation(...)
except ValueError as e:
    raise handle_cva_value_error(e, "operation_name") from e
```

Geen API-contract wijzigingen -- de HTTP-foutresponses die clients ontvangen zijn identiek
aan de situatie voor deze refactor.

---

## Open aannames / Open vragen / Risico's

| Type | Omschrijving | Status |
|------|--------------|--------|
| Aanname | `cva_utils.py` wordt nog door andere modules gebruikt en mag niet verwijderd worden | Bevestigd -- import verplaatst in cva_chat.py en cva_conversations.py alleen |
| Aanname | Alle CVA ValueErrors volgen het patroon "not found or access denied" voor 404 gevallen | Bevestigd via code-inspectie |
| Risico | Geen -- puur refactor zonder gedragswijziging | Gesloten |

---

## QA-checks

- [x] `python -m py_compile src/core/api/v1/cva/dependencies.py` -- geen errors
- [x] `python -c "from src.core.api.v1.cva.dependencies import handle_cva_value_error; print('OK')"` -- importeert correct
- [x] `ruff check src/core/api/v1/cva/` -- 0 errors
- [x] `ruff check src/core/api/cva_chat.py src/core/api/cva_conversations.py` -- 0 errors
- [x] Geen regressies in bestaande CVA tests

---

## Definition of Done

- [x] `src/core/api/v1/cva/__init__.py` aangemaakt
- [x] `src/core/api/v1/cva/dependencies.py` aangemaakt met `handle_cva_value_error`
- [x] `cva_chat.py` en `cva_conversations.py` importeren vanuit nieuw module
- [x] Alle kwaliteitschecks groen
- [x] Feature spec aangemaakt (dit bestand)
- [x] Review APPROVED (`docs/backend/review/review-BE-UTL-037.md`)
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`
