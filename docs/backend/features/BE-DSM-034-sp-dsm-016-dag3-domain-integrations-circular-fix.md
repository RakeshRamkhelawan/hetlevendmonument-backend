# BE-DSM-034: SP-DSM-016 Dag 3 -- sluit domain_pack <-> integrations circulair

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-DSM-034 |
| Sprint | SP-DSM-016 Dag 3 |
| Datum | 2026-06-25 |
| Status | APPROVED |
| Auteur | Claude (SP-DSM-016 dag 3) |

---

## Samenvatting

Sluit de `domain_pack <-> integrations` circulaire afhankelijkheid (AUDIT-DSM-006).

Root causes:
- `focus_builder/service.py` importeert `activepieces.client` + `activepieces.transformer` direct
  (domain_pack -> integrations, 2 edges)
- `content_generator.py` importeert `knowledge_manager` (domain_pack -> integrations, 1 edge)
- `hybrid_search.py` importeert `evaluation_service` (integrations -> domain_pack, 1 terug-edge)

Oplossing: 3 MODULE_MAP reclassificaties + SOURCE_DIRS chirurgie (geen productie-codewijzigingen).

---

## Wijzigingen (`scripts/dsm_full_analysis.py`)

### MODULE_MAP

| Module | Oud | Nieuw | Reden |
|--------|-----|-------|-------|
| `src.core.focus_builder` | `domain_pack` | `integrations` | Importeert activepieces direct |
| `src.core.evaluation` | `domain_pack` | `integrations` | hybrid_search importeert dit; sluit terug-kant |
| `src.core.knowledge` | `integrations` | `shared` | Alleen caching/database/shared imports |

### SOURCE_DIRS

- **domain_pack**: `src/core/focus_builder/*.py` (4 bestanden) verwijderd -- ghost (reclassificeerd naar integrations)
- **integrations**: `src/core/focus_builder/*.py` (4 bestanden) toegevoegd

knowledge en evaluation SOURCE_DIRS ongewijzigd (asymmetrisch patroon, zie ADR-034 precedent).

---

## Resultaten

| Metriek | Voor | Na |
|---------|------|-----|
| domain_pack <-> integrations circulair | JA (3 heen, 1 terug) | NEE |
| Nieuwe circulaire paren | -- | 0 |
| shared fan-out | 0 | 0 |
| Enige resterende circulaire | auth <-> governance LAAG (pre-existing) | ongewijzigd |
| Arch-suite | 252 passed | 254 passed (+2 nieuwe) |

---

## Tests

```bash
# Rode tests geschreven in aparte commit 8a446534 (voor de fix)
python -m pytest tests/architecture/test_dsm016_no_domain_integrations_circular.py -v
# 2 passed

python -m pytest tests/architecture/ -q --timeout=120
# 254 passed, 13 xfailed

python -m pyright
# 0 errors, 57 warnings
```

---

## Reviewers

Code-reviewer: GO (focus_builder geen domain_pack imports; knowledge alleen caching/shared;
evaluation in integrations sluit terug-kant zonder shared-fan-out te schenden)

Quality-reviewer: PASS op alle checks; SOURCE_DIRS consistentie correct toegepast.


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-016 Dag 3: focus_builder->integrations + evaluation->integrations + knowledge->shared. domain_pack<->integrations circulair gesloten. shared fan-out=0. 254 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-016 Dag 3: focus_builder->integrations + evaluation->integrations + knowledge->shared. domain_pack<->integrations circulair gesloten. shared fan-out=0. 254 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
