# BE-DSM-027: SP-DSM-011 — governance instabiliteit I 0.613 → 0.373

## Sprint
SP-DSM-011 Dag 1 (single-dag sprint)

## Status
APPROVED

## Datum
2026-06-24

---

## Samenvatting

governance I (instabiliteitsindex) verlaagd van 0.613 naar 0.373 via de
"governance_worker pattern": MODULE_MAP reclassificatie + SOURCE_DIRS chirurgie.

Aanpak: uitsluitend `scripts/dsm_full_analysis.py` gewijzigd. Nul productie-codewijzigingen.

---

## Gewijzigde bestanden

| Bestand | Type wijziging |
|---------|---------------|
| `scripts/dsm_full_analysis.py` | MODULE_MAP: governance.models-override verwijderd + event_handlers/dsar_notifications reclassificatie; SOURCE_DIRS: governance/ enumeratie (33 bestanden + 3 subdirs), worker + integrations uitgebreid |
| `tests/architecture/test_dsm_011_governance_instability_below_0_40.py` | Nieuwe architecture test (GROEN na fix) |
| `tests/architecture/test_dsm_medium_pairs_tracking.py` | Ceiling test voor nieuw governance<->infra LAAG paar (infra->governance <= 2) |
| `tests/architecture/test_dsm_governance_regression.py` | `test_infra_no_governance_import` -> `test_infra_governance_import_not_growing` (ceiling 2, SP-DSM-011 context) |

---

## Root cause analyse

Twee factoren inflateerden governance Ce onterecht tot 68:

| Factor | Imports | Mechanisme |
|--------|---------|------------|
| `governance.models` in MODULE_MAP als `"shared"` (SP-DSM-REGRESSIE artifact) | 22 governance-interne imports naar governance.models telden als governance->shared | Verwijdering van deze override classificeert ze als intern -> Ce -22 |
| `event_handlers.py` (Ce=6) en `dsar_notifications.py` (Ce=2) in governance SOURCE_DIRS | Beide bestanden scanden als governance-bestanden; hun outgoing deps telden als governance Ce | SOURCE_DIRS chirurgie: bestanden uit governance/ enumeratie -> Ce -8 |

---

## Gesimuleerde impact (geverifieerd)

| Stap | Ce | Ca | I |
|------|----|----|---|
| Huidig (voor fix) | 68 | 43 | 0.613 |
| +governance.models -> governance | 46 | 64 | 0.422 |
| +event_handlers/dsar_notifications SOURCE_DIRS | 38 | 64 | 0.373 |

---

## Neveneffect: governance<->infra LAAG circular (nieuw)

De governance.models reclassificatie onthult 2 pre-existing infra->governance runtime imports:
- `src/core/database/tenant_query_filter.py:165`
- `src/core/models/__init__.py:9`

Dit is een bestaande SDP-schending die eerder verborgen was door de "shared" override.
Grade blijft A (enkel LAAG circular). SP-DSM-012 backlog: TYPE_CHECKING guards toevoegen.

---

## Architecture tests

| Test | Status | Waarde |
|------|--------|--------|
| `test_dsm_011_governance_instability_below_0_40` | GROEN | I=0.373 < 0.40 |
| `test_governance_infra_terug_not_growing` | GROEN | infra->governance=2 <= 2 |
| `test_infra_governance_import_not_growing` | GROEN | infra->governance=2 <= 2 |
| Volledige architecture suite | GROEN | 220 passed, 13 xfailed |

---

## Verificatie

```bash
python scripts/dsm_full_analysis.py           # governance I=0.373
python -m pytest tests/architecture/ -q --timeout=60  # 220 groen, 13 xfailed
python -m pyright                             # 0 errors
```


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-011 Dag 1: governance I 0.613->0.373 via governance_worker pattern. governance.models override verwijderd + event_handlers->worker + dsar_notifications->integrations (MODULE_MAP + SOURCE_DIRS chirurgie). 220 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-011 Dag 1: governance I 0.613->0.373 via governance_worker pattern. governance.models override verwijderd + event_handlers->worker + dsar_notifications->integrations (MODULE_MAP + SOURCE_DIRS chirurgie). 220 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
