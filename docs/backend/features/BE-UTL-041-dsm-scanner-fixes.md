# Backend Feature Specification

## Metadata

- **Feature ID:** BE-UTL-041
- **Feature naam:** DSM Scanner Fixes — double-prefix normalisatie en module-classificatie
- **Status:** Completed
- **Auteur:** Kimi Code CLI
- **Reviewer:** (subagent review — zie `docs/backend/review/review-BE-UTL-041.md`)
- **Datum:** 2026-06-13
- **Gerelateerde user story / ticket:** SP-DSM-SCANNER-FIXES Day 1
- **Gerelateerde router / module:** `scripts/dsm_full_analysis.py`
- **Gerelateerde frontend endpoints:** n.v.t.
- **Gerelateerde database tabellen:** n.v.t.
- **Versie:** 1.0

---

## Doel en scope

### Doel

De DSM-scanner (`scripts/dsm_full_analysis.py`) genereert een gewogen afhankelijkheidsmatrix over de Python-broncode. Deze matrix is input voor architectuur-audits en het beheersen van koppelingen. De scanner rapporteerde twee categorieën vervuiling:

1. **Double-prefix artifacts** — imports als `src.core.src.config` en `src.core.src.main` door verkeerde module-resolutie.
2. **Unclassified modules** — imports die niet in `MODULE_MAP` voorkwamen en daarom als `Ongeclassificeerd` werden afgedrukt.

Dit feature fixt beide problemen zodat de DSM-output betrouwbaarder wordt en minder handmatige interpretatie vereist.

### In scope

- Normalisatie van `src.core.src.*` imports naar `src.*` vóór classificatie.
- Toevoegen van 8 voorheen ongeclassificeerde module-mappings aan `MODULE_MAP`.
- Toevoegen van de bijbehorende bronmappen aan `SOURCE_DIRS`.
- Ondersteuning voor losse Python-bestanden (bijv. `src/core/container.py`) in `SOURCE_DIRS`.
- Regressietests in `tests/architecture/test_dsm_scanner_fixes.py`.
- `architecture` pytest-marker registratie in `pyproject.toml`.

### Out of scope

- Opnieuw indelen van bestaande modules die al correct geclassificeerd zijn.
- Oplossen van overige ongeclassificeerde imports buiten de 8 gemelde modules (bijv. `src.ml.*`, `src.services.*`). Deze blijven zichtbaar in de scanner-output voor toekomstige audits.

---

## Build summary

- **Nieuw gebouwd:**
  - `tests/architecture/test_dsm_scanner_fixes.py` — regressietests voor double-prefix en module-mapping.
- **Gewijzigd:**
  - `scripts/dsm_full_analysis.py` — `MODULE_MAP`, `SOURCE_DIRS`, `scan_module()`.
  - `pyproject.toml` — registratie `architecture` marker.
- **Verwijderd:** n.v.t.
- **Beïnvloede bestaande flows:** architecture-fitness testrun in `scripts/ci-local-fast.sh` (alleen nieuwe tests toegevoegd).

---

## Backend inventory

| ID         | Naam                              | Type    | Bestandspad                                              | Nieuw/Wijziging | Gerelateerde flow |
| ---------- | --------------------------------- | ------- | -------------------------------------------------------- | --------------- | ----------------- |
| BE-UTL-041 | DSM Scanner Fixes                 | Utility | `scripts/dsm_full_analysis.py`                           | Wijziging       | DSM-scan          |
| BE-UTL-041a| Double-prefix normalisatie        | Utility | `scripts/dsm_full_analysis.py` (`scan_module`)           | Wijziging       | DSM-scan          |
| BE-UTL-041b| Module-mapping uitbreiding        | Utility | `scripts/dsm_full_analysis.py` (`MODULE_MAP`)            | Wijziging       | DSM-scan          |
| BE-UTL-041c| Bronmap-mapping uitbreiding       | Utility | `scripts/dsm_full_analysis.py` (`SOURCE_DIRS`)           | Wijziging       | DSM-scan          |
| BE-UTL-041d| Bestandsondersteuning SOURCE_DIRS | Utility | `scripts/dsm_full_analysis.py` (`scan_module`)           | Wijziging       | DSM-scan          |
| BE-UTL-041e| DSM scanner regressietests        | Test    | `tests/architecture/test_dsm_scanner_fixes.py`           | Nieuw           | DSM-scan          |

---

## API-flows

Geen HTTP-flows; dit is een offline analyse-script.

---

## Detaildocumentatie per artefact

---

### [BE-UTL-041] DSM Scanner Fixes

#### 1. Type

Python-utility / architectuur-analyse-script.

#### 2. Locatie

- **Bestandspad:** `scripts/dsm_full_analysis.py`
- **Klasse / functie:** `classify()`, `scan_module()`, datastructuren `MODULE_MAP` en `SOURCE_DIRS`.

#### 3. Gerelateerde flow

DSM-scan — wordt handmatig of in CI uitgevoerd via `python scripts/dsm_full_analysis.py`.

#### 4. Doel

Zorgen dat de gewogen afhankelijkheidsmatrix alle `src.*` imports correct classificeert, zonder double-prefix artifacts en zonder dat relevante modules als ongeclassificeerd worden getoond.

#### 5. Functionele beschrijving

De scanner loopt over de bronmappen heen, parseert elke `.py` met `ast`, en telt voor elke bron-bucket hoe vaak er naar andere buckets geïmporteerd wordt. Imports die niet in `MODULE_MAP` staan, worden als `Ongeclassificeerd` gerapporteerd.

Na deze wijziging:

- Imports die per ongeluk beginnen met `src.core.src.` worden eerst genormaliseerd naar `src.*` zodat ze op de bestaande mapping vallen.
- De volgende 8 modules hebben een expliciete bucket gekregen:

| Module                  | Bucket      | Rationale                                              |
| ----------------------- | ----------- | ------------------------------------------------------ |
| `src.core.container`    | `infra`     | DI-container / applicatie-infrastructuur               |
| `src.core.dependencies` | `infra`     | Gedeelde FastAPI-afhankelijkheden                      |
| `src.domains.canvas`    | `domain_pack`| Domein-specifieke canvas-bedrijfslogica                |
| `src.domains.documents` | `domain_pack`| Document-domein                                        |
| `src.domains.projects`  | `domain_pack`| Project-domein                                         |
| `src.domains.memory`    | `agent_runtime`| Digital Twin / agent-geheugen runtime                  |
| `src.domains.flows`     | `agent_runtime`| Agent-flow runtime                                     |
| `src.domains.agentic`   | `agent_runtime`| Agentic experimentatie-runtime                         |

- `src.core.memory` is van `integrations` naar `agent_runtime` verplaatst.
- `src.config` en `src.main` (uit double-prefix artifacts) zijn gemapt naar respectievelijk `infra` en `core_api`.

#### 6. Technische beschrijving

**Double-prefix normalisatie**

In `scan_module`, direct na het uitlezen van `node.module`:

```python
mod = node.module
if mod.startswith("src.core.src."):
    mod = "src." + mod[len("src.core.src."):]
```

Dit transformeert bijvoorbeeld `src.core.src.config` naar `src.config`, waarna de bestaande mapping `src.config -> infra` matched.

**Module-mapping**

Aan `MODULE_MAP` zijn de volgende entries toegevoegd:

```python
"src.core.container": "infra",
"src.core.dependencies": "infra",
"src.domains.canvas": "domain_pack",
"src.domains.documents": "domain_pack",
"src.domains.projects": "domain_pack",
"src.domains.memory": "agent_runtime",
"src.domains.flows": "agent_runtime",
"src.domains.agentic": "agent_runtime",
"src.config": "infra",
"src.main": "core_api",
```

Daarnaast is `src.core.memory` gewijzigd van `integrations` naar `agent_runtime`.

**Bronmap-mapping**

Aan `SOURCE_DIRS`:

- `agent_runtime`: `src/domains/memory`, `src/domains/flows`, `src/domains/agentic`
- `domain_pack`: `src/domains/canvas`, `src/domains/documents`, `src/domains/projects`
- `infra`: `src/core/container.py`, `src/core/dependencies.py`

**Bestandsondersteuning**

`scan_module` accepteert nu zowel directories als losse bestanden in `SOURCE_DIRS`:

```python
paths = [p] if p.is_file() else list(p.rglob("*.py"))
```

Hierdoor kunnen `container.py` en `dependencies.py` als bron-bestanden voor de `infra`-bucket meetellen zonder dat de hele `src/core` map wordt herclassificeerd.

#### 7. Zichtbaarheids- en toegangsregels

- **Vereiste authenticatie:** n.v.t. (lokaal script)
- **Vereiste rol / scope:** n.v.t.
- **Tenant-isolatie:** n.v.t.
- **Feature flag:** n.v.t.

#### 8. Request-specificatie

Niet van toepassing (geen HTTP).

#### 9. Response-specificatie

Niet van toepassing (stdout/CLI).

#### 10. Validaties en constraints

- `classify()` gebruikt longest-prefix matching; expliciet toegevoegde mappings overschrijven dus geen bestaande langere prefixes.
- `src.core.memory` wijziging naar `agent_runtime` is bewust; de module bevat Digital Twin / agent-geheugendiensten die beter in `agent_runtime` passen dan in `integrations`.

#### 11. Business rules

- De DSM-output wordt gebruikt voor architectuur-beslissingen; correcte classificatie is daarom essentieel.
- Test-bestanden blijven uitgesloten (`any("test" in part.lower() ...)`).

#### 12. Afhankelijkheden

- Python 3.13
- `ast`, `collections`, `pathlib` (std-lib)

#### 13. Foutafhandeling

- Niet-parseerbare bestanden worden overgeslagen (`except Exception: continue`).
- Niet-bestaande paden in `SOURCE_DIRS` worden overgeslagen.
- Imports die na normalisatie nog steeds niet in `MODULE_MAP` staan, blijven als ongeclassificeerd gerapporteerd.

#### 14. Transacties en dataïntegriteit

Geen database-transacties; alleen leesoperaties op bronbestanden.

#### 15. Telemetry / logging / tracing

Geen extra logging toegevoegd; script print bestaande matrix naar stdout.

#### 16. Caching

Geen caching.

#### 17. Acceptatiecriteria

- [x] `scripts/dsm_full_analysis.py` loopt zonder excepties door de volledige `src/` boom.
- [x] `src.core.src.config` en `src.core.src.main` komen niet meer voor in de ongeclassificeerde output.
- [x] De 8 gemelde modules (`container`, `canvas`, `memory`, `flows`, `documents`, `agentic`, `dependencies`, `projects`) komen niet meer voor in de ongeclassificeerde top-10.
- [x] `tests/architecture/test_dsm_scanner_fixes.py` bevat twee rode tests vóór de fix en is groen na de fix.
- [x] `pyproject.toml` bevat de geregistreerde `architecture` pytest-marker.

#### 18. Integratoruitleg

- Voer de scanner uit met `python scripts/dsm_full_analysis.py`.
- Controleer de sectie `Ongeclassificeerde src.core.* imports`; de 8 target modules mogen hier niet meer in staan.
- De regressietests draaien met `pytest tests/architecture/test_dsm_scanner_fixes.py -m architecture`.

#### 19. Trainingssamenvatting

| Onderdeel           | Inhoud                                                       |
| ------------------- | ------------------------------------------------------------ |
| Actor               | Developer / architect                                        |
| Voorwaarde          | Lokale checkout met `src/` en `.venv`                        |
| Actie (request)     | `python scripts/dsm_full_analysis.py`                        |
| Systeemverwerking   | AST-walk, double-prefix normalisatie, module-classificatie   |
| Succesrespons       | Gewogen DSM-matrix zonder target modules in ongeclassificeerd|
| Foutrespons         | Niet-parseerbare bestanden worden overgeslagen               |
| Uitzonderingen      | Overige ongeclassificeerde imports blijven zichtbaar         |

---

## QA-checks

| Check | Methode | Status |
|-------|---------|--------|
| Alle 11 regressietests groen | `pytest tests/architecture/test_dsm_scanner_fixes.py -v` | ✅ |
| Scanner loopt zonder excepties | `python scripts/dsm_full_analysis.py` | ✅ |
| 8 target modules niet meer in ongeclassificeerde top-10 | Inspectie scanner-output | ✅ |
| Double-prefix artifacts niet meer in ongeclassificeerde output | Inspectie scanner-output | ✅ |
| `src.core.memory` niet meer in `integrations` `SOURCE_DIRS` | Inspectie `scripts/dsm_full_analysis.py` | ✅ |
| `architecture` marker geregistreerd | Inspectie `pyproject.toml` | ✅ |
| ID geregistreerd in `ID-REGISTRY.md` | Inspectie `docs/backend/features/ID-REGISTRY.md` | ✅ |

## Definition of Done

- [x] Implementatie afgerond en getest.
- [x] Feature-specificatie opgeslagen in `docs/backend/features/BE-UTL-041-dsm-scanner-fixes.md`.
- [x] Review opgeslagen in `docs/backend/review/review-BE-UTL-041.md` met eindoordeel **APPROVED**.
- [x] ID geregistreerd in `docs/backend/features/ID-REGISTRY.md`.
- [x] Regressietests groen.
- [x] Scanner produceert correcte output zonder excepties.

## Open vragen / aannames

- De mapping van `src.core.memory` van `integrations` naar `agent_runtime` is gebaseerd op de functie van de module (Digital Twin / agent-geheugen). Als de architectuur deze module elders wil plaatsen, kan `MODULE_MAP` en `SOURCE_DIRS` eenvoudig worden aangepast.
- Overige ongeclassificeerde imports (`src.ml.*`, `src.services.*`, `src.core.metrics`, etc.) zijn bewust buiten scope gelaten; deze vereisen een afzonderlijke DSM-audit.
