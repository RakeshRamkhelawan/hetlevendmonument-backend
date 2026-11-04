# BE-DSM-043: SP-DSM-021 Dag 3 -- shared.time sub-laag geintroduceerd

## Status

APPROVED

## Sprint

SP-DSM-021 Dag 3

## Datum

2026-06-26

## Samenvatting

DSM-ARCH-004 Dag 3: de eerste thematische sub-laag van shared geintroduceerd.
`shared.time` omvat `src/core/shared/datetime_utils.py` -- puur stdlib, Ce=0.
Aanpak: MODULE_MAP asymmetrie (bewezen patroon, identiek aan agents.models->shared
en governance.event_handlers->integrations). Geen productie-code verplaatst.
Arch-test afdwingt Ce=0 invariant voor alle toekomstige toevoegingen aan shared.time.

## Deliverables

### 1. Gewijzigd: scripts/dsm_full_analysis.py

**MODULE_MAP toevoeging:**
```python
"src.core.shared.datetime_utils": "shared.time",  # SP-DSM-021 dag 3: datetime utilities -- pure stdlib, Ce=0
```

**SOURCE_DIRS toevoeging:**
```python
"shared.time": [
    "src/core/shared/datetime_utils.py",
],
```

**MODULES uitbreiding:**
```python
"shared",
"shared.time",  # SP-DSM-021 dag 3: datetime utilities sub-laag
"integrations",
```

**main() short-dict uitbreiding:**
```python
"shared.time": "sh.time",  # SP-DSM-021 dag 3
```

### 2. Nieuw: tests/architecture/test_dsm021_shared_sublayers.py

Twee arch-tests:
- `test_dsm021_shared_time_in_modules_list`: shared.time aanwezig in MODULES
- `test_dsm021_shared_time_ce_is_zero`: Ce==0 invariant voor shared.time bestanden

## DSM Metrics

| Metriek | Voor | Na |
|---------|------|----|
| MODULES lijst | 12 entries | 13 entries |
| shared fan-out (Ce) | 0 | 0 |
| shared.time fan-out (Ce) | n.v.t. | **0** |
| shared.time fan-in (Ca) | n.v.t. | 0 (geen callers in productie) |
| Grade A+ (core_api Ce_excl) | 757 <= 800 | 757 <= 800 (ongewijzigd) |
| Arch-suite | 271 passed, 2 failed | 273 passed, 2 failed (+2) |

## Sub-laag keuze: datetime_utils als eerste

`src/core/shared/datetime_utils.py` is de ideale eerste candidate:
- Ce=0 bevestigd: importeert alleen `datetime`, `timezone`, `typing` (stdlib)
- 0 productie-callers via volledige module-path (grep bevestigd)
- Duidelijke semantische grens: puur datetime/timezone utilities
- Nul risico voor Ce-regressie van andere modules

## Bewezen patroon (MODULE_MAP asymmetrie)

Identiek aan:
- `src.core.agents.models -> shared` (overruled `src.core.agents -> agent_runtime`)
- `src.core.governance.event_handlers -> integrations` (overruled `src.core.governance -> governance`)
- `src.core.database.database -> shared` (SOURCE_DIRS asymmetrie met infra)

Longest-prefix matching in `classify()` zorgt dat datetime_utils correct als
"shared.time" wordt geclassificeerd, niet als "shared".

## Pyright

0 errors (baseline 0 gehandhaafd).

## Arch-tests

| Test | Status |
|------|--------|
| `test_dsm021_shared_time_in_modules_list` | PASS (nieuw) |
| `test_dsm021_shared_time_ce_is_zero` | PASS (nieuw) |
| Arch-suite totaal | 273 passed, 2 failed (pre-existing) |

## Trainingssamenvatting

### shared.time DSM sub-laag

**Actor:** Architect / engineer die een datetime utility toevoegt aan src/core/shared/
**Voorwaarde:** Nieuw bestand wordt aangemaakt in src/core/shared/ met datum/tijd functionaliteit
**Actie:** Engineer voegt bestand toe aan `SOURCE_DIRS["shared.time"]` in scripts/dsm_full_analysis.py
  en (optioneel) aan `MODULE_MAP` als het bestand een eigen sub-pad heeft
**Systeemverwerking:** DSM-analyse scant het bestand als onderdeel van shared.time;
  arch-test `test_dsm021_shared_time_ce_is_zero` valideert dat Ce=0 gehandhaafd blijft
**Succesrespons:** test GROEN -- shared.time Ce blijft 0
**Foutrespons:** test ROOD -- shared.time Ce > 0 -- engineer identificeert welke src.* import
  werd toegevoegd en verwijdert die of verplaatst het bestand naar een andere sub-laag
**Uitzonderingen:** Bestanden die zowel datum/tijd als andere concerns combineren
  (bijv. datetime + DB query) horen NIET in shared.time thuis

## Gewijzigde bestanden

- `scripts/dsm_full_analysis.py` (MODULE_MAP + SOURCE_DIRS + MODULES + short-dict)
- `tests/architecture/test_dsm021_shared_sublayers.py` (nieuw)
- `docs/backend/features/BE-DSM-043-sp-dsm-021-dag3-shared-time-sublayer.md` (dit bestand)
- `docs/backend/review/review-BE-DSM-043.md` (nieuw)
- `docs/backend/features/ID-REGISTRY.md` (bijgewerkt)
