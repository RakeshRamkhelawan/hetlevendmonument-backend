# BE-AGT-056 -- Minimaal statuscontract voor ExecutionResult.status (ADR036-D7-001)

## Metadata

- **Sprint:** ADR-036 fix-sprint -- P0 + P1 uit de volledige audit (2026-08-18), dag 7 van 8
- **ADR:** ADR-036 D7-001 (statuscontract Fase 2); Fase 4 (checkpoint-tabel) blijft BUITEN SCOPE
- **Datum:** 2026-08-21
- **Branch:** develop

---

## Doel en scope

### Doel

`ExecutionResult.status` (`src/core/shared/interfaces.py:164`) had geen gesloten vocabulaire
en werd door de ALS-uitvoerpaden (`BaseSpecialistAgent.act()`/`_run_within_budget()`,
`DomainPackOrchestrator._execute_step()`/`_run_single_step()`) nooit gevuld. Een
aanroeper kon `success`/`error_message` lezen, maar niet in EEN veld zien of een mislukking
een governance-weigering, een budgetgrens, een deeluitvoering, of een onverwachte fout was.

### In scope

- Nieuwe `ExecutionStatusContract(str, Enum)` (`src/core/types.py`) met vijf gesloten
  waarden: `KLAAR`, `GEDEELTELIJK`, `MEER_BUDGET_NODIG`, `GEBLOKKEERD`, `MISLUKT`.
- `ExecutionResult.status` van `str | None` naar `ExecutionStatusContract | None`.
- `BaseSpecialistAgent._status_from_errors()` (nieuwe statische helper): leidt de status af
  uit `act()`'s bestaande `results`/`errors`-boekhouding, met een expliciete
  prioriteitsvolgorde bij samenloop (zie sectie 6 hieronder).
- Een `"kind"`-veld op de vier plekken waar `act()` een fout aan `errors` toevoegt
  (governance-weigering, `max_steps`-overschrijding, tool-mislukking, tool-exception), zodat
  de mapping deterministisch is in plaats van substring-matching op de foutmelding.
- `status=MEER_BUDGET_NODIG` op de drie budgetafsluiters in `_run_within_budget()`
  (Prana-tekort, skill-timeout, `max_llm_calls`).
- `status=MISLUKT` op alle zes faal-vormige `ExecutionResult`-constructies in `packs.py`
  (SLA-timeout, generieke exception in `_run_single_step()`, onbekende agent, ongewired-skill,
  skill-exception in `_execute_step()`, en pack-niet-gevonden in `run_pack_by_id()` -- de
  laatste gevonden door Gate 2, zie de aanvulling hieronder).
- **Scope-uitbreiding t.o.v. het oorspronkelijke plan (technische noodzaak, geen
  productafweging)**: zes constructies in `base_agent.py::process_task()` raakten
  uiteindelijk, niet de oorspronkelijk voorziene een. De bestaande `status="400"`-toewijzing
  (prompt-injectie) werd een type-fout zodra `status` een gesloten enum kreeg -> vervangen
  door `status=MISLUKT`. Twee andere plekken (governance-contract-blokkade -> `GEBLOKKEERD`;
  de buitenste `except Exception` -> `MISLUKT`) kregen dezelfde behandeling voor consistentie
  in de eerste implementatieronde. **Gate 2 (code-reviewer) vond dat dit nog niet volledig
  was**: drie WEER andere constructies in dezelfde methode (taakvalidatie-mislukking,
  GDPR-profileringsweigering, agent-op-capaciteit) bleven op `status=None` staan -- exact de
  "sibling-branch-achtergelaten"-fout die dag 6 zelf al twee keer vond (`fabricated_stat`
  bleef eerst ongewijzigd terwijl `ungrounded_file_ref` al gefixed was). Alle drie alsnog
  gefixed: taakvalidatie -> `MISLUKT`, GDPR-weigering -> `GEBLOKKEERD` (een beleidsmatige
  blokkade, geen technische mislukking), capaciteitslimiet -> `MEER_BUDGET_NODIG` (een
  resourcegrens is bereikt, geen "iets ging kapot"). Zie sectie "Gate 2 -- bevindingen en
  fixes" hieronder voor de volledige ronde.

### Out of scope

- Checkpoint-tabel / hervatbaarheid (ADR-036 Fase 4) -- expliciet niet vandaag.
- Council-gemedieerde budgetverlenging (de ADR-tekst noemt dit bij `MEER_BUDGET_NODIG`, maar
  het MECHANISME (een verlenging aanvragen/toekennen) is geen onderdeel van vandaag -- alleen
  het STATUSCONTRACT dat een toekomstig verlengingsmechanisme zou kunnen lezen.
  BEWEERD noch geimplementeerd dat een dergelijk mechanisme al bestaat.

---

## Build summary

- Nieuw gebouwd: `ExecutionStatusContract`-enum; `_status_from_errors()`-helper; 7 nieuwe
  tests (getal zelf herverifieerd via `git diff 09becbd7^ 09becbd7` op elke
  `(async )?def test_`-regel, niet aangenomen) -- 4 in `test_council_gate_per_action.py`
  (2 mutatiebewijs-tests voor de prioriteitsvolgorde, 2 voor `governance_unavailable`
  toegevoegd na Gate 2 ronde 1), 2 in `test_skill_budget_enforcement.py`, 1 in
  `test_governance_wiring_dag4.py` (4+2+1=7). **Correctie na de verplichte blinde eindreview
  (ronde 1)**: de eerste versie van dit document noemde hier "6" i.p.v. "4" voor
  `test_council_gate_per_action.py` -- een optelfout die zijn eigen 2+2-uitsplitsing al
  tegensprak, gevonden door de reviewer en zelf herverifieerd met de exacte `git diff` boven.
- Gewijzigd: 22 bestaande tests uitgebreid met een `status`-assertie (geen enkele test
  hernoemd of verwijderd; getal herverifieerd via `git diff 09becbd7^ 09becbd7` op elke
  toegevoegde `.status ==`-regel -- 30 in totaal, minus 1 die een docstring-vermelding is
  (geen code) en minus de 7 die bij de nieuwe tests horen). **Correctie na de verplichte
  blinde eindreview**: de eerste versie noemde hier "21", een telfout van een. 3 stale
  regelverwijzingen in testdocstrings gecorrigeerd (`specialist_base.py:324-327` ->
  `:512-520`; `specialist_base.py:366-369` -> `:368-377`; een verouderde `success`-formule in een
  moduledocstring).
- Productiecode gewijzigd: `src/core/types.py`, `src/core/shared/interfaces.py`,
  `src/core/als/agents/specialist_base.py`, `src/core/als/enterprise/packs.py`,
  `src/core/agents/base_agent.py`.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-056 | `ExecutionStatusContract` | Enum/type | `src/core/types.py` | Nieuw | n.v.t. |
| BE-AGT-056 | `ExecutionResult.status` | Model-veld | `src/core/shared/interfaces.py` | Wijziging | n.v.t. |
| BE-AGT-056 | `BaseSpecialistAgent._status_from_errors()` | Interne methode | `src/core/als/agents/specialist_base.py` | Nieuw | OODA/piloot-uitvoerpad |
| BE-AGT-056 | `BaseSpecialistAgent.act()` / `_run_within_budget()` | Interne methode | `src/core/als/agents/specialist_base.py` | Wijziging | OODA/piloot-uitvoerpad |
| BE-AGT-056 | `DomainPackOrchestrator._execute_step()` / `_run_single_step()` / `run_pack_by_id()` | Interne methode | `src/core/als/enterprise/packs.py` | Wijziging | pack-uitvoerpad |
| BE-AGT-056 | `EnhancedBaseAgent.process_task()` | Interne methode | `src/core/agents/base_agent.py` | Wijziging | generiek agent-uitvoerpad |

---

## Detaildocumentatie per artefact

## [BE-AGT-056] Minimaal statuscontract

### 1. Type

- Type-contract (enum) + agent-/orchestratiegedrag (interne methoden, geen HTTP-endpoint).

### 2. Locatie

- `src/core/types.py` (enum), `src/core/shared/interfaces.py:164` (veld),
  `src/core/als/agents/specialist_base.py` (`_status_from_errors()`, `act()`,
  `_run_within_budget()`), `src/core/als/enterprise/packs.py` (`_execute_step()`,
  `_run_single_step()`, `run_pack_by_id()`), `src/core/agents/base_agent.py`
  (`process_task()`).

  **Correctie (ronde 4):** deze regel citeerde nog `_execute_agent_step()` -- een
  niet-bestaande methodenaam die Gate 2 (sectie 6a) al had gecorrigeerd naar
  `_run_single_step()`, maar die correctie was nooit tot HIER doorgevoerd. Exact het
  "een sibling-plek van een al-gefixte fout blijft achter"-patroon dat deze dag al drie
  keer in de CODE trof (Gate 2, ronde 1, ronde 3) -- hier een niveau hoger, in de
  documentatie van de fix zelf.

### 3. Gerelateerde flow

- Geen apart Flow-ID -- een statuscontract dat door alle bestaande uitvoerpaden heen gevuld
  wordt, geen nieuwe flow.

### 4. Doel

- Een aanroeper (toekomstige monitoring, een goedkeurings-UI, of een retry-beslisser) kan na
  vandaag een van vijf gesloten waarden lezen in plaats van `success`/`error_message` te
  moeten parsen om te raden WAAROM een uitvoering niet KLAAR is.

### 5. Functionele beschrijving

- **KLAAR**: volledige, succesvolle afronding (geen `errors`).
- **GEDEELTELIJK**: minstens een stap slaagde, minstens een andere niet (tool-mislukking,
  tool-exception, of een `max_steps`-overschrijding die afkapt en doorgaat) -- MITS geen
  governance-weigering erbij zit (die domineert, zie sectie 6).
- **MEER_BUDGET_NODIG**: een van de drie ECHTE budgetafsluiters in `specialist_base.py`
  (Prana-tekort, skill-timeout, `max_llm_calls`) brak de hele aanroep af voordat er iets kon
  lukken -- of, in `base_agent.py`, de agent zit al op zijn maximum aantal gelijktijdige
  taken (een resourcegrens, geen technische mislukking).
- **GEBLOKKEERD**: een governance-beslissing (D5-denylist, ontbrekende initiator, of een
  niet-APPROVED Council-verdict inclusief een HITL-ticket dat op een mens wacht) hield de
  actie tegen -- of, in `base_agent.py`, een `GovernanceContract`-blokkade of een
  GDPR-art.-21-profileringsweigering. Domineert over een gelijktijdig deelsucces (zowel de
  ALS-variant `"governance"` als de infrastructuurvariant `"governance_unavailable"`, zie
  sectie 6).
- **MISLUKT**: een onverwachte fout (tool-exception zonder enig succes, een SLA-timeout, een
  onbekende/ongewired agent of pack, de governance-poort zelf onbereikbaar) -- of, in
  `base_agent.py`, een geweigerde prompt-injectie, een mislukte taakvalidatie, of een
  onverwachte exception in de buitenste `except`-afhandeling van `process_task()`.

### 6. Technische beschrijving

`BaseSpecialistAgent._status_from_errors(results, errors)` (nieuwe `@staticmethod`):

```python
if not errors:
    return ExecutionStatusContract.KLAAR
kinds = {e.get("kind") for e in errors}
if "governance_unavailable" in kinds:
    return ExecutionStatusContract.MISLUKT
if "governance" in kinds:
    return ExecutionStatusContract.GEBLOKKEERD
if results:
    return ExecutionStatusContract.GEDEELTELIJK
return ExecutionStatusContract.MISLUKT
```

Prioriteitsvolgorde, hoog naar laag: `governance_unavailable` (infrastructuurstoring) >
`governance` (beleidsweigering, domineert over deelsucces) > `results` niet-leeg
(GEDEELTELIJK) > MISLUKT (niets gelukt, geen governance-reden). De drie budgetafsluiters
komen hier NOOIT langs -- die geven al terug vanuit `_run_within_budget()` voordat `act()`
deze functie bereikt.

Elke `errors.append(...)`-plek in `act()` krijgt een `"kind"`: `"governance"` (een
`_reject_before_council()`/`_council_rejection()`-weigering) of `"governance_unavailable"`
(de governance-poort zelf gooide een exception), `"step_limit"` (`max_steps`-overschrijding),
`"tool_failure"` (`{"success": false}`), `"tool_exception"` (een gegooide exception tijdens
`execute_tool`).

**Zelf gevonden tijdens implementatie, gecorrigeerd t.o.v. het oorspronkelijke plan**: het
plan groepeerde elke budgetgrens onder `MEER_BUDGET_NODIG`, inclusief `max_steps`. Gemeten
(`specialist_base.py:673-690`): een `max_steps`-overschrijding kapt af en gaat DOOR met de
eerste N tool-calls -- een echte deeluitvoering, geen afsluiter. Daarom draagt
`kind="step_limit"` uitsluitend bij aan `GEDEELTELIJK`.

### 6a. Gate 2 -- bevindingen en fixes (2026-08-21)

Twee onafhankelijke Gate-2-reviewers (code-reviewer + security-reviewer, elk zonder kennis
van de ander) beoordeelden de implementatie. **Security-reviewer: GO, geen bevindingen** --
zelfstandig nagerekend dat `status`'s vijf waarden geen PII kunnen dragen (een gesloten enum,
geen vrije tekst), dat het `"kind"`-veld nergens een extern leespad heeft (repo-breed gegrept,
enige lezer is `_status_from_errors()` zelf), dat de GEBLOKKEERD-domineert-GEDEELTELIJK-regel
`result_data["results"]` niet wist (de onderliggende uitvoeringshistorie blijft intact), dat
de `status="400"`-vervanging geen enkele bestaande lezer raakt (onafhankelijk herverifieerd
met een eigen repo-brede grep, niet op het woord van de brief aangenomen), en dat
`tenant_id`/`agent_id` in geen van de gewijzigde bestanden zijn aangeraakt.

**Code-reviewer: CHANGES_REQUESTED, twee bevindingen, beide gefixt in dezelfde sessie:**

1. **Vier sibling-`ExecutionResult`-constructies bleven op `status=None` staan** --
   `packs.py:269` (`run_pack_by_id()`, "pack niet gevonden", structureel identiek aan de
   "onbekende agent"-tak op regel 426 die al `MISLUKT` kreeg) en drie in
   `base_agent.py::process_task()` (taakvalidatie-mislukking, GDPR-profileringsweigering,
   agent-op-capaciteit) -- dezelfde methode waarvan drie ANDERE takken in de eerste
   implementatieronde al gefixed waren. Exact de "sibling-branch-achtergelaten"-vorm die dag 6
   zelf al twee keer vond. **Fix:** alle vier expliciet gemapt (`packs.py:269` -> `MISLUKT`;
   taakvalidatie -> `MISLUKT`; GDPR-weigering -> `GEBLOKKEERD`, een beleidsmatige blokkade;
   capaciteitslimiet -> `MEER_BUDGET_NODIG`, een resourcegrens). Daarna een uitputtende,
   programmatische controle (elke `ExecutionResult(...)`-aanroep in de drie kernbestanden
   geparsed en op `status=` gecontroleerd, niet alleen de vier genoemde plekken) bevestigde
   dat alle 17 constructies nu een `status` zetten.
2. **De `governance_unavailable`-tak (en zijn prioriteit over `governance`/deelsucces) had
   geen enkele test** -- bewezen met een LIVE mutatie (die tak tijdelijk naar `GEBLOKKEERD`
   laten wijzen in plaats van `MISLUKT`): alle 64 op dat moment gerichte tests bleven groen.
   **Fix:** twee nieuwe tests toegevoegd
   (`test_a_broken_governance_gate_reports_mislukt`,
   `test_governance_unavailable_dominates_a_simultaneous_partial_success`), en zelf
   gereproduceerd dat EXACT de door de reviewer gebruikte mutatie beide nieuwe tests rood
   maakt.

Bijvangst tijdens het verwerken van bevinding 1: twee stale/onnauwkeurige claims in dit
document zelf (de methodenaam `_execute_agent_step` bestaat niet -- de echte naam is
`_run_single_step`; de oorspronkelijke testtellingen "8 nieuw/13 uitgebreid" klopten niet)
zijn hierboven al gecorrigeerd. **Deze telling bleek bij de blinde eindreview (zie 6b
hieronder) zelf ook nog niet helemaal juist** (7/21 was een tussenstap, niet het eindgetal --
de reviewer vond een optelfout en een telfout van een; het huidige, driemaal
herverifieerde eindgetal is 7 nieuw/22 uitgebreid, plus 4 MEER nieuwe tests uit de
blinde-review-fix zelf, zie 6b).

### 6b. Verplichte blinde eindreview -- ronde 1 -- bevinding en fix (2026-08-21)

**Oordeel: NO-GO.** Niet omdat de gebouwde code fout was (alle 17 `status=`-toewijzingen
waren aanwezig en elke gekozen waarde was verdedigbaar), maar omdat de final-approver-brief
en dit document een expliciete, afgevinkte (`[x]`) volledigheidsclaim bevatten die de
reviewer als onwaar reproduceerde.

**Bevinding (BLOCKER):** de claim "alle zes `base_agent.py`-toevoegingen zijn mutatiegetest"
klopte voor slechts 2 van de 6 (`status="400"`->MISLUKT, governance-contract-blokkade). De
andere vier (taakvalidatie-mislukking, GDPR-profileringsweigering, capaciteitslimiet, de
buitenste `except`-afhandeling) waren nooit door een test gecontroleerd op `.status` --
alleen de PARSE-controle uit Gate 2 (bevinding 1 hierboven) had bevestigd dat de kwarg
SYNTACTISCH aanwezig was, niet dat een test hem ook daadwerkelijk toetst. De reviewer bewees
het gat zelf, tweemaal, met een live mutatie (twee losse `status=`-waarden gewijzigd naar
`KLAAR`, telkens `1295 passed` -- identiek aan de baseline, dus geen enkele detectie).

**Waarom dit ertoe doet:** twee van de vier ongeteste takken zijn governance-relevant
(GDPR-opt-out, capaciteitsdrempel) -- precies het soort code waarvan dit project's eigen
regels zeggen dat een claim nooit ongeverifieerd mag blijven staan. Het is ook, letterlijk
in dezelfde dag, de TWEEDE keer dat dit exacte patroon (een tak zonder test, bewezen met een
live mutatie) zich voordeed -- de eerste keer (`governance_unavailable`) al gevonden door
Gate 2, deze keer door de blinde review.

**Fix:** vier nieuwe tests toegevoegd in `test_governance_wiring_dag4.py`
(`test_task_validation_failure_reports_mislukt`,
`test_gdpr_profiling_opt_out_reports_geblokkeerd`,
`test_agent_at_capacity_reports_meer_budget_nodig`,
`test_unexpected_exception_reports_mislukt`), elk met een eigen mutatiebewijs (backup/restore
via `cp`, nooit `git checkout --`): de bijbehorende `status=`-waarde tijdelijk naar een andere
waarde gewijzigd, bevestigd dat de NIEUWE test rood wordt, dan herstel bevestigd groen.

**Twee bijkomende MINOR-bevindingen, ook verwerkt:**
- De testtelling in dit document klopte zelf niet (zie de correctie hierboven bij "Bijvangst"
  en in de Build summary) -- een optelfout ("6" i.p.v. "4" nieuwe tests in
  `test_council_gate_per_action.py`, die zijn eigen 2+2-uitsplitsing al tegensprak) en een
  telfout van een (21 i.p.v. 22 uitgebreide tests).
- De `ExecutionStatusContract`-enum-docstring (`src/core/types.py`) noemt voor GEBLOKKEERD en
  MEER_BUDGET_NODIG alleen de `specialist_base.py`-oorzaken, niet de `base_agent.py`-specifieke
  oorzaken (GDPR-opt-out, governance-contract-blokkade, capaciteitslimiet) die deze sectie wel
  correct beschrijft. Gefixt: de enum-docstring uitgebreid met alle bronnen per waarde.

### 6c. Verplichte blinde eindreview -- ronde 2 -- bevinding en fix (2026-08-21)

**Oordeel: GO WITH MINOR ISSUES.** De reviewer reproduceerde ronde 1's mutatiebewijs
zelfstandig voor alle vier nieuwe takken (niet alleen de gevraagde twee), herrekende beide
gecorrigeerde testtellingen vanaf de ruwe `git diff`-output, en draaide alle Gate 3-checks
zelf -- alles kwam exact overeen. Een MINOR-bevinding, direct verwerkt:

**De enum-docstring-uitbreiding uit 6b beweerde zelf iets wat hij niet leverde.** De openende
zin zei "de bronnen hieronder per waarde bestrijken alle drie [bestanden]", maar `packs.py`
werd daarna in GEEN van de vijf opsommingen meer genoemd -- exact het soort ongeverifieerde
volledigheidsclaim die dit hele statuscontract (en de twee eerdere reviewrondes) al twee keer
eerder betrapte, nu in de eigen reparatie ervan. Zelf nagemeten: alle zes `ExecutionResult`-
constructies in `packs.py` zijn `MISLUKT` (SLA-timeout, generieke exception, onbekende agent,
ongewired-skill, skill-exception, pack-niet-gevonden) -- geen enkele draagt bij aan de andere
vier waarden. **Fix:** de MISLUKT-opsomming uitgebreid met `packs.py`'s zes bronnen bij naam;
de openende claim is nu daadwerkelijk waar.

**Twee bijkomende NIT-bevindingen, ook verwerkt:**
- Deze sectie's eigen DoD-checklist had een `[ ]` op de doc-gate-regel terwijl de gate al
  langer groen stond (de review-file bestond al sinds `09becbd7`). Afgevinkt met het bewijs.
- `docs/backend/review/review-BE-AGT-056.md` citeert nog het inmiddels vervangen "7/21"-getal
  uit de Gate-2-ronde-1-snapshot. Bewust NIET herschreven (dat bestand is een tijdstip-
  snapshot van Gate 2, geen levend document) -- in plaats daarvan hieronder een kort pointer
  toegevoegd zodat een lezer die dat bestand alleen inziet niet op het oude getal vastloopt.

**Een pre-existing, niet-vandaag-veroorzaakte observatie, WEL vandaag gefixed (drempelmodel:
geisoleerd, 1 testbestand, <15 min, lage impact -- past niet bij "backlog" of "stop"):** de
GDPR-art.-21-faalveilige `except`-tak in `base_agent.py` (regel 543-562, valt terug op
"opted out" bij een DB-fout) had geen enkele gedragstest die het EXCEPTION-pad zelf uitoefent
-- de bestaande test test alleen het pad waar de check schoon `True` teruggeeft. Bevestigd
pre-existing (`git diff 09becbd7^ 09becbd7` raakt deze regels niet). Een NIEUWE test
toegevoegd (`test_gdpr_profiling_check_failure_fails_closed_and_reports_geblokkeerd`, mockt
`check_profiling_opt_out` met `side_effect=RuntimeError(...)` i.p.v. `return_value=True`),
mutatiegetest: `self._profiling_opted_out = True` in de `except`-tak tijdelijk naar `False`
(fail-OPEN, precies wat de code-comment uitsluit) gaf de test rood; herstel groen.

### 6d. Verplichte blinde eindreview -- ronde 3 -- bevinding en fix (2026-08-21)

**Oordeel: NO-GO.** De reviewer koos, in plaats van de reeds bevestigde `base_agent.py`-takken
opnieuw te controleren, vier `status=`-toewijzingen om zelf te muteren -- en koos daarbij
`packs.py`, het bestand dat de ENUM-DOCSTRING in ronde 2 net had "bevestigd" op basis van
alleen de aanwezigheid van de juiste enum-waarde per constructie. Dat onderscheid (een waarde
staat er syntactisch versus een test bewijst dat de bijbehorende TAK ook echt wordt bereikt)
is precies waar de derde bevinding zat.

**BLOCKER: `test_domain_pack_sla_timeout` testte de tak niet die zijn eigen naam en
docstring claimen.** De mock `async def very_slow_call(*args):` accepteert geen
`initiated_by_user_id`, terwijl `_run_single_step()` `_execute_step()` altijd met dat keyword-
argument aanroept. Het resultaat is een `TypeError` die SYNCHROON optreedt, voordat
`asyncio.wait_for()` ooit een echte timeout kan meten -- die `TypeError` wordt niet door
`except TimeoutError:` (packs.py:385-393) gevangen maar door de sibling `except Exception as
e:` (packs.py:394-401). Omdat BEIDE takken naar `MISLUKT` mappen, bleef de
`status`-assertie toch groen; de `"timeout" in ...error_message.lower()`-assertie bleef
ook groen, niet omdat er een timeout was, maar omdat "timeout" toevallig een substring is van
de qualified name van de test zelf (`test_domain_pack_sla_timeout.<locals>.very_slow_call`) die
Python in de `TypeError`-boodschap opneemt. De reviewer bewees dit met een DUBBELE mutatie:
`packs.py:392` (de echte TimeoutError-tak) naar `GEDEELTELIJK` -> NIET gevangen (0 van 499
tests raakte); `packs.py:401` (de sibling-tak die daadwerkelijk draait) naar `GEBLOKKEERD` ->
WEL gevangen -- het bewijs dat de eerste mutatie geen toeval was maar een echte blinde vlek.

**Fix:** `very_slow_call(*args, **kwargs)` -- de coroutine bereikt nu daadwerkelijk
`asyncio.sleep(0.1)` en wordt door `asyncio.wait_for(timeout=0.01)` echt afgebroken. Om te
voorkomen dat de sibling-tak (packs.py:394-401) na deze fix zonder enige (ook niet toevallige)
dekking komt te staan, is een nieuwe, doelbewuste test toegevoegd
(`test_domain_pack_step_unexpected_exception_reports_mislukt`, `_execute_step` gooit synchroon
een `RuntimeError` i.p.v. traag te zijn) die uitsluitend deze tak raakt.

**MINOR, zelfde review: `run_pack_by_id()`'s "pack not found"-tak (packs.py:266-276) had
NUL tests van welke soort dan ook.** Bewezen met een live mutatie (`MISLUKT` -> `KLAAR` gaf 0
gedetecteerde regressies over de volledige gerichte set). De methode heeft ook geen enkele
productie-aanroeper (repo-breed gegrept) -- dezelfde situatie als het dag-1-agent-aanmaak-
endpoint, waar toen is vastgelegd dat "geen vindbare aanroeper" geen vrijstelling is van een
correcte status zodra de tak wel bereikt wordt. **Fix:** nieuwe test
`test_run_pack_by_id_not_found_reports_mislukt` toegevoegd.

**NIT, erkend maar NIET gefixed:** de zes governance-tests in `test_governance_wiring_dag4.py`
gebruiken `asyncio.get_event_loop().run_until_complete(...)` i.p.v. `@pytest.mark.asyncio`.
Bevestigd pre-existing (`git show 6132a56a:tests/unit/agents/test_governance_wiring_dag4.py`
toont dit patroon al voor dag 7 begon, in `test_governance_contract_blocks_forbidden_action`)
-- dag 7 volgde alleen de al bestaande lokale conventie van het bestand. Geen gedragsrisico,
geen dag-7-scope; niet aangepast om onaangeraakte pre-existing tests niet zonder aanleiding te
herschrijven.

**Eigen mutatiebewijs (backup/restore via `cp`, nooit `git checkout --`; `git diff --stat`
bevestigde na elk herstel een lege diff op `packs.py`):**
- `packs.py:392` MISLUKT -> GEDEELTELIJK: `test_domain_pack_sla_timeout` FAILED (was PASSED
  voor de fix); herstel PASSED.
- `packs.py:401` MISLUKT -> GEBLOKKEERD: `test_domain_pack_step_unexpected_exception_reports_mislukt`
  FAILED, `test_domain_pack_sla_timeout` bleef PASSED (bewijst dat de twee tests onafhankelijk
  hun eigen tak raken, geen kruisbesmetting); herstel PASSED.
- `packs.py:274` MISLUKT -> KLAAR: `test_run_pack_by_id_not_found_reports_mislukt` FAILED,
  de andere drie tests in het bestand bleven PASSED; herstel PASSED.

**Herverificatie na alle fixes (zelf gedraaid):**

```text
python -m pytest tests/unit/als/enterprise/test_domain_packs.py -v --timeout=60
-> 4 passed (2 bestaand + 2 nieuw)

python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60
-> 1302 passed, 2 skipped, 0 failed (was 1300/2 voor ronde 3, +2 nieuwe tests)

python -m pyright   (canoniek, geen args)
-> 0 errors, 54 warnings (baseline ongewijzigd)

ruff check tests/unit/als/enterprise/test_domain_packs.py
-> All checks passed!
```

Eindtelling BE-AGT-056: 14 nieuwe tests (7 origineel + 4 ronde 1 + 1 ronde 2 + 2 ronde 3 = 14),
22 uitgebreide tests (ongewijzigd -- ronde 3 voegde alleen nieuwe testfuncties toe, breidde
geen bestaande uit). Dag 7 is NIET gesloten -- ronde 4 van de verplichte blinde review volgt.

### 6e. Verplichte blinde eindreview -- ronde 4 -- bevindingen en fixes (2026-08-21)

**Oordeel: GO WITH MINOR ISSUES.** Geen BLOCKER -- de reviewer koos vijf eigen
`status=`-mutaties (verschillend van alle eerder genoemde plekken) over `specialist_base.py`
en `packs.py`, plus een handmatige controle van elke handgeschreven mock-functie in alle 7
testbestanden op signatuur-mismatches (exact ronde 3's faalvorm) -- geen enkele brak, geen
enkele mock bleek verkeerd. Vier bevindingen, alle verwerkt:

**Drie documentatie-slordigheden, direct gefixt (drempelmodel: elk geisoleerd, <15 min):**
1. Sectie 2 ("Locatie") citeerde nog `_execute_agent_step()` -- de niet-bestaande naam die
   Gate 2 (sectie 6a) al had gecorrigeerd naar `_run_single_step()`, maar die correctie was
   nooit tot deze regel doorgevoerd. Fix: bijgewerkt naar `_execute_step()`,
   `_run_single_step()`, `run_pack_by_id()`.
2. Sectie 17 ("Acceptatiecriteria") stond nog op het ronde-1-getal "7+4=11 nieuwe tests" --
   nooit bijgewerkt na de rondes 2 en 3. Fix: 14 (7+4+1+2), zelf herverifieerd via
   `git diff 6132a56a..HEAD -- tests/ | grep -cE "^\+.*def test_"` = 14, 0 verwijderd.
3. De Definition-of-Done-lijst stond nog op "1299 passed" (het ronde-1-getal) en noemde maar
   2 van de inmiddels 4 commits. Fix: 1302 (zelf herverifieerd, zie hieronder), alle 4
   commit-hashes.

**Een pre-existing, dormant productiebug, buiten dag-7-scope, GEBACKLOAD (niet direct
gefixed):** `base_agent.py::process_task()` doet op vier plekken (regel 507, 544, 661, 709)
`async with session_factory as db:` op de waarde uit `memory_store["session_factory"]`. De
echte DI-wiring (`_setup_memory_store()` -> `container.session_factory()` ->
`create_session_factory()`, `container.py:321-324`) zet daar een RAUWE `async_sessionmaker`
neer -- een callable factory, geen reeds-instapbare context manager. Empirisch bevestigd
(niet aangenomen): `async with een_async_sessionmaker as x:` geeft
`TypeError: 'async_sessionmaker' object does not support the asynchronous context manager
protocol`. Bevestigd pre-existing (dag 7's diff raakt deze regels niet) en vandaag dormant:
`agent_memory` staat nergens in `FEATURE_FLAGS` (dus default `False`) en geen
`FEATURE_AGENT_MEMORY`-omgevingsvariabele is gezet -- repo-breed gegrept, geen enkele
treffer. Beoordeeld tegen het drempelmodel: dit is GEEN "geisoleerd, 1 bestand, <15 min"-
geval -- de fix raakt 4 call-sites EN elke test-fake die dezelfde boundary anders mockt
(`_fake_session_factory()`, gebruikt door dit statuscontract's eigen twee GDPR-tests uit
rondes 1/2, slaat al een aangeroepen/entered contextmanager op; een naieve fix van de
call-sites alleen zou die tests breken) EN een architectuurbeslissing (moet de call-site
`session_factory()` worden, of moet `_setup_memory_store()` al een entered waarde opslaan)
-- dus Backlog, met een guard conform CLAUDE.md's regel dat elke niet-direct-gefixte
FA-bevinding een falende architecture-test vereist.

Geregistreerd als **OP-172** in het ADR-036-register (Fase D, P2). Guard:
`tests/unit/agents/test_governance_wiring_dag4.py::test_the_real_session_factory_wiring_supports_async_with_directly`,
`xfail(strict=True)`, zelfde patroon als OP-170/171. Reproduceert de ECHTE waarde via de
productiefunctie `create_session_factory()` tegen een echte in-memory SQLite-engine (niet de
testsuite's eigen `@asynccontextmanager`-fake). Mutatiegetest in beide richtingen: de laatste
regel wijzigen naar `async with session_factory() as db:` (de daadwerkelijke fix) geeft
`XPASS(strict)`, gerapporteerd als failure; de huidige vorm geeft `xfail` zoals bedoeld.

**Herverificatie na alle fixes (zelf gedraaid):**

```text
python -m pytest tests/unit/agents/test_governance_wiring_dag4.py -v --timeout=60
-> 10 passed, 1 xfailed (was 10 passed voor deze ronde)

python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60
-> 1302 passed, 2 skipped, 0 failed (ongewijzigd -- de nieuwe test is xfailed, geen pass)

python -m pyright   (canoniek, geen args)
-> 0 errors, 54 warnings (baseline ongewijzigd -- tests/ staat in pyrightconfig.json's
   exclude-lijst, geverifieerd door het bestand te lezen, dus de nieuwe guard-test heeft
   geen effect op deze poort, ook niet in zijn xfail-vorm)
```

Eindtelling BE-AGT-056: 15 nieuwe tests (14 + de OP-172-guard), 22 uitgebreide tests
(ongewijzigd). Dag 7 is NIET gesloten -- ronde 5 van de verplichte blinde review volgt.

### 6f. Verplichte blinde eindreview -- ronde 5 -- bevinding en fix (2026-08-21)

**Oordeel: NO-GO.** De reviewer nam de opdracht "controleer of ronde 4's eigen claim
('geen enkele mock bleek verkeerd') klopt" letterlijk en vond een BLOCKER een niveau
dieper dan ronde 3 en ronde 4 hadden gekeken: geen signatuur-mismatch (dat had ronde 4 al
uitgesloten), maar een GEDEELD, EENMALIG-BRUIKBAAR fake-object dat door TWEE aparte
call-sites in dezelfde `process_task()`-aanroep wordt binnengetreden.

**BLOCKER: de twee GDPR-tests (`test_gdpr_profiling_opt_out_reports_geblokkeerd`, ronde 1,
en `test_gdpr_profiling_check_failure_fails_closed_and_reports_geblokkeerd`, ronde 2)
testten geen enkele van beide beweerde paden.** Beide zetten
`agent.memory_store = {"session_factory": _fake_session_factory()}`, waarbij
`_fake_session_factory()` een `@asynccontextmanager`-generator is die EENMAAL wordt
aangeroepen. `process_task()` leest `memory_store["session_factory"]` echter op TWEE
plekken: de boot-context-loader (regel ~507) entert hem EERST, en de GDPR-opt-out-check
(regel ~544) entert VERVOLGENS DEZELFDE, inmiddels afgesloten instantie. Zelf gereproduceerd
in isolatie: een tweede `async with` op zo'n object geeft
`AttributeError: '_AsyncGeneratorContextManager' object has no attribute 'args'`. Die
AttributeError wordt door de GDPR-checks eigen `except Exception` (fail-closed) opgevangen
-- dus BEIDE tests slaagden altijd op `GEBLOKKEERD`, volledig onafhankelijk van wat
`check_profiling_opt_out()`s mock teruggaf. Zelf dubbel bewezen met een mock-inversie: (1)
`return_value=True` -> `False` op de eerste test liet hem GROEN blijven (zou het echte pad
lopen, dan had `False` -> geen blokkade -> assertiefout moeten geven); (2)
`side_effect=RuntimeError(...)` -> een schone `return_value=False` op de tweede test liet
hem OOK groen blijven. Beide mutaties bevestigd op de ONGEWIJZIGDE (pre-fix) code.

**Waarom dit zwaarder is dan ronde 3's vondst:** ronde 3's mock had een simpele
signatuur-mismatch (`*args` accepteerde geen keyword). Deze mock had een correcte
signatuur en werkte prima op zichzelf -- de fout ontstond alleen uit de SAMENLOOP van twee
onafhankelijke call-sites die een eigenlijk-bedoeld-voor-eenmalig-gebruik object delen.
Ronde 4 controleerde expliciet "elke handgeschreven mock op een signatuur-mismatch" en
concludeerde terecht dat er geen was -- maar keek niet naar hoe vaak een gedeeld fake-object
binnen EEN test-aanroep wordt entered.

**Fix:** een nieuwe, herbruikbare testfake `_ReenterableFakeSessionFactory` (een gewone
klasse met `__aenter__`/`__aexit__` die bij elke aanroep een verse `AsyncMock()` teruggeeft)
vervangt de `@asynccontextmanager`-generator in beide tests. Dit reproduceert PRECIES het
huidige productiegedrag (`async with session_factory as db:`, ongeroepen -- het OP-172-gat
zelf blijft bewust ongefixed, dat is een aparte, grotere fix) maar staat wel toe dat de
boot-context-loader EN de GDPR-check onafhankelijk van elkaar entered worden.

**Eigen mutatiebewijs NA de fix (bewijst dat de fix zelf geen nieuw hol geval creeert):**
dezelfde twee mock-inversies opnieuw uitgevoerd op de GEFIXTE code -- beide keren FAILED
(niet meer PASSED), exact zoals verwacht. Herstel -> beide weer PASSED.

**Herverificatie na de fix (zelf gedraaid):**

```text
python -m pytest tests/unit/agents/test_governance_wiring_dag4.py -v --timeout=60
-> 10 passed, 1 xfailed (ongewijzigd aantal -- geen nieuwe testfunctie, twee bestaande
   tests testen nu daadwerkelijk hun beweerde pad)

python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60
-> 1302 passed, 2 skipped, 1 xfailed (ongewijzigd)

python -m pyright   (canoniek, geen args)
-> 0 errors, 54 warnings (baseline ongewijzigd)

ruff check tests/unit/agents/test_governance_wiring_dag4.py
-> All checks passed!
```

**Tweede bevinding, NIT, niet apart gefixed (te triviaal om een eigen paragraaf te
verdienen, meegenomen in de volgende documentatiecorrectie):** de DoD-commitlijst noemde
nog maar 4 van de inmiddels 6 commits van deze dag (2 konden nooit zichzelf citeren op het
moment van schrijven, dus het realistische maximum was altijd 5) -- gecorrigeerd naar alle
6 hashes.

Dag 7 is NIET gesloten -- ronde 6 van de verplichte blinde review volgt.

### 6g. Verplichte blinde eindreview -- ronde 6 -- convergentie, dag 7 GESLOTEN (2026-08-21)

**Oordeel: GO.** Gericht op precies een vraag: opent ronde 5's eigen fix
(`_ReenterableFakeSessionFactory`, die nu een VERSE `AsyncMock()` per entry teruggeeft in
plaats van dezelfde eenmalige instantie) een nieuw gat, en bestaat er een zesde instantie
van "assertie aanwezig, waarde correct, verkeerde tak draait" elders in de dag-7-diff? Geen
van beide. De reviewer muteerde ronde 5's eigen fix (bleef niet langer indifferent aan de
mock) en 5 eigen, nieuwe `status=`-plekken in `specialist_base.py`/`packs.py` (allemaal
genuine gevangen), grepte repo-breed dat `memory_store["session_factory"]` maar in EEN
testbestand voorkomt, en herverifieerde elk numeriek document-claim zelf. Twee NIT's,
door de reviewer zelf uitdrukkelijk als "geen dag-7-bevinding" gekwalificeerd (pre-existing
AsyncMock-ruis, eigen resource-druk tijdens een losstaande run) -- geen actie.

**Zes rondes blinde eindreview, vijf vonden iets echt (rondes 1/2/3/5 gefixed, ronde 4's
OP-172 bewust gebackload), de zesde niets nieuws -- convergentie bereikt, zelfde patroon
als dag 6 (4 rondes).**

## DAG 7: GESLOTEN

Eindstand: 15 nieuwe tests (14 gedragstests + de mutatiegetoetste OP-172-`xfail`-guard), 22
uitgebreide tests, volledige mandatory regressiesuite 15741 passed/219 skipped/22
xfailed/0 failed, pyright 0 errors/54 warnings, mypy 0 errors, ruff schoon, doc-gate
684/709 zonder nieuwe incomplete IDs. Commits: `544fd1b6`, `09becbd7`, `d1df3fcd`,
`ddda38be`, `4f63be6c`, `c5b0520e`, `57cd4155`. Openstaande, bewust gebackloagde
bevinding: OP-172 (Fase D, P2, ADR-036-register) -- de `session_factory`-DI-wiring in
`base_agent.py` is dormant-gebroken zolang `agent_memory` uit staat; een echte fix raakt
minimaal 4 call-sites in `base_agent.py` plus `container.py`'s DI-contract en vereist een
architectuurbeslissing, dus buiten de scope van dag 7 zelf.

### 7. Zichtbaarheids- en toegangsregels

- Geen wijziging. `status` is write-only geweest tot vandaag (nul lezers repo-breed, zelf
  nagegaan) en krijgt geen nieuw leespad in deze fix -- geen HTTP-schema-wijziging
  (`ExecutionResultSchema`, `src/core/api/v1/orchestration/schemas.py:123-131`, heeft geen
  `status`-veld).

### 8-16. n.v.t

### 17. Acceptatiecriteria

- Alle 14 nieuwe tests slagen (7 vanuit de eerste implementatieronde en Gate 2, +4 uit
  blinde-review-ronde 1, +1 uit ronde 2, +2 uit ronde 3 -- zie secties 6a-6d); alle 22
  uitgebreide tests slagen met hun nieuwe `status`-assertie erbij. **Correctie (ronde 4):**
  deze regel stond nog op het ronde-1-getal ("7+4=11"), nooit bijgewerkt na de rondes 2 en 3
  -- zelf herverifieerd via `git diff 6132a56a..HEAD -- tests/ | grep -cE "^\+.*def test_"`
  = 14 nieuwe testfuncties, 0 verwijderd.
- Mutatiebewijs, alle zelf uitgevoerd (backup/restore via `cp` + `git diff --stat`, nooit
  `git checkout --`):
  - Prioriteitsvolgorde (governance domineert over deelsucces): de `results`-check tijdelijk
    VOOR de `governance`-check plaatsen maakt
    `test_a_governance_block_dominates_a_simultaneous_partial_success` rood.
  - `max_steps` != budgetafsluiter: een `"step_limit"`-tak toevoegen die `MEER_BUDGET_NODIG`
    teruggeeft maakt `test_exceeding_max_steps_is_reported_not_silently_truncated` rood.
  - `base_agent.py`'s zes `status=`-toewijzingen: elk apart weghalen maakt de bijbehorende
    test rood. **Correctie na de verplichte blinde eindreview (ronde 1)**: deze claim was
    voor commit `09becbd7` slechts voor 2 van de 6 waar (`status="400"`->MISLUKT en de
    governance-contract-blokkade) -- de andere vier (taakvalidatie-mislukking,
    GDPR-profileringsweigering, capaciteitslimiet, de buitenste `except`-afhandeling) hadden
    GEEN test die `.status` controleerde, ondanks de expliciete `[x]`-claim in de brief en dit
    document dat ze wel mutatiegetest waren. De reviewer bewees het gat zelf tweemaal (twee
    losse mutaties, telkens `1295 passed` -- identiek aan de ongewijzigde run, dus 0
    detectie) voordat het gefixed werd. Vier nieuwe tests toegevoegd
    (`test_task_validation_failure_reports_mislukt`,
    `test_gdpr_profiling_opt_out_reports_geblokkeerd`,
    `test_agent_at_capacity_reports_meer_budget_nodig`,
    `test_unexpected_exception_reports_mislukt`), en zelf gereproduceerd dat elk van de vier
    voorheen-ongeteste `status=`-toewijzingen nu daadwerkelijk rood wordt als hij wordt
    weggehaald.
  - `governance_unavailable` (Gate-2-bevinding): die tak naar `GEBLOKKEERD` laten wijzen
    i.p.v. `MISLUKT` maakt beide nieuwe tests (`test_a_broken_governance_gate_reports_mislukt`,
    `test_governance_unavailable_dominates_a_simultaneous_partial_success`) rood -- exact de
    mutatie waarmee Gate 2 het ontbreken van deze tests aantoonde.
- `python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60` ->
  1295 passed, 2 skipped (was 1288/2 voor dag 7 -- +7 netto, exact het aantal nieuwe
  testfuncties, zelf herverifieerd met een daadwerkelijke run na de Gate-2-fixes, niet
  berekend).

### 18. Integratoruitleg

- Geen publieke API-wijziging. `ExecutionResult.status` is een intern veld zonder
  HTTP-schema-tegenhanger.

### 19. Trainingssamenvatting

- **Actor:** `BaseSpecialistAgent.act()`/`_run_within_budget()`,
  `DomainPackOrchestrator._execute_step()`/`_run_single_step()`/`run_pack_by_id()`,
  `EnhancedBaseAgent.process_task()`.
- **Voorwaarde:** een van de bestaande uitvoerpaden rondt af, met of zonder fout.
- **Actie:** `_status_from_errors()` (of een directe toewijzing in de budget-/exception-
  afhandeling) berekent een van de vijf `ExecutionStatusContract`-waarden.
- **Systeemreactie:** `ExecutionResult.status` bevat de waarde; geen ander veld verandert.
- **Succesrespons:** `KLAAR` (volledig succes) of `GEDEELTELIJK` (deelsucces, expliciet
  benoemd in `errors`).
- **Foutrespons:** `MEER_BUDGET_NODIG` (budgetgrens), `GEBLOKKEERD` (governance-weigering),
  `MISLUKT` (onverwachte fout of onbereikbare governance-poort).
- **Uitzonderingen:** `status` blijft `None` op paden die geen van de gewijzigde bestanden
  raken (bijv. andere `ExecutionResult`-constructies buiten deze vijf bestanden) -- expliciet
  niet vandaag uitgebreid, zie "Out of scope". BINNEN de vijf bestanden zet inmiddels ELKE
  `ExecutionResult(...)`-aanroep een `status` (17 constructies, programmatisch geverifieerd
  na Gate 2 -- zie sectie 6a).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

Geen publieke API-wijziging. `ExecutionResult.status` is een intern veld; er is geen
HTTP-response-schema dat het vandaag serialiseert.

---

## Open aannames

- Dat de bestaande `errors`-lijst (vier `"kind"`-waarden) een volledige partitie is van elke
  mislukkingsvorm die `act()` vandaag kan produceren -- zelf nagelopen (alle vier
  `errors.append(...)`-plekken in het bestand zijn getagd), maar een TOEKOMSTIGE vijfde
  faalvorm zonder `"kind"` valt stil terug op de laatste `return MISLUKT`-regel, niet op een
  fout. Dat is een bewuste, veilige default (fail als MISLUKT, niet als KLAAR), geen gat.

## Open vragen

- Wanneer een Council-gemedieerd verlengingsmechanisme voor `MEER_BUDGET_NODIG` (ADR-036 D7's
  eigen tekst noemt dit) wordt gebouwd -- expliciet buiten scope van vandaag, aan Rakesh om
  in te plannen.
- Wanneer de checkpoint-tabel (Fase 4) komt en of die dit statuscontract hergebruikt of een
  eigen vocabulaire krijgt.

## Risico's

- Geen CRITICAL/HIGH. `status` had nul lezers voor vandaag (zelf nagegaan, twee
  onafhankelijke manieren, en onafhankelijk een derde keer herbevestigd door de
  security-reviewer), dus dit is een write-only uitbreiding zonder observeerbaar
  gedragsrisico voor bestaande consumenten. Het enige reele risico dat wel materialiseerde --
  vier sibling-`ExecutionResult`-constructies die op `status=None` bleven staan, en een
  volledig ongeteste prioriteitstak (`governance_unavailable`) -- is gevonden door Gate 2's
  code-reviewer (de tweede met een LIVE mutatie bewezen) en in dezelfde sessie gefixt en
  mutatiegetest.

## QA-checks

```
python -m pytest tests/unit/als/ tests/unit/agents/ tests/unit/core/ -q --timeout=60
-> 1295 passed, 2 skipped
python -m pytest tests/architecture/ -q --timeout=60
-> 671 passed, 1 xfailed (OP-170, ongewijzigd)
python -m pyright
-> 0 errors, 54 warnings (baseline ongewijzigd)
python scripts/run_mypy_audit.py
-> 0 errors, baseline 0
ruff check <alle 12 gewijzigde bestanden>
-> All checks passed!
python scripts/validate_feature_docs.py
-> 684/709, geen nieuwe incomplete IDs
python -m pytest tests/unit tests/architecture tests/core -n 4 --timeout=60 -q --tb=short --ignore=tests/core/agents/test_focus_builder_chat_agent.py
-> 15734 passed, 219 skipped, 21 xfailed, 0 failed
```

## Definition of Done

- [x] Rode tests geschreven (via TDD-volgorde: enum eerst als inerte vocabulaire, toen
      pyright de eerste ECHTE regressie toonde -- `base_agent.py:622`'s `status="400"` --
      direct gefixed, daarna de volledige testset geschreven en bevestigd rood/groen)
- [x] Gate 2 (code-reviewer: CHANGES_REQUESTED -> 2 bevindingen gefixed + mutatiegetest;
      security-reviewer: GO, geen bevindingen)
- [x] Implementatie voltooid (5 productiebestanden; scope groeide van 1 naar 6 plekken in
      `base_agent.py` en van 5 naar 6 in `packs.py`, elke uitbreiding expliciet gemotiveerd,
      niet stilzwijgend)
- [x] Mutatiebewijs in beide richtingen voor de prioriteitsvolgorde, de max_steps-correctie,
      alle zes base_agent.py-toevoegingen, en de Gate-2-gevonden `governance_unavailable`-tak
- [x] ADR-036-register: EEN nieuwe rij nodig (OP-172, zie sectie 6e) -- een pre-existing,
      dormant DB-wiringbug (`agent_memory`-flag staat overal uit) gevonden door ronde 4,
      buiten dag-7-scope, gebackload met een groene guard + gedateerde uitzondering +
      staleness-test conform het drempelmodel. **Correctie (ronde 4):** deze regel zei
      voorheen "geen nieuwe rij nodig" -- dat klopte tot ronde 4 iets vond dat niet binnen
      dag 7's <15-min-criterium paste.
- [x] Volledige gerichte set groen (1302 passed, 2 skipped, 0 failed -- na ronde 3's fix;
      was 1299 na ronde 1, 1300 na ronde 2, 1295 voor ronde 1). **Correctie (ronde 4):** deze
      regel stond nog op het ronde-1-getal (1299), nooit bijgewerkt na de rondes 2 en 3 --
      zelf herverifieerd: `python -m pytest tests/unit/als/ tests/unit/agents/
      tests/unit/core/ -q --timeout=60` geeft vandaag opnieuw 1302 passed, 2 skipped.
- [x] Volledige architecture-suite groen (671 passed, 1 xfailed -- OP-170, ongewijzigd)
- [x] Doc-gate (`validate_feature_docs.py`) groen -- 684/709, geen nieuwe incomplete IDs
      (zelf herbevestigd, de eerdere `[ ]` was zelf een stale claim: de review-file bestond
      en de gate stond al groen op het moment dat deze regel nog onafgevinkt was)
- [x] ID-REGISTRY bijgewerkt
- [x] Commit (`544fd1b6`, `09becbd7`, `d1df3fcd`, `ddda38be`, `4f63be6c`, `c5b0520e`) +
      final-approver-brief + verplichte blinde review (ronde 1: NO-GO, gefixt; ronde 2: GO WITH MINOR ISSUES,
      gefixt; ronde 3: NO-GO, gefixt; ronde 4: zie hieronder). **Correctie (ronde 4):** deze
      regel noemde nog maar 2 van de inmiddels 4 commits.
