# BE-DSM-045: SP-DSM-021 Dag 5 -- shared.types sub-laag + sprint DSM-ARCH-004 afsluiting

## Status

APPROVED

## Sprint

SP-DSM-021 Dag 5 (laatste dag)

## Datum

2026-06-27

## Samenvatting

DSM-ARCH-004 volledig: 4 thematische sub-lagen van shared geintroduceerd over 3 dagen.
Dag 5 voegt `shared.types` toe (ai_act_types.py + consent_categories.py, Ce=0)
en sluit de sprint af met een finale DSM-scorecard (15 modules, Grade A+ gehandhaafd).

## Deliverables Dag 5

### 1. Gewijzigd: scripts/dsm_full_analysis.py

**MODULE_MAP toevoegingen** (na unicode_logging regel):
```python
"src.core.shared.ai_act_types": "shared.types",  # SP-DSM-021 dag 5: AI Act type definitions -- pure stdlib, Ce=0
"src.core.shared.consent_categories": "shared.types",  # SP-DSM-021 dag 5: consent category enums -- pure stdlib, Ce=0
# NOTE: interfaces.py stays in shared -- Ce=2 (imports src.core.types + src.core.shared.agent_context)
```

**SOURCE_DIRS toevoeging** (na shared.utils blok):
```python
"shared.types": [
    "src/core/shared/ai_act_types.py",
    "src/core/shared/consent_categories.py",
    # NOTE: interfaces.py excluded -- Ce=2 (imports src.core.types + src.core.shared.agent_context)
],
```

**MODULES, main() short-dict, generate_html() short lijst** -- bijgewerkt met "shared.types" / "sh.typ".

### 2. Uitgebreid: tests/architecture/test_dsm021_shared_sublayers.py

Twee nieuwe arch-tests (totaal nu 6):
- `test_dsm021_shared_types_in_modules_list`: shared.types aanwezig in MODULES
- `test_dsm021_shared_types_ce_is_zero`: Ce==0 invariant voor shared.types bestanden

### 3. Kandidaten-evaluatie shared.types

| Bestand | Ce=0? | Intra-shared dep? | Opgenomen |
|---------|-------|--------------------|-----------|
| ai\_act\_types.py | ja | nee | ja |
| consent\_categories.py | ja | nee | ja |
| interfaces.py | nee (Ce=2) | n.v.t. | nee -- blijft in shared |

`interfaces.py` importeert `src.core.types` en `src.core.shared.agent_context` -- reclassificatie
zou shared.types Ce>0 maken en daarmee de Ce=0 invariant breken.

---

## Sprint DSM-ARCH-004: Finale Scorecard

### DSM Metrics Overzicht (15 modules)

| Module | Bestanden | fan-out (Ce_excl) | fan-in (Ca) | I | Oordeel |
|--------|-----------|-------------------|-------------|---|---------|
| tenancy | 18 | 10 | 20 | 0.333 | LAAG |
| auth | 63 | 23 | 272 | 0.078 | LAAG |
| governance | 50 | 9 | 63 | 0.125 | LAAG |
| agent_runtime | 902 | 185 | 182 | 0.504 | MEDIUM |
| llm | 24 | 4 | 41 | 0.089 | LAAG |
| tool_broker | 34 | 11 | 29 | 0.275 | LAAG |
| worker | 2 | 0 | 12 | 0.000 | minimaal |
| domain_pack | 106 | 15 | 69 | 0.179 | LAAG |
| core_api | 536 | **758** | 1 | 0.999 | KRITIEK (bewust: entry-point) |
| infra | 151 | 0 | 292 | 0.000 | LAAG |
| shared | 56 | **0** | 1151 | 0.000 | KRITIEK fan-in (bewust: foundation) |
| shared.time | 1 | 0 | 0 | 0.000 | minimaal |
| shared.utils | 2 | 0 | 0 | 0.000 | minimaal |
| shared.types | 2 | 0 | 0 | 0.000 | minimaal |
| integrations | 77 | 40 | 74 | 0.351 | MEDIUM |

### Grade A+ Criteria

| Criterium | Waarde | Status |
|-----------|--------|--------|
| core_api Ce_excl | 758 <= 800 | **PASS** |
| Circulaire paren | 1 (core_api <-> governance, MEDIUM, pre-existing) | **PASS** (geen nieuwe) |
| shared Ce | 0 | **PASS** |
| shared.time Ce | 0 | **PASS** |
| shared.utils Ce | 0 | **PASS** |
| shared.types Ce | 0 | **PASS** |

**Grade A+ gehandhaafd.**

### Circulaire dependencies

```
[MEDIUM] core_api <-> governance: 45 heen / 1 terug  (pre-existing, backlog)
```

### Arch-suite finale meting

| Metriek | Waarde |
|---------|--------|
| Passed | 278 |
| Failed | 4 (alle pre-existing) |
| Xfailed | 12 |
| Nieuwe tests SP-DSM-021 | 6 (+2 per dag) |

---

## DSM-ARCH-004 Sprint Samenvatting

### Wat bereikt is

| Dag | Sub-laag | Bestanden | Ce | Beslissingsmoment |
|-----|----------|-----------|-----|------------------|
| Dag 3 | shared.time | datetime\_utils.py | 0 | Geen intra-shared deps |
| Dag 4 | shared.utils | unicode\_utils.py + unicode\_logging.py | 0 | docker\_utils uitgesloten (intra-shared dep config.py) |
| Dag 5 | shared.types | ai\_act\_types.py + consent\_categories.py | 0 | interfaces.py uitgesloten (Ce=2) |

### Patronen vastgelegd

1. **MODULE_MAP asymmetrie**: longest-prefix matching in `classify()` -- specifiekere MODULE_MAP
   entry wint van de parent-prefix. Bewezen patroon, nu 4x toegepast voor shared sub-lagen.

2. **Ce=0 invariant via arch-test**: elke sub-laag heeft een `test_dsm021_shared_<naam>_ce_is_zero`
   die permanent afdwingt dat geen src.* imports worden toegevoegd.

3. **Intra-shared dep check**: voor elk candidate bestand controleren of andere shared-bestanden
   het importeren. Als ja: reclassificatie verbreekt shared Ce=0. Bewijs: docker_utils + interfaces.py.

4. **Criteria voor uitsluiting** (documenteer altijd in MODULE_MAP NOTE):
   - Intra-shared dep (andere shared file importeert het) -> stays in shared
   - Ce > 0 (bestand importeert zelf src.*) -> stays in shared

### Wat open blijft (backlog)

| Item | Reden | Pad |
|------|-------|-----|
| docker_utils.py reclassificatie | config.py intra-shared dep -- oplossing vereist refactor | Backlog |
| interfaces.py reclassificatie | Ce=2 (src.core.types + agent_context) -- oplossing vereist refactor | Backlog |
| core_api <-> governance circulaire dep | 45 edges -- grote refactor | Backlog |

## Pyright

0 errors (baseline 0 gehandhaafd gedurende de hele sprint).

## Arch-tests Overzicht (SP-DSM-021)

| Test | Status | Dag |
|------|--------|-----|
| `test_dsm021_shared_time_in_modules_list` | PASS | Dag 3 |
| `test_dsm021_shared_time_ce_is_zero` | PASS | Dag 3 |
| `test_dsm021_shared_utils_in_modules_list` | PASS | Dag 4 |
| `test_dsm021_shared_utils_ce_is_zero` | PASS | Dag 4 |
| `test_dsm021_shared_types_in_modules_list` | PASS | Dag 5 |
| `test_dsm021_shared_types_ce_is_zero` | PASS | Dag 5 |
| Arch-suite totaal | 278 passed, 4 failed (pre-existing) | Dag 5 |

## Trainingssamenvatting

### shared sub-lagen toevoegen (DSM-ARCH-004 patroon)

**Actor:** Architect / engineer die een nieuw bestand toevoegt aan src/core/shared/
**Voorwaarde:** Nieuw bestand heeft Ce=0 (geen src.* imports) EN wordt niet geimporteerd door
  andere bestanden in src/core/shared/ (geen intra-shared dep)
**Actie:** Engineer voegt MODULE_MAP entry toe + voegt bestand toe aan SOURCE_DIRS["shared.<naam>"]
  Kiest de juiste sub-laag op basis van semantiek: time / utils / types
**Systeemverwerking:** DSM-analyse scant het bestand als onderdeel van de sub-laag;
  Ce=0 arch-test valideert de invariant; test_shared_fan_out_is_zero valideert shared Ce=0
**Succesrespons:** alle arch-tests GROEN -- sub-laag Ce=0, shared Ce=0
**Foutrespons:** test ROOD:
  (1) sub-laag Ce > 0: bestand importeert src.* -- verwijder MODULE_MAP entry of fix import
  (2) shared Ce > 0 na toevoeging: intra-shared dep gevonden -- verwijder MODULE_MAP entry
**Uitzonderingen:** als geen bestaande sub-laag past (time/utils/types), beslis of een nieuwe
  sub-laag gerechtvaardigd is (min. 2 bestanden, duidelijke semantische grens)

## Gewijzigde bestanden

- `scripts/dsm_full_analysis.py` (MODULE_MAP + SOURCE_DIRS + MODULES + short-dict + generate_html)
- `tests/architecture/test_dsm021_shared_sublayers.py` (2 nieuwe tests, totaal 6)
- `docs/backend/features/BE-DSM-045-sp-dsm-021-dag5-sprint-afsluiting.md` (dit bestand)
- `docs/backend/review/review-BE-DSM-045.md` (nieuw)
- `docs/backend/features/ID-REGISTRY.md` (bijgewerkt)
