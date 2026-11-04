# Backend Feature Specification

## Metadata

- Feature ID: BE-CI-002
- Feature naam: ALS department-agents Any-type TODO(TYPE) markers (regressie richting Any-type gate)
- Status: ACTIEF
- Auteur: Claude (SP-CI-001 Dag 3)
- Reviewer: code-reviewer subagent (APPROVED WITH MINOR GAPS, gap gefixed) + quality-reviewer subagent (CHANGES_REQUESTED, gefixed) -- beide vereist per CLAUDE.md Gate 2 (41 bestanden, >2-bestanden-drempel)
- Datum: 2026-07-14
- Gerelateerde user story / ticket: SP-CI-001 (CI Pipeline Herstel), Bevinding "Any-type baseline monitor" -- uitgebreide scope na ontdekking dat develop 331 i.p.v. de op main gemeten 66 violations heeft (176 commits divergentie)
- Gerelateerde router / module: `src/core/als/agents/departments/*` (41 bestanden)
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

`scripts/check_any_gate.py --baseline docs/any_type_baseline.json src/` toonde op `develop`
331 Any-type-violations (baseline 0) -- 5x meer dan de 66 die de scheduled CI-run op `main`
rapporteerde, door 176 commits divergentie tussen de branches (zie
`docs/agent-briefs/generated/2026-07-14-sprint-dag-3-SP-CI-001.md` voor de volledige
root-cause). Rakesh koos expliciet voor de volledige 331 aan te pakken (grotere sprint dan
gepland). 164 van de 331 (bijna de helft) concentreerden zich in 41 bestanden onder
`src/core/als/agents/departments/` -- "digital employee" departement-agents
(sales_marketing, product_innovation, strategy_business, finance_treasury, hr_culture,
it_security, legal_compliance, data_ai_governance, customer_experience,
operations_supply_chain) die allemaal van `DepartmentAgent`/`MLAgent`/`LLMAgent`
(`base_department_agent.py`) erven en de OODA-loop-methodes (`observe`/`orient`/`decide`)
overriden met `dict[str, Any]`-parameters.

De basisclasse had AL het `# TODO(TYPE): replace Any with concrete type`-patroon op de
RETURN-type-posities van deze methodes (gevestigde conventie), maar niet op de
PARAMETER-posities -- en elke subclass herhaalde het ongemarkeerde patroon zonder enige marker.

### In scope

- 164 `dict[str, Any]`/`list[dict[str, Any]]`-parameterposities in 41 bestanden onder
  `src/core/als/agents/departments/`: `# TODO(TYPE): replace Any with concrete type` toegevoegd
  op exact de regel die `check_any_gate.py` als violation meldde (of een verkorte variant
  `# TODO(TYPE): replace Any` op 1 regel waar black anders de 100-karakter-limiet zou
  overschrijden bij diepe inspringing).

### Out of scope

- De resterende ~167 Any-type-violations buiten deze cluster (security_agent.py,
  business_registry.py, agency_capabilities.py, eval_harness.py, API-routers, schemas, etc.) --
  dag 4.
- De 68 mypy-fouten (36 bestanden) -- volledig ANDERE bestanden dan deze cluster (geen overlap
  geverifieerd via de mypy-baseline-lijst), aparte dag.
- Het daadwerkelijk vervangen van `dict[str, Any]` door concrete `TypedDict`/dataclass-types --
  dat vereist per-departement domeinontwerp (wat betekent elk OODA-payload precies?) en is
  bewust NIET gedaan; de TODO-marker documenteert de schuld eerlijk in plaats van een
  gefingeerd concreet type te verzinnen zonder dat ontwerpwerk.

---

## Build summary

- Gewijzigd: 41 bestanden onder `src/core/als/agents/departments/` -- uitsluitend
  toegevoegde trailing comments (164 regels), gevolgd door een `black --line-length 100`-pass
  om de daardoor ontstane regellengte-overschrijdingen in 6 bestanden te herstellen (waarna 4
  regels hun marker op de verkeerde sub-regel kregen door black's her-wrapping, handmatig
  gecorrigeerd).
- Nieuw gebouwd: geen.
- Verwijderd: geen.
- Beinvloede bestaande flows: geen functionele wijziging -- puur documentatie van bestaande
  type-schuld.

  **Correctie (2026-07-14, onafhankelijke review FA-IND-002):** de oorspronkelijk hier
  aangehaalde "164 insertions / 164 deletions, exacte 1:1 regel-vervanging" klopt niet als
  eindstaat -- de daadwerkelijke diffstat (`git show a7509ba5 --stat --
  src/core/als/agents/departments/`) is "213 insertions(+), 179 deletions(-)", omdat black's
  her-wrapping van lange signatures sommige 1-regelige aanroepen in meerdere regels opsplitste.
  De conclusie zelf (geen logica-wijziging) blijft correct, maar nu onderbouwd met een
  robuustere methode: de onafhankelijke reviewer voerde een AST-dump-vergelijking
  (`ast.dump(ast.parse(...))`) uit tussen de parent-commit en deze commit over alle 41
  bestanden en vond 0 verschillen -- comments beinvloeden de AST niet, dus dit sluit elke
  logica-wijziging uit onafhankelijk van regel-tellingen.

---

## Verificatie (i.p.v. API-flows -- dit is een CI-gate-compliance-fix, geen endpoint-feature)

```bash
python scripts/check_any_gate.py --baseline docs/any_type_baseline.json src/core/als/agents/departments/
# -> Baseline total: 0; current total: 0 -- Any-type gate: no violations found.

black --check --line-length 100 src/core/als/agents/departments/
# -> All done! 52 files would be left unchanged.

ruff check src/core/als/agents/departments/
# -> All checks passed!

python -m mypy src/core/als/agents/departments/ --ignore-missing-imports
# -> Success: no issues found in 52 source files.

python -m pytest tests/als/test_41_agent_organogram.py tests/als/test_router.py \
  tests/als/test_router_department_filtering.py \
  tests/architecture/test_autonomy_ladder_uses_real_agent_capabilities.py \
  tests/security/test_department_isolation_comprehensive.py \
  tests/security/test_routing_constraint_enforcement.py \
  tests/unit/als/test_agent_inventory.py -q --tb=short --timeout=60
# -> 146 passed, 2 skipped

python -m pytest tests/unit/ -n 8 --timeout=60 -q --tb=short
# -> 14084 passed, 209 skipped, 20 xfailed, 0 failed (volledige regressie, geen nieuwe failures)
```

---

## Trainingssamenvatting

- Actor: Ontwikkelaar / CI-pijplijn
- Voorwaarde: De Any-type-gate draait in CI met een 0-baseline op de ALS department-agents.
- Actie: Er wordt code gecommit die de gemarkeerde department-agent-bestanden raakt; CI voert de type-gate uit.
- Systeemreactie: De gate telt Any-type-violations; de `TODO(TYPE)`-markers documenteren de bekende OODA-loop-parameterposities zonder de baseline te breken.
- Succesrespons: 0 nieuwe violations t.o.v. de baseline -> gate groen, merge toegestaan.
- Foutrespons: Een nieuwe Any-type-violation -> gate rood, CI blokkeert de merge tot geadresseerd.
- Uitzonderingen: De gemarkeerde `TODO(TYPE)`-posities zijn bekende, geaccepteerde uitzonderingen tot de vervolg-typing-sprint.

## Open aannames

- De concrete inhoud van elke OODA-payload (`observation`/`orientation`/`payload`/
  `result_data`) verschilt vermoedelijk per departement-agent; een toekomstige
  type-verscherpingssprint zal per-departement `TypedDict`s moeten ontwerpen in plaats van 1
  generieke envelope-type te verzinnen die de werkelijke velden niet dekt.

## Open vragen

- Geen voor deze dag-scope.

## Risico's

- Geen: uitsluitend commentaar toegevoegd, 0 logica-wijziging, 0 nieuwe test-failures over de
  volledige suite (14084 tests) en de gerichte ALS-suite (146 tests).

---

## QA-checks

- [x] Functioneel getest: 146/146 gerichte ALS-tests groen
- [x] Volledige regressie: 14084/14084 unit-tests groen (0 nieuwe failures)
- [x] Any-type gate: 0 violations in de cluster
- [x] black/ruff/mypy: alle groen
- [x] Geen ASCII-schending (byte-niveau gecontroleerd door beide subagents)
- [x] Geen secrets/tenant_id/datetime-patronen geraakt (comment-only diff)

---

## Definition of Done

- [x] Fix is aangebracht (164 markers, 41 bestanden)
- [x] Root-cause vastgesteld en gedocumenteerd (gevestigde TODO(TYPE)-conventie, precedent
      bevestigd door quality-reviewer in `src/alembic/env.py` en elders)
- [x] Gate 2: code-reviewer + quality-reviewer subagents -- beiden initieel bevindingen,
      beide gefixed (zie review-BE-CI-002.md)
- [x] Geen nieuwe regressies (volledige suite + gerichte suite)
- [x] black --check idempotent (bevestigd 2 keer achter elkaar, geen verdere wijzigingen)
