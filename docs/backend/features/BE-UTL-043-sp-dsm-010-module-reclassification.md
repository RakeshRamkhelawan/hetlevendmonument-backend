# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-043
- Feature naam: SP-DSM-010 MODULE_MAP + SOURCE_DIRS reclassificatie (Grade A)
- Status: APPROVED
- Auteur: Claude (Sonnet 4.6)
- Reviewer: Claude (Sonnet 4.6)
- Datum: 2026-06-24
- Gerelateerde user story / ticket: SP-DSM-010 Dag 1
- Gerelateerde router / module: scripts/dsm_full_analysis.py
- Gerelateerde frontend endpoints: N/A
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

Elimineer het `[MEDIUM] agent_runtime <-> integrations` circulaire paar uit de DSM-analyse
door MODULE_MAP en SOURCE_DIRS in `scripts/dsm_full_analysis.py` te corrigeren zodat
bestanden die architectureel tot `agent_runtime` behoren, ook als zodanig worden geclassificeerd.
Resultaat: DSM Grade A (0 MEDIUM circulaire paren).

### In scope

- MODULE_MAP reclassificaties voor 5 submodules: `src.core.collaboration`,
  `src.core.events.handlers`, `src.core.events.learning_event_wiring`,
  `src.core.activepieces.indexer`, `src.core.protocol`
- SOURCE_DIRS aanpassingen: bovengenoemde bestanden verwijderd uit `integrations`,
  toegevoegd aan `agent_runtime`
- Nieuwe architecture test: `test_dsm_010_no_integrations_agent_runtime_circular.py`
- Bijgewerkte tracking test: `test_dsm_medium_pairs_tracking.py`

### Out of scope

- Productiecodwijzigingen (geen)
- Alembic-migraties (geen)
- API-endpoints (geen)
- Frontend-wijzigingen (geen)
- Daadwerkelijk refactoren van de imports in de betreffende modules

---

## Build summary

- Nieuw gebouwd: `tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py`
- Gewijzigd: `scripts/dsm_full_analysis.py`, `tests/architecture/test_dsm_medium_pairs_tracking.py`
- Verwijderd: geen
- Beinvloede bestaande flows: DSM-analyse pijplijn (scan_module + classify), architecture test suite

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-036-A | MODULE_MAP reclassificaties | Utility config | `scripts/dsm_full_analysis.py` | Wijziging | DSM-analyse |
| BE-UTL-036-B | SOURCE_DIRS reclassificaties | Utility config | `scripts/dsm_full_analysis.py` | Wijziging | DSM-analyse |
| BE-UTL-036-C | test_dsm_010 architecture test | Test | `tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py` | Nieuw | Architecture gate |
| BE-UTL-036-D | tracking test update (heen max 33) | Test | `tests/architecture/test_dsm_medium_pairs_tracking.py` | Wijziging | Architecture gate |

---

## API-flows

N/A -- geen API-endpoints betrokken. Dit is een puur analytisch en architectureel hulpmiddel.

---

## Detaildocumentatie per artefact

---

## [BE-UTL-036-A] MODULE_MAP reclassificaties in dsm_full_analysis.py

### 1. Type

- Configuratiewijziging in analyse-utility

### 2. Locatie

- Bestandspad: `scripts/dsm_full_analysis.py`
- Klasse / functie: `MODULE_MAP` (dict, globaal)

### 3. Gerelateerde flow

- DSM-analyse: `python scripts/dsm_full_analysis.py` output

### 4. Doel

Importdoelen (strings zoals `src.core.collaboration`) correct toewijzen aan de
DSM-module (`agent_runtime`) zodat `classify()` ze via longest-prefix-matching
niet meer als `integrations` classificeert.

### 5. Functionele beschrijving

Vijf submodules werden als `integrations` geclassificeerd terwijl ze structureel
tot `agent_runtime` behoren:

| Submodule | Reden herclassificatie |
|-----------|----------------------|
| `src.core.collaboration` | `task_distributor.py` importeert `src.core.agents.*` en `src.core.ai` (agent_runtime-modules) |
| `src.core.events.handlers` | `learning_event_handler.py` en `workflow_handler.py` importeren uit `learning_loop` en `als.enterprise` (agent_runtime) |
| `src.core.events.learning_event_wiring` | Wired learning event handlers — puur agent_runtime-concern |
| `src.core.activepieces.indexer` | `indexer.py` importeert `src.core.memory.memory_manager` (agent_runtime) |
| `src.core.protocol` | Alle 4 bestanden in `protocol/` afhankelijk van agent_runtime-structuren; `unified_message_protocol.py` had circulaire afhankelijkheid met `collaboration` |

### 6. Technische beschrijving

`classify(module_str)` gebruikt longest-prefix matching over alle MODULE_MAP-sleutels.
Nieuwe/gewijzigde sleutels (in volgorde van specificiteit):

```python
# Toegevoegd (specifiek voor indexer, overschrijft src.core.activepieces = integrations):
"src.core.activepieces.indexer": "agent_runtime"

# Toegevoegd (specifiek voor handlers/, overschrijft src.core.events = integrations):
"src.core.events.handlers": "agent_runtime"

# Gewijzigd (was: integrations):
"src.core.protocol": "agent_runtime"

# Gewijzigd (was: integrations):
"src.core.collaboration": "agent_runtime"
```

`src.core.events.learning_event_wiring` wordt geclassificeerd via
`src.core.events` (integrations) TENZIJ expliciet in SOURCE_DIRS["agent_runtime"]
opgenomen (zie BE-UTL-036-B).

### 7. Zichtbaarheids- en toegangsregels

- Geen authenticatie/autorisatie van toepassing
- Alleen relevant voor lokale DSM-analyse en CI architecture tests

### 8. t/m 16. (N/A voor non-API utility)

Niet van toepassing. Geen endpoints, geen DB-operaties, geen caching, geen middleware.

### 17. Acceptatiecriteria

- `scan_module("integrations", SOURCE_DIRS["integrations"])` retourneert
  `counts.get("agent_runtime", 0) == 0` (geen backward deps)
- `python scripts/dsm_full_analysis.py` output: 0 MEDIUM circulaire paren
- DSM Grade = A in output
- `pytest tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py` GROEN
- `pytest tests/architecture/test_dsm_medium_pairs_tracking.py` GROEN

### 18. Integratoruitleg

- Voeg nieuwe submodules die agent_runtime-imports bevatten toe aan MODULE_MAP met prefix
  specifieker dan hun bovenliggende module
- Verwijder de map/het bestand uit SOURCE_DIRS["integrations"] en voeg toe aan
  SOURCE_DIRS["agent_runtime"]
- Controleer altijd of reclassificatie geen nieuwe backward deps introduceert via andere
  bestanden die de herclassificeerde submodule importeren

### 19. Trainingssamenvatting

- Actor: DSM-analyse tool (scripts/dsm_full_analysis.py)
- Voorwaarde: MODULE_MAP bevat incorrecte module-classificaties voor submodules die
  agent_runtime-imports bevatten terwijl hun bovenliggende module als integrations is geclassificeerd
- Actie (request): `python scripts/dsm_full_analysis.py` of
  `pytest tests/architecture/` uitvoeren
- Systeemverwerking: classify() gebruikt longest-prefix matching; scan_module() telt
  cross-module imports per bronbestand; DSM-rapport aggregeert heen+terug per paar
- Succesrespons: Grade A (0 MEDIUM/KRITIEK circulaire paren); backward dep
  integrations->agent_runtime = 0
- Foutrespons: Grade B of lager als backward deps > 0; test ROOD als
  integrations->agent_runtime > 0
- Uitzonderingen: reclassificatie kan cascade-effect hebben op heen-counts van
  de doelmodule; altijd tracking test bijwerken na reclassificatie

---

## [BE-UTL-036-B] SOURCE_DIRS reclassificaties in dsm_full_analysis.py

### 1. Type

- Configuratiewijziging in analyse-utility

### 2. Locatie

- Bestandspad: `scripts/dsm_full_analysis.py`
- Klasse / functie: `SOURCE_DIRS` (dict, globaal)

### 4. Doel

SOURCE_DIRS bepaalt welke bestanden als bronbestanden voor een module worden gescand.
MODULE_MAP classificeert importdoelen. Beide moeten consistent zijn.

### 5. Functionele beschrijving

SOURCE_DIRS["integrations"] is aangepast: `src/core/collaboration` en
`src/core/protocol` zijn verwijderd als directory-paden. In hun plaats zijn de
activepieces/-bestanden individueel opgesomd (om `indexer.py` uit te sluiten) en
de events/-bestanden individueel opgesomd (om `handlers/` en
`learning_event_wiring.py` uit te sluiten).

SOURCE_DIRS["agent_runtime"] is uitgebreid met:
- `src/core/collaboration`
- `src/core/events/handlers`
- `src/core/events/learning_event_wiring.py`
- `src/core/activepieces/indexer.py`
- `src/core/protocol`

### 6. Technische beschrijving

```python
SOURCE_DIRS["integrations"] = [
    # activepieces individueel (indexer.py -> agent_runtime):
    "src/core/activepieces/__init__.py",
    "src/core/activepieces/catalog_syncer.py",
    # ... (10 bestanden, niet indexer.py)
    "src/core/integrations",
    # protocol verwijderd -> agent_runtime
    "src/core/connectors",
    "src/core/communication",
    "src/core/notifications",
    # events individueel (handlers/ en learning_event_wiring.py -> agent_runtime):
    "src/core/events/__init__.py",
    "src/core/events/consumer.py",
    # ... (6 bestanden, niet handlers/ en niet learning_event_wiring.py)
    "src/core/websocket",
    # collaboration verwijderd -> agent_runtime
    "src/core/session",
    # ...
]

SOURCE_DIRS["agent_runtime"].extend([
    "src/core/collaboration",
    "src/core/events/handlers",
    "src/core/events/learning_event_wiring.py",
    "src/core/activepieces/indexer.py",
    "src/core/protocol",
])
```

### 17. Acceptatiecriteria

- Scan van SOURCE_DIRS["integrations"] bevat geen `collaboration/`,
  `protocol/`, `events/handlers/` of `events/learning_event_wiring.py` paden
- Scan van SOURCE_DIRS["agent_runtime"] bevat bovengenoemde paden wel
- `pytest tests/architecture/ -q` toont 218 passed, 0 failed

---

## [BE-UTL-036-C] test_dsm_010_no_integrations_agent_runtime_circular.py

### 1. Type

- Architecture test (pytest)

### 2. Locatie

- Bestandspad: `tests/architecture/test_dsm_010_no_integrations_agent_runtime_circular.py`

### 4. Doel

Garandeert dat `integrations -> agent_runtime` (backward SDP-schending) permanent 0 blijft.
CI faalt zodra een toekomstige reclassificatie of nieuw bestand deze invariant schendt.

### 5. Functionele beschrijving

Importeert `scan_module` en `SOURCE_DIRS` uit `scripts/dsm_full_analysis.py`,
roept `scan_module("integrations", ...)` aan, en asserteert dat
`counts.get("agent_runtime", 0) == 0`.

### 17. Acceptatiecriteria

- Test GROEN op commit SP-DSM-010 dag 1
- Test wordt ROOD als een bestand met agent_runtime-import aan
  SOURCE_DIRS["integrations"] wordt toegevoegd

### 19. Trainingssamenvatting

- Actor: CI / pytest architecture suite
- Voorwaarde: SOURCE_DIRS["integrations"] bevat bestanden die agent_runtime importeren
- Actie: `pytest tests/architecture/test_dsm_010*`
- Systeemverwerking: scan_module() telt imports per module-categorie
- Succesrespons: 1 passed
- Foutrespons: AssertionError met integrations->agent_runtime count
- Uitzonderingen: test faalt ook bij toevoeging van een nieuw integrations-bestand dat
  per ongeluk een agent_runtime-module importeert

---

## Integratorhandleiding

### Voor ontwikkelaars die de DSM-analyse uitvoeren

1. Voer `python scripts/dsm_full_analysis.py` uit voor een volledig DSM-rapport.
2. Grade A = 0 MEDIUM/KRITIEK paren. Grade B = 1+ MEDIUM paren.
3. Voeg nieuwe modules toe aan MODULE_MAP met specifiekere prefix dan de bovenliggende
   module als ze een andere module-categorie behoren.
4. Pas SOURCE_DIRS aan om te garanderen dat scan en classificatie consistent zijn.
5. Draai altijd `pytest tests/architecture/ -q` na elke wijziging aan dsm_full_analysis.py.

---

## Open aannames

- `src.core.events.learning_event_wiring` heeft geen eigen MODULE_MAP-sleutel;
  het wordt alleen via SOURCE_DIRS["agent_runtime"] uit integrations-scan gehouden.
  Als een toekomstige import classify() aanroept op dit pad, valt het terug op
  `src.core.events = integrations`. Risico: laag (bestanden worden gescand als bron,
  niet als importdoel in praktijk).

## Open vragen

- Geen.

## Risico's

- Laag: toekomstige toevoeging van bestanden in `src/core/events/` kan
  learning_event_wiring.py-patroon breken als niet individueel opgesomd.
  Mitigatie: architecture test detecteert dit direct.

---

## QA-checks

- [x] Analyse-tool functioneel getest (DSM-rapport Grade A geproduceerd)
- [x] Architecture tests GROEN (218 passed, 0 failed)
- [x] Pyright gate: 0 errors
- [x] Ruff gate: 0 errors
- [x] Geen productiewijzigingen (alleen scripts/ en tests/architecture/)
- [x] Backward dep integrations->agent_runtime = 0 geverifieerd
- [x] Heen-count agent_runtime->integrations = 33 (max 33 in tracking test)

---

## Definition of Done

- [x] Reclassificaties doorgevoerd in scripts/dsm_full_analysis.py
- [x] Architecture test aangemaakt (RED -> GREEN)
- [x] Tracking test bijgewerkt (heen max 33, terug == 0)
- [x] DSM Grade A bevestigd via scripts/dsm_full_analysis.py output
- [x] 218 architecture tests GROEN, 0 failed
- [x] Pyright baseline (0 errors) gehandhaafd
- [x] Feature-spec aangemaakt (dit document)
- [x] Review: APPROVED (zie review-BE-UTL-036.md)
- [x] ID-REGISTRY bijgewerkt
