# BE-DSM-042: SP-DSM-020 Dag 2 -- integrations I-ceiling vastgelegd, sub-laag reclassificatie afgewezen

## Status

APPROVED

## Sprint

SP-DSM-020 Dag 2

## Datum

2026-06-26

## Samenvatting

DSM-ARCH-003 afgerond: formele I-ceiling arch-tests voor de integrations-laag bestaan en
zijn GROEN (aangemaakt in SP-DSM-017 Dag 2, commit 88da1209). De evaluatie van
focus_builder/evaluation/gdpr_purge als eigen sub-laag is uitgevoerd en de beslissing
is: reclassificatie afwijzen, steady-state I=0.535 accepteren.

Geen codewijzigingen deze dag. Uitkomst is een gedocumenteerde architectuurbeslissing
en bijgewerkt toezichtsmodel voor de integrations-laag.

## DSM-ARCH-003: Bevinding en beslissing

### Bevinding (uit DSM-audit 2026-06-26)

integrations heeft I=0.535 zonder formele ceiling-test. Module bevat 24 MODULE_MAP-entries
die een heterogeen geheel vormen: event handlers, storage, websocket, activepieces,
analytics, focus_builder, evaluation, gdpr_purge, etc.

integrations omvat 77 Python-bestanden verdeeld over meerdere MODULE_MAP-entries
(activepieces, events, websocket, storage, analytics, focus_builder, evaluation, etc.).

Vraag: moeten focus_builder / evaluation / gdpr_purge een eigen DSM-sub-laag krijgen
om integrations te stabiliseren (I te verlagen)?

### Huidige metrics (bevestigd na SP-DSM-019)

| Metriek | Waarde | Ceiling / Budget |
|---------|--------|-----------------|
| Ce_all (inclusief shared) | 85 | n.v.t. |
| Ca (fan-in) | 74 | n.v.t. |
| I = Ce/(Ce+Ca) | 0.535 | **<= 0.60** (arch-test aanwezig) |
| Ce_excl_shared | 40 | **<= 65** (arch-test aanwezig) |
| SDP-schendingen | 0 | 0 |
| Circulaire paren | 0 | 0 |

Fan-out verdeling: shared=45, infra=31, auth=5, governance=2, worker=2.

### Evaluatie: focus_builder / evaluation / gdpr_purge reclassificeren?

**Kandidaat-modules voor eigen sub-laag:**
- `src.core.focus_builder` (models, schemas, service, validators)
- `src.core.evaluation`
- `src.core.actors.gdpr_purge`

**Analyse:**

| Criterium | Uitkomst |
|-----------|---------|
| Actieve SDP-schending? | Nee -- integrations importeert alleen infra/auth/governance (allemaal gerechtvaardigd) |
| I boven ceiling? | Nee -- I=0.535 ruimschoots onder 0.60 |
| Ce_excl_shared boven budget? | Nee -- 40 van 65 beschikbaar |
| Reclassificatie lost SDP-schending op? | Nee -- geen schending aanwezig |
| Reclassificatie verlaagt integrations I? | Marginaal, afhankelijk van hun eigen imports |
| Kostprijs reclassificatie | Hoog: 1-2 nieuwe DSM-lagen, nieuwe arch-tests per laag, uitbreiding MODULE_MAP, risico van nieuwe ceiling-violaties bij reclassificatie |
| Samenhang focus_builder/evaluation met integrations? | Ja: cross-domain services die externe systemen of AI-evaluatie-providers aanroepen; "outward-facing" karakter past in integrations |

**Beslissing: reclassificatie AFGEWEZEN.**

Gronden:
1. Geen actieve SDP-schending of I-ceiling-overtreding om op te lossen.
2. De heterogeniteit van integrations (77 bestanden, meerdere MODULE_MAP-entries) is architecturale realiteit: het is
   de laag die business-domain logica koppelt aan externe systemen. focus_builder en
   evaluation passen conceptueel in dit cluster.
3. Reclassificatie verhoogt de DSM-complexiteit (meer lagen = meer ceiling-tests = meer
   onderhoud) zonder een meetbaar voordeel op te leveren.
4. De bestaande arch-tests (Ce_excl_shared <= 65 en I <= 0.60) zijn het correcte bewakingsmechanisme.
   Zolang deze groen blijven, is geen actie vereist.

**Toezichtsmodel (steady-state):**

| Signaal | Actie |
|---------|-------|
| `test_dsm017_integrations_instability_below_0_60` rood | Onderzoek welke modules Ce doen stijgen; overweeg dan pas sub-laag |
| `test_dsm017_integrations_ce_excl_shared_within_budget` rood | Idem; Ce_excl_shared > 65 is het echte alarm-punt |
| Nieuwe SDP-schending (integrations->onstabiel) | Directe fix vereist ongeacht I-waarde |
| I-waarde nadert 0.55+ | Pre-emptieve review als sub-laag optie |

## Arch-tests (bestaand, GROEN)

| Test | Commit | Status |
|------|--------|--------|
| `test_dsm017_integrations_ce_excl_shared_within_budget` | 88da1209 | PASS (Ce=40 <= 65) |
| `test_dsm017_integrations_instability_below_0_60` | 88da1209 | PASS (I=0.535 <= 0.60) |

Beide tests aangemaakt in SP-DSM-017 Dag 2, minor-fixes in 94d695ab. Geen nieuwe
code of tests toegevoegd deze dag -- bestaande tests vormen het bewakingsmechanisme.

**Pre-existing noot (FA-003):** de test-docstring vermelt "budget 60 + 5 buffer = 65"
terwijl deze spec de ceiling als 65 vermeldt zonder het budget/buffer-onderscheid te
expliciteren. De assert-waarde (65) is correct in beide. Terminologie-harmonisatie
is backlog (SP-DSM-017 scope, buiten commit f6925926).

## Pyright

0 errors (geen codewijzigingen).

## Trainingssamenvatting

### integrations DSM-laag (toezichtsmodel)

**Actor:** Architect / tech lead die DSM-metrics reviewt
**Voorwaarde:** Nieuwe module wordt aangemaakt in integrations-domein (focus_builder, events, etc.)
**Actie:** Architect checkt `test_dsm017_integrations_instability_below_0_60` en
  `test_dsm017_integrations_ce_excl_shared_within_budget` via CI; geen aanvullende handmatige stap vereist
**Systeemverwerking:** Arch-tests draaien bij elke commit; DSM-analyse scanner detecteert automatisch
  nieuwe imports vanuit integrations-bestanden
**Succesrespons:** Beide tests GROEN -- geen actie vereist
**Foutrespons:** Een van de tests ROOD -- engineer onderzoekt welke imports zijn toegevoegd;
  bij structurele groei overweeg dan sub-laag reclassificatie conform dit document
**Uitzonderingen:** Sub-laag reclassificatie (focus_builder/evaluation) vereist herziening van
  dit besluit via een nieuwe BE-DSM-XXX feature spec

## Gewijzigde bestanden

Geen codewijzigingen. Documentatiedag.

- `docs/backend/features/BE-DSM-042-sp-dsm-020-dag2-integrations-monitoring.md` (dit bestand)
- `docs/backend/review/review-BE-DSM-042.md` (nieuw)
- `docs/backend/features/ID-REGISTRY.md` (bijgewerkt)
