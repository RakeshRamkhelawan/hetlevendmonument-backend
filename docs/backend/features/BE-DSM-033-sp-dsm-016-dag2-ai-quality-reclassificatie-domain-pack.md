# BE-DSM-033: SP-DSM-016 Dag 2 -- ai_quality reclassificatie naar domain_pack

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-DSM-033 |
| Sprint | SP-DSM-016 Dag 2 |
| Datum | 2026-06-25 |
| Status | APPROVED |
| Auteur | Claude (SP-DSM-016 dag 2) |

---

## Samenvatting

Sluit de `domain_pack <-> governance` circulaire afhankelijkheid (AUDIT-DSM-005).

Root cause: `src.core.ai_quality` was geclassificeerd als `governance` maar importeert
`procedures`-data (domain_pack). Dit creeerde 3 backward edges governance->domain_pack.
Aanvullend importeerde `dsar_service.py` (governance) een `CVAConversation` (domain_pack)
via lazy import, waardoor na de ai_quality fix nog 1 edge overbleef. Opgelost door
`src.core.conversations` te reclassificeren naar `shared` (conversations importeert
alleen `database.Base`, geen domain_pack-specifieke code).

---

## Wijzigingen

### `scripts/dsm_full_analysis.py`

1. **MODULE_MAP**: `"src.core.ai_quality"` gewijzigd van `"governance"` naar `"domain_pack"`
2. **MODULE_MAP**: `"src.core.conversations"` gewijzigd van `"domain_pack"` naar `"shared"`
   (SP-DSM-016 dag 2: sluit governance->domain_pack via dsar_service lazy import)
3. **governance SOURCE_DIRS**: `"src/core/ai_quality"` verwijderd
4. **domain_pack SOURCE_DIRS**: `"src/core/ai_quality"` toegevoegd;
   `"src/core/conversations"` verwijderd (ghost: reclassificeerd naar shared)
5. **shared SOURCE_DIRS**: `"src/core/conversations"` toegevoegd

### `tests/architecture/test_dsm016_no_governance_domain_circular.py` (NIEUW)

Twee arch-tests:
- `test_dsm016_governance_no_domain_pack_circular_pair`: verifieert dat DSM-output NIET
  meer het paar `domain_pack <-> governance` toont.
- `test_dsm016_ai_quality_not_classified_as_governance`: verifieert dat MODULE_MAP geen
  `"src.core.ai_quality": "governance"` meer bevat (statische code-check).

---

## Resultaten

| Metriek | Voor | Na |
|---------|------|-----|
| domain_pack <-> governance circulair | JA (1 heen, 1 terug) | NEE |
| Nieuwe circulaire paren | -- | 0 |
| shared fan-out | 0 | 0 |
| Arch-suite | 250 passed | 252 passed (+2 nieuwe) |

---

## Tests

```bash
python -m pytest tests/architecture/test_dsm016_no_governance_domain_circular.py -v
# 2 passed

python -m pytest tests/architecture/ -q --timeout=120
# 252 passed, 13 xfailed
```

---

## Pyright

```bash
python -m pyright
# 0 errors, 57 warnings
```


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-016 Dag 2: ai_quality reclassificatie governance->domain_pack + conversations reclassificatie domain_pack->shared. domain_pack<->governance circulair gesloten. shared fan-out=0. 252 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-016 Dag 2: ai_quality reclassificatie governance->domain_pack + conversations reclassificatie domain_pack->shared. domain_pack<->governance circulair gesloten. shared fan-out=0. 252 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
