# BE-DSM-044: SP-DSM-021 Dag 4 -- shared.utils sub-laag geintroduceerd

## Status

APPROVED

## Sprint

SP-DSM-021 Dag 4

## Datum

2026-06-27

## Samenvatting

DSM-ARCH-004 Dag 4: tweede thematische sub-laag van shared geintroduceerd.
`shared.utils` omvat `unicode_utils.py` en `unicode_logging.py` -- puur stdlib, Ce=0.
`docker_utils.py` uitgesloten: `src.core.shared.config` importeert het (intra-shared dep),
reclassificatie zou shared Ce=0 invariant breken.
Aanpak: MODULE_MAP asymmetrie (zelfde patroon als Dag 3). Geen productie-code verplaatst.
2 nieuwe arch-tests dwingen Ce=0 invariant af voor alle toekomstige toevoegingen aan shared.utils.

## Kandidaten-evaluatie

| Bestand | Ce=0? | Intra-shared dep? | Opgenomen in shared.utils |
|---------|-------|--------------------|--------------------------|
| unicode_utils.py | ja | nee | ja |
| unicode_logging.py | ja | nee | ja |
| docker_utils.py | ja | ja (config.py importeert het) | nee -- blijft in shared |

## Deliverables

### 1. Gewijzigd: scripts/dsm_full_analysis.py

**MODULE_MAP toevoeging** (na datetime_utils regel):
```python
"src.core.shared.unicode_utils": "shared.utils",  # SP-DSM-021 dag 4: string utilities -- pure stdlib, Ce=0
"src.core.shared.unicode_logging": "shared.utils",  # SP-DSM-021 dag 4: logging setup -- pure stdlib, Ce=0
# NOTE: docker_utils stays in shared -- src.core.shared.config imports it (intra-shared dep)
```

**SOURCE_DIRS toevoeging** (na shared.time blok):
```python
"shared.utils": [  # SP-DSM-021 dag 4: string/logging utilities sub-laag (Ce=0 invariant)
    "src/core/shared/unicode_utils.py",
    "src/core/shared/unicode_logging.py",
    # NOTE: docker_utils excluded -- intra-shared dep from config.py, stays in shared
],
```

**MODULES uitbreiding** (na shared.time):
```python
"shared.time",  # SP-DSM-021 dag 3: datetime utilities sub-laag
"shared.utils",  # SP-DSM-021 dag 4: string/docker/logging utilities sub-laag
```

**main() short-dict uitbreiding**:
```python
"shared.time": "sh.time",  # SP-DSM-021 dag 3
"shared.utils": "sh.u",    # SP-DSM-021 dag 4
```

**generate_html() short lijst** (FA-001 patroon, zelfde dag uitgebreid):
```python
"shr", "sh.t", "sh.u", "int",
```

### 2. Uitgebreid: tests/architecture/test_dsm021_shared_sublayers.py

Twee nieuwe arch-tests (totaal nu 4):
- `test_dsm021_shared_utils_in_modules_list`: shared.utils aanwezig in MODULES
- `test_dsm021_shared_utils_ce_is_zero`: Ce==0 invariant voor shared.utils bestanden

## DSM Metrics

| Metriek | Voor (Dag 3) | Na (Dag 4) |
|---------|-------------|-----------|
| MODULES lijst | 13 entries | 14 entries |
| shared fan-out (Ce) | 0 | **0** (gehandhaafd) |
| shared.utils fan-out (Ce) | n.v.t. | **0** |
| shared.utils fan-in (Ca) | n.v.t. | 0 (geen callers via volledige module-path) |
| Grade A+ (core_api Ce_excl) | 757 <= 800 | 757 <= 800 (ongewijzigd) |
| Arch-suite | 273 passed, 7 failed | 273 passed, 7 failed (+2) |

Noot: 7 failures zijn dezelfde pre-existing als voor Dag 3/Dag 4 (bevestigd via git stash-test).
De Dag 3 brief vermeldde "2 failed" omdat de meting de quarantine-tc tests oversloeg.

## Kritiek beslissingsmoment: docker_utils

Tijdens implementatie ontdekt dat `src.core.shared.config` `docker_utils` importeert.
Reclassificatie van docker_utils naar shared.utils zou `shared Ce=0` breken
(config.py scant als "shared", import-target wordt "shared.utils" = Ce=1).

Beslissing: docker_utils blijft in shared (ongewijzigde MODULE_MAP entry `src.core.shared -> shared`
vangt docker_utils op via de `src.core.shared` parent-prefix).

## Bewezen patroon (MODULE_MAP asymmetrie)

Identiek aan:
- `src.core.shared.datetime_utils -> shared.time` (Dag 3)
- `src.core.agents.models -> shared` (SP-DSM-017 dag 1)
- `src.core.governance.event_handlers -> integrations` (SP-DSM-012)

## Pyright

0 errors (baseline 0 gehandhaafd).

## Arch-tests

| Test | Status |
|------|--------|
| `test_dsm021_shared_time_in_modules_list` | PASS (dag 3) |
| `test_dsm021_shared_time_ce_is_zero` | PASS (dag 3) |
| `test_dsm021_shared_utils_in_modules_list` | PASS (nieuw, dag 4) |
| `test_dsm021_shared_utils_ce_is_zero` | PASS (nieuw, dag 4) |
| Arch-suite totaal | 273 passed, 7 failed (pre-existing) |

## Trainingssamenvatting

### shared.utils DSM sub-laag

**Actor:** Architect / engineer die een string- of logging-utility toevoegt aan src/core/shared/
**Voorwaarde:** Nieuw bestand wordt aangemaakt in src/core/shared/ met string/logging functionaliteit
  EN het wordt niet al geimporteerd door een ander bestand in src/core/shared/ (intra-shared dep check)
**Actie:** Engineer voegt bestand toe aan `SOURCE_DIRS["shared.utils"]` in scripts/dsm_full_analysis.py
  en voegt MODULE_MAP entry toe voor het specifieke bestand (shared.utils als waarde)
**Systeemverwerking:** DSM-analyse scant het bestand als onderdeel van shared.utils;
  arch-test `test_dsm021_shared_utils_ce_is_zero` valideert Ce=0;
  arch-test `test_shared_fan_out_is_zero` valideert dat shared Ce=0 gehandhaafd blijft
**Succesrespons:** beide tests GROEN -- shared.utils Ce=0, shared Ce=0
**Foutrespons:** test ROOD -- 2 mogelijke oorzaken:
  (1) shared.utils Ce > 0: bestand importeert src.*; verwijder of verplaats naar andere laag
  (2) shared Ce > 1 (ipv 0): bestand heeft intra-shared dep; verwijder MODULE_MAP entry voor dit bestand
**Uitzonderingen:** Bestanden die zowel string/logging als andere concerns combineren
  (bijv. string-util die ook db queries doet) horen NIET in shared.utils thuis;
  bestanden die door andere shared-bestanden worden geimporteerd mogen NIET worden gereclassificeerd

## Gewijzigde bestanden

- `scripts/dsm_full_analysis.py` (MODULE_MAP + SOURCE_DIRS + MODULES + short-dict + generate_html)
- `tests/architecture/test_dsm021_shared_sublayers.py` (2 nieuwe tests)
- `docs/backend/features/BE-DSM-044-sp-dsm-021-dag4-shared-utils-sublayer.md` (dit bestand)
- `docs/backend/review/review-BE-DSM-044.md` (nieuw)
- `docs/backend/features/ID-REGISTRY.md` (bijgewerkt)
