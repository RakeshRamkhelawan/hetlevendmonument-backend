# Feature Spec: BE-DSM-037

**ID:** BE-DSM-037
**Sprint:** SP-DSM-017 Dag 2
**Datum:** 2026-06-26
**Status:** APPROVED

---

## Scope

P2 DSM audit aanbeveling: integrations I=0.535 zonder formele ceiling.
2 nieuwe arch-tests aangemaakt als regressie-alarm.

**Geen productie-code of MODULE_MAP wijzigingen.**

---

## Nieuwe tests

Bestand: `tests/architecture/test_dsm017_integrations_stability.py`

| Test | Ceiling | Huidig | Buffer |
|------|---------|--------|--------|
| `test_dsm017_integrations_ce_excl_shared_within_budget` | <= 65 | 40 | 25 |
| `test_dsm017_integrations_instability_below_0_60` | <= 0.60 | 0.535 | 0.065 |

---

## Verificatie

```
python -m pytest tests/architecture/test_dsm017_integrations_stability.py -v
> 2 passed

python -m pytest tests/architecture/ -q --timeout=120
> 261 passed, 1 failed (test_TODO_SP_DSM_017 backlog -- verwacht), 13 xfailed
```


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-017 Dag 2: integrations stability monitoring. Ce_excl_shared<=65, I<=0.60 ceiling tests. Geen code-wijzigingen. 261+1rood arch-tests. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-017 Dag 2: integrations stability monitoring. Ce_excl_shared<=65, I<=0.60 ceiling tests. Geen code-wijzigingen. 261+1rood arch-tests..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
